#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
\getenv migrate_password OPS_MIGRATION_PASSWORD
\getenv app_password OPS_DB_PASSWORD
SELECT format('CREATE ROLE ops_migrator LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'migrate_password') \gexec
SELECT format('CREATE ROLE ops_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'app_password') \gexec
CREATE EXTENSION IF NOT EXISTS vector;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO ops_migrator;
GRANT USAGE ON SCHEMA public TO ops_app;
SQL
