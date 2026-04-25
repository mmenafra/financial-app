# AGENTS

Orientation for this repo. Full setup, Docker, and production notes: [README.md](README.md).

## Layout

- **`backend/`** – Django + Django REST Framework API (`manage.py` lives here).
- **`frontend/`** – Angular app (CLI project `web`).

## Check changes

From the repo root, prefer [Makefile](Makefile) targets (requires Docker for backend `lint` / `test` / `fmt` as wired today):

| Goal | Command |
|------|---------|
| Backend lint | `make lint` |
| Backend format | `make fmt` |
| Backend tests | `make test` |
| Frontend lint | `make fe-lint` |
| Frontend tests (CI-style, no watch) | `make fe-test-ci` |
| Everything | `make lint-all` / `make test-all` |

Run `make help` for a full list. Agent-specific rules live in [`.cursor/rules/`](.cursor/rules/).
