-- 02_backup_role.sql
-- Creates (or updates) the read-only backup role.
-- Run as superuser. Pass -v backup_password='...' -v dbname='...' to psql.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backup_user') THEN
    CREATE ROLE backup_user WITH LOGIN;
    RAISE NOTICE 'Created role backup_user';
  END IF;
END;
$$;

-- Set or update password outside DO block so psql variables are correctly expanded
ALTER ROLE backup_user WITH PASSWORD :'backup_password';

-- Grant read-only access to all existing and future tables/sequences/functions
-- pg_read_all_data is a built-in role in PostgreSQL 14+ that grants SELECT on
-- all tables including those created after this script runs.
GRANT pg_read_all_data TO backup_user;

-- Allow connecting to the target database
GRANT CONNECT ON DATABASE :"dbname" TO backup_user;
