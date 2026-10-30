# VideoPlatform Backend

A Django REST API for a video-sharing platform inspired by YouTube and Aparat. This project focuses on backend development, authentication, video and comment management, subscriptions, notifications, and integration with a Next.js frontend.

## Related Repositories

- **Backend:** [VideoPlatform-Backend](https://github.com/Mehr3had/VideoPlatform-Backend)
- **Frontend:** [VideoPlatform-Frontend](https://github.com/Mehr3had/VideoPlatform-Frontend)

## Tech Stack

- Python
- Django
- Django REST Framework
- Simple JWT
- SQLite
- Pillow
- django-cors-headers
- FFmpeg / FFprobe
- Next.js (frontend)

## Features

### Authentication and Account Management

- User registration and JWT authentication
- User profiles and profile editing
- Username and password management
- Forgot-username and password-reset workflows
- Account deletion

### Video Management

- Upload, edit, and delete videos
- Video thumbnails and view counts
- Video duration extraction using FFprobe
- Trending videos
- Video reactions (likes and dislikes)
- Category-based filtering
- Search by video title and description
- Paginated video listings

### Video Playback Support

- Multiple video quality support (480p, 720p, and 1080p)
- Video quality metadata and file management
- Persian and English subtitle support
- Subtitle and quality information included in video detail responses

**Note:** Video quality generation is currently implemented as a separate processing utility and is not automatically triggered during video uploads.

### Comments and Moderation

- Create comments and replies
- Like and dislike comments
- Edit and delete comments
- Report inappropriate comments
- Administrative report management
- Comment moderation through Django Admin

### Subscriptions and Notifications

- Subscribe to and unsubscribe from channels
- Notifications for new videos from subscribed channels
- Notifications for comment replies and interactions
- Notification preferences
- Unread notification counts
- Mark notifications as read
- Delete individual notifications or clear all notifications
- Subscriber milestone notifications

### User Dashboard

- User dashboard and account settings
- Profile and content management
- Integration with the Next.js frontend

## Getting Started

### Prerequisites

- Python compatible with the project's installed Django version
- Git
- FFmpeg and FFprobe available in the system PATH
- Node.js and npm if you also want to run the frontend

### 1. Clone the repository

```bash
git clone https://github.com/Mehr3had/VideoPlatform-Backend.git
cd VideoPlatform-Backend
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and configure the Django secret key:

```dotenv
DJANGO_SECRET_KEY=your-generated-secret-key
```

Generate a secure key with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated value into `.env`. Never commit your secret key or share it publicly.

### 5. Apply database migrations

```powershell
python manage.py migrate
```

This applies the database migrations to the local SQLite database.

### 6. Create an administrator (optional)

```powershell
python manage.py createsuperuser
```

### 7. Run the development server

```powershell
python manage.py runserver
```

The backend will be available at:

- Application: `http://127.0.0.1:8000/`
- Django Admin: `http://127.0.0.1:8000/admin/`
- Video application routes: `http://127.0.0.1:8000/videos/`
- API routes: `http://127.0.0.1:8000/videos/api/`

## API Overview

The following table lists selected API endpoints. The application-specific endpoints are mounted under `/videos/`.

| Endpoint | Purpose |
|---|---|
| `/videos/api/register/` | User registration |
| `/videos/api/login/` | User login |
| `/videos/api/refresh/` | Refresh JWT access token |
| `/videos/api/me/` | Current user information |
| `/videos/api/account/username/` | Change username |
| `/videos/api/account/password/` | Change password |
| `/videos/api/account/delete/` | Delete account |
| `/videos/api/password-reset/` | Request a password reset |
| `/videos/api/password-reset/confirm/` | Confirm a password reset |
| `/videos/api/videos/` | List and search videos |
| `/videos/api/videos/upload/` | Upload a video |
| `/videos/api/videos/trending/` | Retrieve trending videos |
| `/videos/api/videos/<video_id>/` | Retrieve video details, qualities, and subtitles |
| `/videos/api/categories/` | Retrieve categories |
| `/videos/api/users/<user_id>/` | Retrieve a user profile |
| `/videos/api/users/<user_id>/videos/` | Retrieve videos uploaded by a user |
| `/videos/api/users/<user_id>/subscribe/` | Manage a channel subscription |
| `/videos/<video_id>/react/` | Retrieve or update a video reaction |
| `/videos/<video_id>/comments/` | Retrieve and create comments |
| `/videos/api/comments/<comment_id>/like/` | Like a comment |
| `/videos/api/comments/<comment_id>/report/` | Report a comment |
| `/videos/api/notifications/` | Retrieve notifications |
| `/videos/api/notifications/unread-count/` | Retrieve the unread notification count |
| `/videos/api/notification-preferences/` | Manage notification preferences |
| `/videos/api/admin/reports/` | Review comment reports |

HTTP methods, authentication requirements, and request payloads vary by endpoint. Refer to the corresponding view in `videos/views.py` for the exact behavior.

## Search, Filtering, and Pagination

The video listing endpoint supports searching by title or description, filtering by category, and paginating results.

Example request:

```http
GET /videos/api/videos/?search=Batman&category=1&page=2&page_size=10
```

Query parameters:

| Parameter | Description |
|---|---|
| `search` | Search video titles and descriptions |
| `category` | Filter videos by category ID |
| `page` | Select the results page |
| `page_size` | Choose the number of results per page |

Pagination defaults to **6 videos per page**, with a configurable maximum of **20 videos per page**.

## Video Processing

The backend uses FFprobe to extract video duration during upload.

A separate video-processing utility uses FFmpeg to generate different video resolutions:

- 480p
- 720p
- 1080p

The utility skips resolutions higher than the source video's resolution. Generated video files and subtitle files are stored in the media directory and are excluded from version control.

Video quality generation currently requires invoking the processing utility separately.

## Frontend Integration

The frontend is built with Next.js and runs locally at `http://localhost:3000`.

Configure the frontend's `.env.local` file:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

The frontend uses this variable as the base URL for backend requests and resource URLs.

Ensure that Django's CORS configuration allows requests from the frontend origin. See the [frontend repository](https://github.com/Mehr3had/VideoPlatform-Frontend) for frontend setup instructions.

## Media Files and Local Data

Uploaded videos, thumbnails, profile images, subtitles, generated video qualities, and the local SQLite database are excluded from version control.

A fresh clone will not include locally uploaded media or sample content created during development. After applying migrations, create categories and upload your own videos and thumbnails through Django Admin or the available API endpoints.

Subtitles and video quality records can be managed through Django Admin.

## Security Notes

- Keep `.env` out of version control.
- Use a unique secret key.
- Keep `DEBUG=True` restricted to local development.
- Configure `ALLOWED_HOSTS`, HTTPS, database settings, and media storage before production deployment.
- Never publish real credentials, secret keys, or authentication tokens.

## Project Status

This is a full-stack learning and portfolio project demonstrating Django REST API development and integration with a Next.js frontend. Features are developed incrementally; production deployment and comprehensive security testing should be considered separate tasks.

## License

No license has been specified yet.