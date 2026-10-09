# VideoPlatform — Django REST API

A video-sharing platform built with Django and Django REST Framework, featuring JWT authentication, video management, reactions, comments, user profiles, subscriptions, search, categories, and pagination.

## Related Repository

* **Backend:** [VideoPlatform-Backend](https://github.com/Mehr3had/VideoPlatform-Backend)
* **Frontend:** [VideoPlatform-Frontend](https://github.com/Mehr3had/VideoPlatform-Frontend)

## Tech Stack

* Python
* Django
* Django REST Framework
* Simple JWT
* SQLite
* Pillow
* django-cors-headers

## Features

* User registration and JWT authentication
* User profiles and profile editing
* Video upload, playback, editing, and deletion
* Video thumbnails and view counts
* Trending videos
* Likes and dislikes
* Comments
* User subscriptions
* Search, categories, and pagination
* User dashboard and account settings
* Next.js frontend integration

## Getting Started

### Prerequisites

* Python compatible with the installed Django version
* Git
* Node.js and npm if you also want to run the frontend

### 1. Clone the repository

```bash
git clone https://github.com/Mehr3had/VideoPlatform-Backend.git
cd VideoPlatform-Backend
```

### 2. Create a virtual environment

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

Create a `.env` file in the project root and add:

```dotenv
DJANGO_SECRET_KEY=your-generated-secret-key
```

Generate a new secret key:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated key into `.env`. Never commit this file or share its contents.

### 5. Apply database migrations

```powershell
python manage.py migrate
```

### 6. Start the development server

```powershell
python manage.py runserver
```

The backend will run at:

`http://127.0.0.1:8000/`

The API endpoints are available under `/videos/api/`.

## Frontend Integration

The frontend is built with Next.js and runs locally at `http://localhost:3000`.

Configure the frontend API base URL to point to the Django backend:

`http://127.0.0.1:8000`

The backend's CORS settings are configured for the local frontend origin.

See the [frontend repository](https://github.com/Mehr3had/VideoPlatform-Frontend) for its setup instructions.

## Media Files

Sample thumbnail images are included in the repository. Video files, uploaded profile images, and the local SQLite database are not included.

After setting up the project, create an account through the registration endpoint or create an administrator with:

```powershell
python manage.py createsuperuser
```

Upload your own video files to test video playback and media-related features.

## Security Notes

* Keep `.env` out of version control.
* Use a unique secret key.
* `DEBUG=True` is intended for local development only.
* Configure `ALLOWED_HOSTS`, HTTPS, production database settings, and media storage before deployment.
* Never publish real credentials, secret keys, or authentication tokens.

## Project Status

A learning and portfolio project focused on Django REST APIs, authentication, media handling, and full-stack integration.
