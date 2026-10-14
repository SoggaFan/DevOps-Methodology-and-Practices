.PHONY: setup run test quality security coverage migrate backup restore verify up down container-check

PYTHON ?= python3
VENV_PYTHON := .venv/bin/python
VENV_BIN := .venv/bin
BACKUP_FILE ?= backup.sql

# One-time developer setup. CI uses the same command for a clean environment.
setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt

# Loads local settings for non-container execution when .env is present.
run:
	@set -a; if [ -f .env ]; then . ./.env; fi; set +a; $(VENV_PYTHON) -m uvicorn app.main:app --reload

# Tests run against TEST_DATABASE_URL when set; otherwise they use isolated in-memory SQLite.
test:
	mkdir -p reports
	$(VENV_PYTHON) -m pytest -q --cov=app --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml --cov-fail-under=65

quality:
	$(VENV_BIN)/ruff format --check app tests
	$(VENV_BIN)/ruff check app tests

security:
	$(VENV_BIN)/bandit -q -r app

coverage:
	$(VENV_PYTHON) -m coverage report --show-missing

# Prefer Alembic after its config is added. Until then, apply the project's SQL baseline.
migrate:
	@if [ -f alembic.ini ]; then \
		$(VENV_PYTHON) -m alembic upgrade head; \
	else \
		cat sql/001_schema.sql sql/002_seed.sql | docker compose exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'; \
	fi

backup:
	docker compose exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' > "$(BACKUP_FILE)"
	@echo "Backup written to $(BACKUP_FILE)"

restore:
	@test -f "$(BACKUP_FILE)" || { echo "Backup file not found: $(BACKUP_FILE)"; exit 2; }
	cat "$(BACKUP_FILE)" | docker compose exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

verify:
	$(MAKE) quality
	$(MAKE) security
	$(MAKE) test

up:
	docker compose up --build -d

down:
	docker compose down

container-check:
	docker compose ps
	curl -fsS http://localhost:8000/health
