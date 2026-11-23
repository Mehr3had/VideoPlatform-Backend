import json
import os
import re
import sys
import time

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ARCHIVE_URL = (
    "http://127.0.0.1:8000/"
    "videos/api/live/mediamtx-archive/"
)


def main():
    if len(sys.argv) != 2 or sys.argv[1] != "archive":
        print("Invalid archive hook command.", file=sys.stderr)
        return 2

    token = os.getenv("LIVE_WEBHOOK_TOKEN", "").strip()
    stream_path = os.getenv("MTX_PATH", "").strip("/")
    segment_path = os.getenv("MTX_SEGMENT_PATH", "").strip()

    match = re.fullmatch(r"live/([1-9]\d*)", stream_path)

    if not token or len(token) < 32:
        print("Archive webhook token is missing or invalid.", file=sys.stderr)
        return 2

    if not match:
        print("Invalid MTX_PATH.", file=sys.stderr)
        return 2

    if not segment_path or Path(segment_path).suffix.lower() != ".mp4":
        print("Invalid MTX_SEGMENT_PATH.", file=sys.stderr)
        return 2

    payload = json.dumps(
        {"path": stream_path}
    ).encode("utf-8")

    # Retry HTTP 409 because the offline event might still be updating
    # the Django stream status when this hook starts.
    max_attempts = 30

    for attempt in range(1, max_attempts + 1):
        request = Request(
            ARCHIVE_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Live-Webhook-Token": token,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=660) as response:
                body = response.read(2048).decode("utf-8", "replace")

                print(
                    f"[MediaMTX archive hook] {stream_path}: "
                    f"HTTP {response.status} - {body}"
                )

                if response.status in (200, 201, 202):
                    return 0

                return 1

        except HTTPError as error:
            detail = error.read(2048).decode("utf-8", "replace")

            if error.code == 409 and attempt < max_attempts:
                print(
                    f"[MediaMTX archive hook] Stream is not ended yet. "
                    f"Retry {attempt}/{max_attempts - 1}."
                )
                time.sleep(1)
                continue

            print(
                f"[MediaMTX archive hook] Django returned "
                f"HTTP {error.code}: {detail}",
                file=sys.stderr,
            )
            return 1

        except (URLError, TimeoutError, OSError) as error:
            print(
                f"[MediaMTX archive hook] Could not contact Django: {error}",
                file=sys.stderr,
            )
            return 1

    print(
        f"[MediaMTX archive hook] Archive trigger retries exhausted for {stream_path}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())