-- Creates/updates the least-privilege application role during first initialization.
-- This script is also safe to run explicitly against an existing Compose volume.
\getenv app_password POSTGRES_APP_PASSWORD
\getenv database_name POSTGRES_DB

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fishing_app') THEN
        EXECUTE 'CREATE ROLE fishing_app LOGIN';
    END IF;
END
$$;

ALTER ROLE fishing_app WITH LOGIN PASSWORD :'app_password';
REVOKE ALL ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO fishing_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO fishing_app;
