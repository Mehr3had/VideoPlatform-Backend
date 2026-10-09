# VideoPlatform — Django REST API

A video-sharing platform built with Django and Django REST Framework. The project includes JWT authentication, video management, reactions, comments, user profiles, subscriptions, search, categories, and pagination.

## Tech Stack

* Python
* Django
* Django REST Framework
* Simple JWT
* SQLite
* Pillow
* django-cors-headers

## Features

* User registration and JWT-based authentication
* User profiles and profile editing
* Video upload, editing, and deletion
* Video thumbnails and playback
* Video views and trending videos
* Likes and dislikes
* Comments
* User subscriptions
* Search, categories, and pagination
* User dashboard and account settings

## Requirements

* Python compatible with the installed Django version
* Git
* The companion Next.js frontend (in a separate repository, if applicable)

## Local Setup

### 1. Clone the repository

```bash
git clone <BACKEND_REPOSITORY_URL>
cd VideoPlatform
```

Replace `<BACKEND_REPOSITORY_URL>` with the actual repository URL.

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-new-secret-key
```

Generate a new key using:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated value into `.env`. Never commit `.env` or share its contents.

### 5. Apply database migrations

```powershell
python manage.py migrate
```

### 6. Start the development server

```powershell
python manage.py runserver
```

The API server will be available at:

`http://127.0.0.1:8000/`

## Media Files

Uploaded videos, thumbnails, and profile images are stored under `media/` during local development. Ensure the required sample media files are present if you want to reproduce the demo content.

User-uploaded media should be handled separately from source code in a production deployment.

## Frontend Integration

The companion frontend is built with Next.js and runs locally on port `3000`. Django's CORS configuration should allow the frontend origin:

`http://localhost:3000`

Make sure the frontend API base URL points to the local Django server.

## Security Notes

* Keep `.env` out of version control.
* Use a strong, unique secret key.
* `DEBUG=True` is for local development only.
* Configure `ALLOWED_HOSTS`, HTTPS, database settings, and production media storage before deployment.
* Do not publish real user credentials or tokens.

## Status

This project was developed as a learning and portfolio project, with a focus on REST APIs, authentication, media handling, and full-stack integration.
