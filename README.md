# VideoPlatform Backend

A Django REST Framework backend for a video-sharing platform inspired by YouTube and Aparat. It provides authentication, video and media management, comments, channel subscriptions, notifications, moderation, and live-streaming APIs for the Next.js frontend.

## Related repository

- **Frontend:** [VideoPlatform-Frontend](https://github.com/Mehr3had/VideoPlatform-Frontend)
- **Backend:** [VideoPlatform-Backend](https://github.com/Mehr3had/VideoPlatform-Backend)

## Tech stack

| Technology | Purpose |
|---|---|
| Python 3.14 | Backend runtime (tested locally) |
| Django 6.1.1 | Web framework |
| Django REST Framework 3.18.1 | REST APIs |
| Simple JWT 5.5.1 | JWT authentication and refresh-token rotation |
| SQLite | Default local development database |
| Pillow 12.3.0 | Image processing |
| django-cors-headers 4.9.0 | Frontend cross-origin requests |
| FFmpeg / FFprobe | Media processing and metadata extraction |
| MediaMTX 1.21.3 | RTMP ingest, HLS delivery, and live recording (local demo setup) |

Exact Python dependency versions are pinned in [`requirements.txt`](requirements.txt).

## Frontend Screenshots

The following screenshots showcase the user interface of VideoPlatform.

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="https://raw.githubusercontent.com/Mehr3had/VideoPlatform-Frontend/master/docs/screenshots/home.png" width="100%" alt="Home Page">
    </td>
    <td width="50%" valign="top">
      <img src="https://raw.githubusercontent.com/Mehr3had/VideoPlatform-Frontend/master/docs/screenshots/video-player.png" width="100%" alt="Video Player">
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <img src="https://raw.githubusercontent.com/Mehr3had/VideoPlatform-Frontend/master/docs/screenshots/profile.png" width="100%" alt="Creator Profile">
    </td>
    <td width="50%" valign="top">
      <img src="https://raw.githubusercontent.com/Mehr3had/VideoPlatform-Frontend/master/docs/screenshots/settings.png" width="100%" alt="User Settings">
    </td>
  </tr>
</table>

For more details about the frontend, visit the [Frontend Repository](https://github.com/Mehr3had/VideoPlatform-Frontend).

## Features

### Authentication and account management

- User registration and JWT authentication.
- Access-token refresh and refresh-token rotation with blacklist support.
- User profiles and profile editing.
- Username and password management.
- Forgot-username and password-reset workflows.
- Account deletion.

### Video management and playback

- Upload, edit, and delete videos.
- Video thumbnails, duration extraction, and view counts.
- Trending videos, category filtering, title/description search, and pagination.
- Video likes and dislikes.
- Video-quality metadata and support for 480p, 720p, and 1080p files.
- Persian and English subtitle support.

> **Video quality processing:** the FFmpeg quality-generation utility is separate from the upload flow; uploading a video does not automatically generate every quality variant.

### Comments and moderation

- Comments, replies, editing, and deletion.
- Comment likes and dislikes.
- Question-style comments and spoiler-range metadata.
- User reports and administrative review of reported comments.

### Subscriptions and notifications

- Subscribe to and unsubscribe from channels.
- Notifications for channel activity, new videos, comment replies, and interactions.
- Notification preferences, unread counts, read status, and deletion.
- Subscriber milestone notifications.

### Live streaming

- Create and manage live streams through the API.
- Generate a publisher credential for an RTMP stream.
- Authenticate MediaMTX publishing requests through a Django HTTP-auth endpoint.
- Track publisher online/offline events and update live-stream status.
- Deliver the live stream through MediaMTX HLS.
- Record live streams and request archive processing when a stream ends.
- Live chat, message reporting, and live-stream reactions.
- Live-stream reporting and administrative moderation for live-stream and chat reports.

The publisher secret is returned when a live stream is created and must be treated as a credential. Do not commit, log, or share it.

### Media maintenance

Two Django management commands help identify old, unused media:

- `cleanup_hls` — checks eligible temporary, backup, or orphan HLS directories.
- `cleanup_media` — checks media files that are no longer referenced by database records.

Both commands are designed to preview eligible items by default. Use `--execute` only after reviewing the output. The default age threshold is 24 hours and can be changed with `--older-than-hours`.

## Getting started

### Prerequisites

- Git.
- Python 3.14 (the version used for local verification).
- FFmpeg and FFprobe available on `PATH` for media operations.
- Node.js and npm if you also run the frontend.
- MediaMTX 1.21.3 or a compatible version for live streaming.

### 1. Clone the repository

```bash
git clone https://github.com/Mehr3had/VideoPlatform-Backend.git
cd VideoPlatform-Backend
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use the virtual-environment interpreter directly or follow your local PowerShell execution-policy guidance.

### 3. Install Python dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the backend project root:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
LIVE_WEBHOOK_TOKEN=replace-with-a-separate-random-token
```

Generate values locally:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use the first value for `DJANGO_SECRET_KEY` and the second for `LIVE_WEBHOOK_TOKEN`. Keep `.env` private; never commit these values or paste them into issue reports.

### 5. Apply migrations

```powershell
python manage.py migrate
```

The default development configuration uses SQLite and creates `db.sqlite3` locally.

### 6. Create an administrator (optional)

```powershell
python manage.py createsuperuser
```

### 7. Run Django

```powershell
python manage.py runserver 127.0.0.1:8000
```

Local addresses:

- Django application: `http://127.0.0.1:8000/`
- Django Admin: `http://127.0.0.1:8000/admin/`
- Video application routes: `http://127.0.0.1:8000/videos/`
- API root: `http://127.0.0.1:8000/videos/api/`

The current development settings allow `localhost` and `127.0.0.1` as hosts and allow the frontend origin `http://localhost:3000` for CORS and CSRF. Update these settings deliberately when using a different local origin or deployment domain.

## Live streaming setup

Live streaming uses Django for stream creation and authorization, MediaMTX for RTMP ingest/HLS delivery/recording, and the frontend for the creator and viewer interfaces.

### MediaMTX configuration

The local demo configuration uses the following settings:

| Setting | Local demo value |
|---|---|
| HTTP authentication | Django MediaMTX-auth endpoint |
| Auth endpoint | `http://127.0.0.1:8000/videos/api/live/mediamtx-auth/` |
| RTMP listener | `127.0.0.1:1935` |
| HLS listener | `127.0.0.1:8888` |
| HLS variant | `mpegts` |
| HLS segment count | `35` |
| HLS segment duration | `2s` |
| HLS muxer close timeout | `10s` |
| Recording format | `fmp4` |
| Recording part duration | `1s` |
| Recording segment duration | `1h` |
| Recording retention | `168h` (7 days) |

With 35 segments of approximately 2 seconds each, the configured HLS playlist represents an approximately 70-second rolling window. Actual playback availability can vary with stream and player behavior.

The MediaMTX configuration file is a local deployment asset and is not included in this repository. Create or adapt your own configuration; do not copy machine-specific absolute paths from another developer's setup.

### Webhook integration

`mediamtx_webhook.py` sends publisher lifecycle events to the Django API. It expects:

- `LIVE_WEBHOOK_TOKEN` to be configured in the backend `.env` file.
- MediaMTX to provide `MTX_PATH` and `MTX_SOURCE_ID` for the event.
- The Django API to be reachable at `http://127.0.0.1:8000` from the MediaMTX process.
- MediaMTX ready/not-ready hooks to invoke the script with the `online` and `offline` event argument respectively.

The webhook updates the stream state. On a confirmed offline event, it can request archive processing through the backend archive endpoint. Keep the webhook token private and configure the hooks using paths and Python executable locations appropriate to your operating system.

### Publisher and playback flow

1. Start Django and MediaMTX.
2. Open the frontend Live Studio and create a live stream.
3. Use the RTMP publishing address and one-time stream credential returned by the API in OBS or a compatible RTMP publisher such as FFmpeg.
4. MediaMTX authenticates the publisher through Django and serves HLS to viewers.
5. The MediaMTX webhook reports online/offline events to Django; after a confirmed end event, archive processing is requested.

The publisher credential is sensitive. Do not include an actual stream key in documentation, screenshots, logs, or Git commits.

## API overview

Application API routes are mounted under `/videos/api/`.

| Endpoint | Purpose |
|---|---|
| `POST /videos/api/register/` | Register a user |
| `POST /videos/api/login/` | Obtain JWT tokens |
| `POST /videos/api/refresh/` | Refresh an access token |
| `/videos/api/me/` | Current-user information |
| `/videos/api/videos/` | List and search videos |
| `POST /videos/api/videos/upload/` | Upload a video |
| `/videos/api/videos/<video_id>/` | Video details, qualities, and subtitles |
| `/videos/api/categories/` | List categories |
| `/videos/api/users/<user_id>/` | User profile |
| `/videos/api/users/<user_id>/subscribe/` | Subscribe to or unsubscribe from a channel |
| `/videos/api/notifications/` | Notifications |
| `/videos/api/notification-preferences/` | Notification preferences |
| `/videos/api/live/` | Create a live stream |
| `/videos/api/live/active/` | List active live streams |
| `/videos/api/live/<live_id>/` | Live-stream details |
| `/videos/api/live/<live_id>/chat/` | Read or send live-chat messages |
| `/videos/api/live/<live_id>/react/` | Live-stream reactions |
| `/videos/api/live/<live_id>/report/` | Report a live stream |
| `/videos/api/live/<live_id>/chat/<message_id>/report/` | Report a live-chat message |
| `/videos/api/admin/live-reports/` | Review live-stream reports |
| `/videos/api/admin/live-chat-reports/` | Review live-chat reports |
| `/videos/api/live/mediamtx-auth/` | MediaMTX publisher authentication |
| `/videos/api/live/mediamtx-event/` | Receive MediaMTX lifecycle events |
| `/videos/api/live/mediamtx-archive/` | Request live archive processing |

Authentication and HTTP methods vary by endpoint. The table is an overview; inspect `videos/urls.py` and the corresponding views for request methods, permissions, and payload details.

### Versioned API (v1)

The backend provides a versioned API namespace under:

`/videos/api/v1/`

API v1 includes the platform's existing application endpoints and dedicated
user-data endpoints. The legacy `/videos/api/` routes are retained
for backward compatibility.

#### User preferences

| Method | Endpoint | Description |
|---|---|---|
| GET | `/videos/api/v1/user-preferences/` | Retrieve the authenticated user's preferences |
| PATCH | `/videos/api/v1/user-preferences/` | Update user preferences |

Supported preference fields:

| Field | Allowed values |
|---|---|
| `language` | `fa`, `en` |
| `theme` | `light`, `dark` |
| `accent` | Six-digit hex color (e.g. `#8b5cf6`) |
| `background_style` | `default`, `soft`, `blue` |
| `playback_rate` | `0.25` to `2.0` |
| `volume` | `0.0` to `1.0` |
| `muted` | `true`, `false` |

#### Watch history

| Method | Endpoint | Description |
|---|---|---|
| GET | `/videos/api/v1/watch-history/` | Retrieve the authenticated user's watch history |
| DELETE | `/videos/api/v1/watch-history/` | Delete all watch-history entries |
| GET | `/videos/api/v1/watch-history/<video_id>/` | Retrieve watch progress for a video |
| PATCH | `/videos/api/v1/watch-history/<video_id>/` | Update playback progress, subtitle language, and completion status |
| DELETE | `/videos/api/v1/watch-history/<video_id>/` | Delete a specific watch-history entry |

The watch-history collection endpoint returns 50 records by default.
Use `?limit=<number>` to request between 1 and 100 records.

Watch history stores playback position, duration, subtitle language,
completion status, and the last update timestamp.

#### Search history

| Method | Endpoint | Description |
|---|---|---|
| GET | `/videos/api/v1/search-history/` | Retrieve recent searches |
| POST | `/videos/api/v1/search-history/` | Save a search query |
| DELETE | `/videos/api/v1/search-history/` | Clear search history |
| DELETE | `/videos/api/v1/search-history/?query=<query>` | Delete a specific search query |

Search history retains up to five recent queries per authenticated user.

All user-data endpoints require authentication and operate only on the
currently authenticated user's records.

## Maintenance commands

Preview old/orphan HLS directories:

```powershell
python manage.py cleanup_hls
```

Execute eligible HLS cleanup after reviewing the preview:

```powershell
python manage.py cleanup_hls --execute
```

Preview media files not referenced by database records:

```powershell
python manage.py cleanup_media
```

Execute eligible media cleanup after reviewing the preview:

```powershell
python manage.py cleanup_media --execute
```

Both commands accept `--older-than-hours` to change the default 24-hour threshold. Always review the dry-run output before using `--execute`, especially on a database containing user uploads.

## Frontend integration

The companion frontend is a Next.js application. For local development, it typically runs at `http://localhost:3000`.

Set the frontend `.env.local` file to:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

The current backend CORS and CSRF settings allow `http://localhost:3000`. See the [frontend README](https://github.com/Mehr3had/VideoPlatform-Frontend#readme) for installation and run instructions.

## Local data and files

A fresh clone does not include the local SQLite database or uploaded media. The following runtime data is intentionally excluded from Git: uploaded videos, generated HLS segments, live recordings, generated thumbnails, subtitles, profile images, and other local media. The frontend's static Pishi sticker assets are stored in the frontend repository.

After migrations, create an administrator, add categories, and upload your own sample content as needed.

## Security and deployment notes

- Keep `.env`, `DJANGO_SECRET_KEY`, `LIVE_WEBHOOK_TOKEN`, JWTs, and publisher credentials out of version control.
- Never use the development `DEBUG=True` configuration as a production configuration.
- Configure `ALLOWED_HOSTS`, CORS, CSRF trusted origins, HTTPS, database, media storage, and webhook networking for your deployment.
- Restrict MediaMTX RTMP/HLS listeners and webhook access according to your network design.
- This repository's SQLite and local media configuration is intended for development/demo use, not a production deployment recipe.

## Project status

VideoPlatform is a full-stack learning and portfolio project. Features are developed incrementally; production deployment, operational monitoring, and comprehensive security testing are separate tasks.

## License

No license has been specified yet.
