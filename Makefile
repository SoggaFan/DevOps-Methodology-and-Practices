.PHONY: setup run test quality security coverage migrate db-bootstrap backup restore restore-new-volume verify up down container-check container-persistence-check scale-up scale-check scale-down

PYTHON ?= python3
VENV_PYTHON := .venv/bin/python
VENV_BIN := .venv/bin
BACKUP_FILE ?= backups/fishing.dump
RESTORE_PROJECT ?= fishing-restore

# One-time developer setup. CI uses the same command for a clean environment.
setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt

# Loads local settings for non-container execution when .env is present.
run:
	@set -a; if [ -f .env ]; then . ./.env; fi; set +a; $(VENV_PYTHON) -m uvicorn app.main:app --reload

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

# Idempotent helper for a pre-existing Docker volume where init SQL did not run.
db-bootstrap:
	docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /docker-entrypoint-initdb.d/000_create_app_user.sql'

# Apply the repeatable SQL baseline/seed and ensure the least-privilege app grants.
migrate:
	cat sql/001_schema.sql sql/002_seed.sql sql/003_grants.sql | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backup:
	mkdir -p "$(dir $(BACKUP_FILE))"
	docker compose exec -T db sh -c 'pg_dump --format=custom --no-owner --no-privileges -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' > "$(BACKUP_FILE)"
	@echo "Custom-format backup written to $(BACKUP_FILE)"

# Destructive recovery of the current DB requires explicit confirmation.
restore:
	@test -f "$(BACKUP_FILE)" || { echo "Backup file not found: $(BACKUP_FILE)"; exit 2; }
	@test "$(RESTORE_CONFIRM)" = "YES" || { echo "WARNING: this drops the public schema in the current Compose DB. Run: make restore RESTORE_CONFIRM=YES BACKUP_FILE=$(BACKUP_FILE)"; exit 2; }
	docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO fishing_app;"'
	docker compose exec -T db sh -c 'pg_restore --no-owner --no-privileges -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < "$(BACKUP_FILE)"
	docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /docker-entrypoint-initdb.d/003_grants.sql'

restore-new-volume: container-check
	BACKUP_FILE="$(BACKUP_FILE)" RESTORE_PROJECT="$(RESTORE_PROJECT)" bash ./scripts/restore_new_volume.sh

verify:
	$(MAKE) quality
	$(MAKE) security
	$(MAKE) test

# The policy gate runs before Compose changes the environment.
up: container-check
	docker compose up --build -d

down:
	docker compose down

# Static policy checks + checks against the running Compose services.
container-check:
	docker compose config --quiet
	$(PYTHON) scripts/container_check.py

# Interactive acceptance test; recreates db/api, proves data persistence, and checks SIGTERM.
container-persistence-check:
	$(PYTHON) scripts/container_persistence_check.py

# Optional extension: put two un-published API instances behind Nginx.
scale-up: container-check
	-docker compose stop api
	-docker compose rm -f api
	docker compose -f docker-compose.yml -f docker-compose.scale.yml --profile scale up --build -d --remove-orphans

scale-check:
	$(PYTHON) scripts/scale_check.py

scale-down: container-check
	docker compose -f docker-compose.yml -f docker-compose.scale.yml --profile scale down
	docker compose up --build -d
