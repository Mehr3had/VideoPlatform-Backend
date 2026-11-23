import json
import os
import re
import sys

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
AUTH_TOKEN_FILE = BASE_DIR / ".env"
EVENT_URL = "http://127.0.0.1:8000/videos/api/live/mediamtx-event/"

load_dotenv(AUTH_TOKEN_FILE)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"online", "offline"}:
        print("Invalid MediaMTX hook event.", file=sys.stderr)
        return 2

    token = os.getenv("LIVE_WEBHOOK_TOKEN", "").strip()
    stream_path = os.getenv("MTX_PATH", "").strip("/")
    source_id = os.getenv("MTX_SOURCE_ID", "").strip()

    if not token:
        print("LIVE_WEBHOOK_TOKEN is missing.", file=sys.stderr)
        return 2

    if not re.fullmatch(r"live/[1-9]\d*", stream_path):
        print("Invalid MTX_PATH.", file=sys.stderr)
        return 2

    if not source_id or len(source_id) > 128:
        print("Invalid MTX_SOURCE_ID.", file=sys.stderr)
        return 2

    payload = {
        "event": sys.argv[1],
        "path": stream_path,
        "source_id": source_id,
    }

    request = Request(
        EVENT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Live-Webhook-Token": token,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            print(
                f"[MediaMTX hook] {sys.argv[1]} "
                f"{stream_path}: HTTP {response.status}"
            )
            return 0

    except HTTPError as error:
        detail = error.read(512).decode("utf-8", "replace")
        print(
            f"[MediaMTX hook] Django returned HTTP {error.code}: {detail}",
            file=sys.stderr,
        )
        return 1

    except (URLError, TimeoutError, OSError) as error:
        print(
            f"[MediaMTX hook] Could not contact Django: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())