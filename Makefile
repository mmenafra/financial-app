DC = docker compose
DC_PROD = $(DC) -f docker-compose.prod.yml
BACKEND = backend
FRONTEND = frontend

.PHONY: help docker-build docker-up docker-down docker-prod migrate \
	lint fmt test seed seed-categories format-all lint-all test-all \
	fe-install fe-dev fe-build fe-fmt fe-lint fe-test fe-test-ci fe-betterer fe-betterer-update \
	db-clean-all clean-db-all db-clean-user db-clean-transactions db-clean-user-since \
	db-backup db-restore \
	createsuperuser dump-gemini-keys

help:
	@echo "Docker (dev):  make docker-build | docker-up | docker-down | make migrate (apply DB migrations)"
	@echo "Docker (prod): make docker-prod  (Django+Postgres+nginx frontend)"
	@echo "Backend:       make lint (django check + ruff + flake8 + pylint) | fmt (autoflake + isort + black + ruff format) | test (pytest) | seed"
	@echo "               make seed-categories EMAIL=<email> (optional RESET=1 to clear user categories first)"
	@echo "               make createsuperuser (interactive; admin UI at /admin/)"
	@echo "               make dump-gemini-keys [DUMP_GEMINI_OPTS=--insecure] (plaintext keys; use --insecure when DEBUG=False)"
	@echo "DB clean:      make db-clean-all (alias: clean-db-all) | db-clean-user USER=<u> (tx, visa stmts, imports, categories, patterns) | db-clean-transactions USER=<u> | db-clean-user-since USER=<u> [FROM_DATE=...] (keeps categories only)"
	@echo "DB backup:      make db-backup  (gzip SQL under backups/; compose db service must be running)"
	@echo "DB restore:     make db-restore BACKUP=path/to/file.sql.gz  (also accepts plain .sql)"
	@echo "Frontend:      make fe-install | fe-dev | fe-build"
	@echo "               make fe-fmt (npm run format / Prettier)"
	@echo "               make fe-lint (ESLint + Stylelint) | fe-test (Vitest) | fe-test-ci (Vitest, no watch)"
	@echo "               make fe-betterer | fe-betterer-update"
	@echo "Combined:      make format-all (fmt + fe-fmt) | make lint-all (lint + fe-lint) | make test-all (test + fe-test-ci)"

docker-build:
	$(DC) build

docker-up:
	$(DC) up --build

docker-down:
	$(DC) down

migrate:
	$(DC) run --rm $(BACKEND) python manage.py migrate

docker-prod:
	$(DC_PROD) up --build

lint:
	$(DC) run --rm $(BACKEND) sh -c "python manage.py check && ruff check . && flake8 . && pylint --rcfile=/app/.pylintrc config api"

fe-lint:
	cd $(FRONTEND) && npx ng lint && npx stylelint "src/**/*.scss"

fe-fmt:
	cd $(FRONTEND) && npm run format

format-all: fmt fe-fmt

lint-all: lint fe-lint

test-all: test fe-test-ci

fmt:
	$(DC) run --rm $(BACKEND) sh -c "autoflake --in-place -r --remove-all-unused-imports --remove-unused-variables --ignore-init-module-imports . && isort . && black . && ruff format ."

test:
	$(DC) run --rm $(BACKEND) pytest

fe-test:
	cd $(FRONTEND) && npx ng test

fe-test-ci:
	cd $(FRONTEND) && npm run test:ci

fe-betterer:
	cd $(FRONTEND) && npx betterer

fe-betterer-update:
	cd $(FRONTEND) && npm run betterer:update

seed:
	$(DC) run --rm $(BACKEND) python manage.py seed_finance_data --reset

seed-categories:
	@test -n "$(EMAIL)" || (echo "Usage: make seed-categories EMAIL=<email> [RESET=1]" && exit 1)
	$(DC) run --rm $(BACKEND) python manage.py seed_categories --email "$(EMAIL)" $(if $(RESET),--reset,)

createsuperuser:
	$(DC) run --rm -it $(BACKEND) python manage.py createsuperuser

dump-gemini-keys:
	$(DC) run --rm $(BACKEND) python manage.py dump_gemini_keys $(DUMP_GEMINI_OPTS)

db-clean-all:
	$(DC) run --rm $(BACKEND) python manage.py clean_db --all

clean-db-all: db-clean-all

db-clean-user:
	@test -n "$(USER)" || (echo "Usage: make db-clean-user USER=<username>" && exit 1)
	$(DC) run --rm $(BACKEND) python manage.py clean_db --user "$(USER)"

db-clean-transactions:
	@test -n "$(USER)" || (echo "Usage: make db-clean-transactions USER=<username>" && exit 1)
	$(DC) run --rm $(BACKEND) python manage.py clean_db --transactions "$(USER)"

db-clean-user-since:
	@test -n "$(USER)" || (echo "Usage: make db-clean-user-since USER=<username> [FROM_DATE=2026-02-01]" && exit 1)
	$(DC) run --rm $(BACKEND) python manage.py clean_db --user-since "$(USER)" $(if $(FROM_DATE),--from-date "$(FROM_DATE)",)

# Full logical backup (PostgreSQL pg_dump SQL with DROP IF EXISTS prelude). Writes backups/finance_app_<timestamp>.sql.gz
db-backup:
	@mkdir -p backups
	@out=backups/finance_app_$$(date +%Y%m%d_%H%M%S).sql.gz; \
		set -e; \
		echo "Writing $$out ..."; \
		$(DC) exec -T db pg_dump -U finance_user -d finance_app --clean --if-exists | gzip > "$$out"; \
		echo "Done: $$out"

db-restore:
	@test -n "$(BACKUP)" || (echo 'Usage: make db-restore BACKUP=path/to/backup.sql.gz  (also accepts plain .sql)' && exit 1)
	@test -f "$(BACKUP)" || (echo "File not found: $(BACKUP)" && exit 1)
	case "$(BACKUP)" in \
		*.gz|*.gzip) gzip -dc "$(BACKUP)" ;; \
		*) cat "$(BACKUP)" ;; \
	esac | $(DC) exec -T db psql -U finance_user -d finance_app -v ON_ERROR_STOP=1

fe-install:
	cd $(FRONTEND) && npm ci

fe-dev:
	cd $(FRONTEND) && npx ng serve

fe-build:
	cd $(FRONTEND) && npx ng build --configuration production
