DC = docker compose
DC_PROD = $(DC) -f docker-compose.prod.yml
BACKEND = backend
FRONTEND = frontend

.PHONY: help docker-build docker-up docker-down docker-prod \
	lint fmt test seed lint-all test-all \
	fe-install fe-dev fe-build fe-lint fe-test fe-test-ci fe-betterer fe-betterer-update

help:
	@echo "Docker (dev):  make docker-build | docker-up | docker-down"
	@echo "Docker (prod): make docker-prod  (Django+Postgres+nginx frontend)"
	@echo "Backend:       make lint (django check + ruff + flake8 + pylint) | fmt (autoflake + isort + black + ruff format) | test (pytest) | seed"
	@echo "Frontend:      make fe-install | fe-dev | fe-build"
	@echo "               make fe-lint (ESLint + Stylelint) | fe-test (Vitest) | fe-test-ci (Vitest, no watch)"
	@echo "               make fe-betterer | fe-betterer-update"
	@echo "Combined:      make lint-all (lint + fe-lint) | make test-all (test + fe-test-ci)"

docker-build:
	$(DC) build

docker-up:
	$(DC) up --build

docker-down:
	$(DC) down

docker-prod:
	$(DC_PROD) up --build

lint:
	$(DC) run --rm $(BACKEND) sh -c "python manage.py check && ruff check . && flake8 . && pylint --rcfile=/app/.pylintrc config api"

fe-lint:
	cd $(FRONTEND) && npx ng lint && npx stylelint "src/**/*.scss"

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

fe-install:
	cd $(FRONTEND) && npm ci

fe-dev:
	cd $(FRONTEND) && npx ng serve

fe-build:
	cd $(FRONTEND) && npx ng build --configuration production
