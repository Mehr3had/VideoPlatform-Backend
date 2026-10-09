# VideoPlatform — Frontend

A video-sharing platform frontend built with **Next.js, React, and TypeScript**, integrated with a Django REST API backend.

## Features

* **Authentication:** User registration and login with JWT-based authentication.
* **Video browsing:** Browse videos, search content, filter by category, and explore trending videos.
* **Video playback:** Watch videos and interact through likes, dislikes, and comments.
* **User profiles:** View user profiles, browse uploaded videos, and manage subscriptions.
* **Creator dashboard:** Upload videos, edit existing videos, and manage uploaded content.
* **Account settings:** Update profile information and manage account credentials.
* **Responsive interface:** A component-based UI designed for a video-sharing experience.

## Tech Stack

* Next.js (App Router)
* React
* TypeScript
* Tailwind CSS
* Django REST Framework
* JWT authentication

## Related Repository

* **Backend:** [VideoPlatform-Backend](https://github.com/Mehr3had/VideoPlatform-Backend)

## Prerequisites

Make sure the following tools are installed:

* Node.js and npm
* Git
* The [VideoPlatform backend](https://github.com/Mehr3had/VideoPlatform-Backend), running locally

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Mehr3had/VideoPlatform-Frontend.git
cd VideoPlatform-Frontend
```

### 2. Install dependencies

```bash
npm install
```

### 3. Configure environment variables

Create a `.env.local` file in the project root:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

This variable defines the base URL of the Django backend. Update it if the backend runs at a different address.

The frontend uses this variable to construct API endpoints and backend resource URLs.

**Security note:** Variables prefixed with `NEXT_PUBLIC_` can be exposed to the browser. Never store passwords, secret keys, or private credentials in them.

### 4. Start the backend

Follow the setup instructions in the [backend repository](https://github.com/Mehr3had/VideoPlatform-Backend).

Make sure the Django database migrations have been applied and the backend is running at `http://127.0.0.1:8000`.

### 5. Start the frontend

```bash
npm run dev
```

Open http://localhost:3000 in your browser.

Make sure Django allows requests from `http://localhost:3000` through its CORS configuration.

**Note:** The local database and uploaded video files are not included in this repository. You may need to create an account and upload sample videos to test all features.

## Production Build

To create an optimized production build:

```bash
npm run build
```

To run the production build locally:

```bash
npm run start
```

## Project Structure

```text
src/
├── app/
│   ├── dashboard/
│   │   ├── edit/[id]/
│   │   └── upload/
│   ├── login/
│   ├── profile/
│   │   ├── [id]/
│   │   └── edit/
│   ├── register/
│   ├── settings/
│   └── videos/[id]/
├── components/
│   └── Navbar.tsx
└── lib/
    └── api.ts
```

## Backend Integration

The frontend communicates with a Django REST API. The API base URL is configured through `NEXT_PUBLIC_API_URL` and centralized in `src/lib/api.ts`.

For local development, the backend and frontend typically run on ports `8000` and `3000`, respectively. The backend must be running for API-dependent features to work.

## Status

This project is a full-stack learning and portfolio project and is under development.

## License

No license has been specified yet.
