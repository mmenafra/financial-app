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

### Validation policy (agents and automation)

- **Once per change batch:** After substantive edits for a task are complete, run **`make lint-all` once**, then **`make test-all` once** (in that order). Do **not** run full lint or full tests repeatedly while still editing unrelated files, or “just to be sure” after a green run. Re-run only when fixing a failure from the last run (re-run the failed target(s) until green; you do not need to re-lint if only tests failed and lint was already clean).
- **Fix lint properly:** If lint fails, fix the code (or adjust config only when the project already does so for the same class of issue). Do **not** add `# noqa`, broad Ruff/per-file disables, ESLint disable comments, or similar **solely** to make lint pass.

## Cursor auto-run (terminal allowlist)

Cursor matches **prefixes**: a single entry `make` allows every Makefile target (`make lint-all`, `make docker-build`, `make fe-test-ci`, etc.).

- **IDE agent:** `~/.cursor/permissions.json` → `terminalAllowlist` (when set, it **replaces** the in-app terminal allowlist—edit the file to add or remove prefixes). This repo’s machine local file should include `make` plus any other prefixes you want (e.g. `git`, `docker`, `npx`). See [permissions.json](https://cursor.com/docs/reference/permissions).
- **Cursor CLI:** [`.cursor/cli.json`](.cursor/cli.json) in this repo allows `Shell(make)` for project sessions (merges with your global CLI config).
