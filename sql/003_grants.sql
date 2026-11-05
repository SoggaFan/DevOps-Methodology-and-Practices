-- The app may use existing objects but must not own or alter the schema.
REVOKE CREATE ON SCHEMA public FROM fishing_app;
GRANT USAGE ON SCHEMA public TO fishing_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fishing_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fishing_app;
