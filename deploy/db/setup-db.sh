#!/usr/bin/env bash
set -euo pipefail

DB_NAME=fishing
DB_USER=fishing_app
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./deploy/db/setup-db.sh"
  exit 1
fi

apt-get update
apt-get install -y postgresql postgresql-client ufw

systemctl enable --now postgresql

read -r -s -p "Password for PostgreSQL role ${DB_USER}: " DB_PASSWORD
echo

runuser -u postgres -- psql -v ON_ERROR_STOP=1 -v db_password="$DB_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fishing_app') THEN
    CREATE ROLE fishing_app LOGIN;
  END IF;
END
$$;
ALTER ROLE fishing_app PASSWORD :'db_password';

SELECT 'CREATE DATABASE fishing' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'fishing')\gexec
SQL

runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
REVOKE ALL ON DATABASE "$DB_NAME" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE "$DB_NAME" TO "$DB_USER";
GRANT USAGE ON SCHEMA public TO "$DB_USER";
SQL
runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$PROJECT_DIR/sql/001_schema.sql"
runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$PROJECT_DIR/sql/002_seed.sql"
runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$DB_USER";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fishing_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fishing_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO fishing_app;
SQL

unset DB_PASSWORD

echo "Database and application role are ready."
