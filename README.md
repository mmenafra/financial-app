# Django DRF Boilerplate API

Starter project for a Django REST Framework backend.

## Stack

- Django
- Django REST Framework
- django-cors-headers

## Quick Start

1. Create and activate a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. (Optional) add environment variables:
   - `cp .env.example .env`
4. Run migrations:
   - `python manage.py migrate`
5. Start the server:
   - `python manage.py runserver`

## Run with Docker Compose (App + PostgreSQL)

1. Build and start services:
   - `docker compose up --build`
2. Open the API at:
   - `http://localhost:8000`
3. Stop services:
   - `docker compose down`

Notes:
- The `app` service runs migrations automatically on startup.
- Docker Compose uses PostgreSQL as the main database.
- Data is persisted in the `postgres_data` Docker volume.

## Makefile Commands

- `make docker-build` - build Docker images.
- `make docker-up` - start app and database with Docker Compose.
- `make docker-down` - stop Docker Compose services.
- `make lint` - run Django checks and Ruff lint.
- `make fmt` - run Ruff formatter.
- `make test` - run Django tests.

## API Endpoint

- Health check: `GET /api/health/`

## Authentication Endpoints

- Signup: `POST /api/auth/signup/`
  - body: `{"username":"john","email":"john@example.com","password":"StrongPass123!"}`
- Signin: `POST /api/auth/signin/`
  - body: `{"username":"john","password":"StrongPass123!"}`
- Forgot password: `POST /api/auth/forgot-password/`
  - body: `{"email":"john@example.com"}`
- Reset password: `POST /api/auth/reset-password/`
  - body: `{"uid":"<uid>","token":"<token>","new_password":"NewStrongPass123!"}`

Notes:
- Signup and signin return JWT `access` and `refresh` tokens.
- Forgot password returns a generic success message even if email does not exist.
- In development, reset emails are printed to the terminal (console email backend).

## Swagger Docs

- OpenAPI schema: `GET /api/schema/`
- Swagger UI: `GET /api/docs/`

Use Swagger UI to test all endpoints directly from the browser.
