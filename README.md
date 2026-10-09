# VideoPlatform — Django REST API

A video-sharing platform backend built with Django and Django REST Framework. It provides APIs for authentication, video management, reactions, comments, user profiles, subscriptions, search, categories, and pagination.

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
* Integration with a Next.js frontend

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

Create a `.env` file in the project root:

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

This creates the local SQLite database and applies the project's migrations.

### 6. Start the development server

```powershell
python manage.py runserver
```

The backend runs at:

`http://127.0.0.1:8000/`

API endpoints are available under `/videos/api/`.

## Frontend Integration

The frontend is built with Next.js and runs locally at `http://localhost:3000`.

Configure the frontend's `.env.local` file with:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

The frontend uses this value as the base URL for backend API requests and resource URLs.

Django must allow requests from `http://localhost:3000` through its CORS configuration.

See the [frontend repository](https://github.com/Mehr3had/VideoPlatform-Frontend) for frontend setup instructions.

## Media Files and Local Data

Sample thumbnail images are included in the repository. Video files, uploaded profile images, and the local SQLite database are not included.

After applying migrations, create an account through the registration endpoint or create an administrator with:

```powershell
python manage.py createsuperuser
```

Upload your own video files to test video playback and media-related features.

## Security Notes

* Keep `.env` out of version control.
* Use a unique secret key.
* `DEBUG=True` is intended for local development only.
* Configure `ALLOWED_HOSTS`, HTTPS, database settings, and media storage before production deployment.
* Never publish real credentials, secret keys, or authentication tokens.

## Project Status

A full-stack learning and portfolio project focused on Django REST APIs, authentication, media handling, and integration with a Next.js frontend.

## License

No license has been specified yet.
