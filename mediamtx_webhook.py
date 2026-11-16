import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parent

os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
django.setup()

from django.conf import settings


API_BASE = "http://127.0.0.1:8000/videos/api/live"

EVENT_URL = f"{API_BASE}/mediamtx-event/"
ARCHIVE_URL = f"{API_BASE}/mediamtx-archive/"


def post_json(url, payload, timeout=5):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Live-Webhook-Token": settings.LIVE_WEBHOOK_TOKEN,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode(
                "utf-8",
                errors="replace",
            )
            return response.status, body

    except HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        return exc.code, body


def main():

    if (
        len(sys.argv) != 2
        or sys.argv[1] not in {"online", "offline"}
    ):
        print("Invalid webhook event.", file=sys.stderr)
        return 2

    event = sys.argv[1]

    stream_path = os.environ.get(
        "MTX_PATH", ""
    ).strip("/")

    source_id = os.environ.get(
        "MTX_SOURCE_ID", ""
    ).strip()

    token = getattr(
        settings,
        "LIVE_WEBHOOK_TOKEN",
        "",
    )

    if (
        not re.fullmatch(r"live/[1-9]\d*", stream_path)
        or not source_id
        or len(source_id) > 128
        or not token
    ):
        print(
            "Missing or invalid webhook environment.",
            file=sys.stderr,
        )
        return 2

    event_payload = {
        "event": event,
        "path": stream_path,
        "source_id": source_id,
    }

    try:

        # First update the stream state in Django.
        event_status, event_body = post_json(
            EVENT_URL,
            event_payload,
            timeout=10,
        )

        print(
            f"MediaMTX webhook {event}: "
            f"HTTP {event_status} - {event_body}",
            flush=True,
        )

        if not 200 <= event_status < 300:
            print(
                "Stream event was rejected.",
                file=sys.stderr,
            )
            return 1

        try:
            event_data = json.loads(event_body)
        except json.JSONDecodeError:
            print(
                "Invalid JSON response from event endpoint.",
                file=sys.stderr,
            )
            return 1

        # Online events only update the live status.
        if event == "online":
            return 0

        # Do not archive when an old publisher disconnects.
        if event_data.get("ignored"):
            print(
                "Offline event ignored; archive was not requested.",
                flush=True,
            )
            return 0

        # Archive only after Django confirms that the stream ended.
        if event_data.get("status") != "ended":
            print(
                "Stream is not ended; archive was not requested.",
                file=sys.stderr,
            )
            return 1

        archive_payload = {
            "path": stream_path,
        }

        print(
            f"Starting archive processing for {stream_path}...",
            flush=True,
        )

        # Archive processing can include waiting, merging and HLS generation.
        archive_status, archive_body = post_json(
            ARCHIVE_URL,
            archive_payload,
            timeout=900,
        )

        print(
            f"MediaMTX archive: "
            f"HTTP {archive_status} - {archive_body}",
            flush=True,
        )

        if not 200 <= archive_status < 300:
            print(
                "Archive processing failed.",
                file=sys.stderr,
            )
            return 1

        return 0

    except (URLError, TimeoutError, OSError) as exc:
        print(
            f"Webhook connection failed: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())