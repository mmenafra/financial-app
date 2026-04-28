# Finance app monorepo

- **`backend/`** – Django REST Framework API  
- **`frontend/`** – Angular 20 (CLI project name `web`)

## Stack

**Backend:** Django, Django REST Framework, django-cors-headers, PostgreSQL (Docker) or SQLite (local).

**Frontend:** Angular, TypeScript, SCSS.

**Optional:** `backend/package.json` includes `open-banking-chile` (CLI tooling); run from `backend/` with `npx` if you use it.

## Quick start (local, no Docker)

### Backend

1. Create and activate a virtual environment:
   - `cd backend`
   - `python3 -m venv .venv` (or use a venv at repo root)
   - `source .venv/bin/activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Environment: from repo root, `cp .env.example .env` (or use `backend/.env.example` as a template)
4. Migrations: `python manage.py migrate` (from `backend/` with `manage.py` in cwd)
5. Server: `python manage.py runserver`

### Frontend

```bash
cd frontend
npm ci
npx ng serve
```

App: `http://localhost:4200/`

## Run with Docker Compose (development)

1. `docker compose up --build` (or `make docker-up`)
2. **API:** `http://localhost:8000`
3. **Angular (dev):** `http://localhost:4200`
4. `docker compose down` (or `make docker-down`)

Notes:

- The **`backend`** service runs migrations on startup and mounts `./backend` for live code edits.
- The **`frontend`** service uses the `dev` image target (`ng serve` with polling); `./frontend` is bind-mounted, with `node_modules` kept in a container volume.
- PostgreSQL is used in Compose; data is stored in the `postgres_data` volume.

## Production-like stack (Django + nginx for Angular)

```bash
make docker-prod
# same as: docker compose -f docker-compose.prod.yml up --build
```

- **Static Angular UI:** `http://localhost:80` (nginx)
- **API:** `http://localhost:8000`

`docker-compose.prod.yml` is a self-contained file (avoids complex merge of dev bind-mounts) with `DJANGO_DEBUG=False` for the backend.

## Makefile commands

**Docker (dev):** `make docker-build` | `make docker-up` | `make docker-down`

**Docker (prod):** `make docker-prod`

**Backend:** `make lint` (Django `check` + ruff + flake8 + pylint) | `make fmt` (autoflake + isort + black + ruff format) | `make test` (pytest) | `make seed` (uses Compose `backend` service) | `make createsuperuser` (interactive; then open `/admin/`)

**Frontend (host):** `make fe-install` | `make fe-dev` | `make fe-build`

**Frontend quality:** `make fe-lint` (ESLint `ng lint` + Stylelint) | `make fe-test` (Vitest via `ng test`, watch) | `make fe-test-ci` (Vitest, `watch=false`) | `make fe-betterer` (incremental checks; `make fe-betterer-update` after improving results). In `frontend/`: `npm run format` / `format:check` (Prettier), `npm run lint:styles` (Stylelint), `npm run test:jest` (Jest, same `*.spec.ts` as Vitest in typical setups)

**Combined:** `make lint-all` (backend stack above + Angular lint) | `make test-all` (pytest in Docker, then Angular `test:ci`)

`npm` scripts in `frontend/`: `npm run lint` (ESLint), `npm test` / `test:ci` (experimental `@angular/build:unit-test` + Vitest), `test:jest` / `test:jest:ci` (Jest + `jest-preset-angular`), `npm run betterer` / `betterer:update`. State uses [NgRx](https://ngrx.io/) (`provideStore`, `provideEffects`, `@ngrx/entity` helper example). Betterer: [`frontend/.betterer.ts`](frontend/.betterer.ts); `@betterer/eslint` is omitted (ESLint 8 vs flat ESLint 9).

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
- Import bank statement: `POST /api/transactions/import-bank-statement/` (authenticated)
  - form-data: `file=<statement.dat>`
  - returns parsed metadata and transactions as JSON
- Import Visa Nacional (PDF): `POST /api/transactions/import-visa-national/` (authenticated)
  - form-data: `file=<statement.pdf>` (text-based PDF; Scotiabank Chile Visa Nacional layout)
  - returns JSON: `{ "transactions": [ ... ] }` — only rows from **II. DETALLE → 2.PERÍODO ACTUAL**
  - each item may include: `operation_date`, `posting_code`, `reference_code`, `description`, `amount`, optional `total_to_pay`, optional `installment` / `installment_value`

Example (after obtaining a JWT access token):

```bash
curl -sS -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/Estado-de-Cuenta-Scotiabank-Marzo-2026.pdf" \
  http://localhost:8000/api/transactions/import-visa-national/
```

Notes:
- Signup and signin return JWT `access` and `refresh` tokens.
- Forgot password returns a generic success message even if email does not exist.
- In development, reset emails are printed to the terminal (console email backend).

## Swagger Docs

- OpenAPI schema: `GET /api/schema/`
- Swagger UI: `GET /api/docs/`

Use Swagger UI to test all endpoints directly from the browser.
