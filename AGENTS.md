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
| Frontend format (Prettier) | `make fe-fmt` (or `cd frontend && npm run format`) |
| Frontend lint | `make fe-lint` |
| Frontend tests (CI-style, no watch) | `make fe-test-ci` |
| Format everything | `make format-all` (`fmt` + `fe-fmt`) |
| Lint everything | `make lint-all` |
| Test everything | `make test-all` |

Run `make help` for a full list. Agent-specific rules live in [`.cursor/rules/`](.cursor/rules/).

### Validation policy (agents and automation)

- **Once per change batch:** After substantive edits for a task are complete, run **`make format-all` once**, then **`make lint-all` once**, then **`make test-all` once** (in that order). Do **not** run full format, lint, or full tests repeatedly while still editing unrelated files, or “just to be sure” after a green run. Re-run only when fixing a failure from the last run (re-run the failed target(s) until green; you do not need to re-lint if only tests failed and lint was already clean).
- **Fix lint properly:** If lint fails, fix the code (or adjust config only when the project already does so for the same class of issue). Do **not** add `# noqa`, broad Ruff/per-file disables, ESLint disable comments, or similar **solely** to make lint pass.

## Commit message format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>
```

| Type | When to use |
|------|-------------|
| `feat` | New feature or user-visible behaviour |
| `fix` | Bug fix |
| `refactor` | Code change that is neither a feature nor a fix |
| `chore` | Tooling, config, deps, CI, seed data, non-production code |

**Scope** (optional but preferred): the affected area, e.g. `visa-nacional`, `visa-intl`, `frontend`, `transactions`, `recurring`.

**Summary**: imperative, lowercase, no trailing period. Keep it under ~72 characters.

Examples from this repo:
- `feat(visa-nacional): expose statement PDF URL and download link`
- `fix(visa-intl): recurring match, statement reuse, dashboard selection`
- `refactor(recurring): drop RecurringPattern category; recurring modal & matching`
- `chore: agent validation workflow, CLI allowlist, and category UI a11y`

## Cursor auto-run (terminal allowlist)

Cursor matches **prefixes**: a single entry `make` allows every Makefile target (`make format-all`, `make lint-all`, `make test-all`, `make docker-build`, `make fe-test-ci`, etc.).

- **IDE agent:** `~/.cursor/permissions.json` → `terminalAllowlist` (when set, it **replaces** the in-app terminal allowlist—edit the file to add or remove prefixes). This repo’s machine local file should include `make` plus any other prefixes you want (e.g. `git`, `docker`, `npx`). See [permissions.json](https://cursor.com/docs/reference/permissions).
- **Cursor CLI:** [`.cursor/cli.json`](.cursor/cli.json) in this repo allows `Shell(make)` for project sessions (merges with your global CLI config).

## Cursor Cloud specific instructions

### Services

| Service | Port | Start method |
|---------|------|--------------|
| PostgreSQL 16 | 5432 | `docker compose up db` (or full stack below) |
| Django backend | 8000 | `docker compose up backend` (runs migrations on start) |
| Angular frontend | 4200 | `docker compose up frontend` (ng serve with polling) |

Full stack: `docker compose up --build` (or `make docker-up`).

### Docker daemon

The Cloud VM runs Docker-in-Docker with `fuse-overlayfs` storage driver and `iptables-legacy`. The daemon must be started before any `make` targets that use Docker Compose:

```bash
dockerd > /tmp/dockerd.log 2>&1 &
sleep 3
```

The `/etc/docker/daemon.json` already configures `fuse-overlayfs`; do **not** pass `--storage-driver` as a flag (it conflicts with the config file).

### Node.js

Node 22 is installed via nvm. Source it before running frontend commands:

```bash
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
```

### Quick verification

```bash
curl -s http://localhost:8000/api/health/   # → {"status":"ok",...}
curl -s -o /dev/null -w "%{http_code}" http://localhost:4200/  # → 200
```

### Notes

- Backend `.env` uses `DB_ENGINE=sqlite` by default (`.env.example`); Docker Compose overrides to postgres.
- `MERCADOPAGO_ACCESS_TOKEN` and `GOOGLE_CLIENT_ID` are optional; the app works without them.
- Frontend Stylelint warnings (12) are pre-existing and non-blocking.
- `make lint` / `make fmt` / `make test` all run inside the Docker Compose `backend` service container—the Docker daemon must be running.
