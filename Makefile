DC = docker compose
DC_PROD = $(DC) -f docker-compose.prod.yml
BACKEND = backend
FRONTEND = frontend

.PHONY: help docker-build docker-up docker-down docker-prod \
	lint fmt test seed fe-install fe-dev fe-build

help:
	@echo "Docker (dev):  make docker-build | docker-up | docker-down"
	@echo "Docker (prod): make docker-prod  (Django+Postgres+nginx frontend)"
	@echo "Backend:       make lint | fmt | test | seed"
	@echo "Frontend:      make fe-install | fe-dev | fe-build"

docker-build:
	$(DC) build

docker-up:
	$(DC) up --build

docker-down:
	$(DC) down

docker-prod:
	$(DC_PROD) up --build

lint:
	$(DC) run --rm $(BACKEND) sh -c "python manage.py check && ruff check ."

fmt:
	$(DC) run --rm $(BACKEND) ruff format .

test:
	$(DC) run --rm $(BACKEND) python manage.py test

seed:
	$(DC) run --rm $(BACKEND) python manage.py seed_finance_data --reset

fe-install:
	cd $(FRONTEND) && npm ci

fe-dev:
	cd $(FRONTEND) && npx ng serve

fe-build:
	cd $(FRONTEND) && npx ng build --configuration production
