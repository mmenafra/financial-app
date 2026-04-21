DC = docker compose
APP = app

.PHONY: help docker-build docker-up docker-down lint fmt test

help:
	@echo "Available targets:"
	@echo "  make docker-build  - Build app Docker image"
	@echo "  make docker-up     - Start app + postgres services"
	@echo "  make docker-down   - Stop services"
	@echo "  make lint          - Run Django checks and Ruff lint"
	@echo "  make fmt           - Run Ruff formatter"
	@echo "  make test          - Run Django test suite"

docker-build:
	$(DC) build

docker-up:
	$(DC) up --build

docker-down:
	$(DC) down

lint:
	$(DC) run --rm $(APP) sh -c "python manage.py check && ruff check ."

fmt:
	$(DC) run --rm $(APP) ruff format .

test:
	$(DC) run --rm $(APP) python manage.py test
