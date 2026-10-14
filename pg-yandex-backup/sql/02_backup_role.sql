-- 02_backup_role.sql
-- Creates (or updates) the read-only backup role.
-- Run as superuser. Pass -v backup_password='...' -v dbname='...' to psql.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backup_user') THEN
    -- Create role with password from psql variable
    EXECUTE format(
      'CREATE ROLE backup_user WITH LOGIN PASSWORD %L',
      :'backup_password'
    );
    RAISE NOTICE 'Created role backup_user';
  ELSE
    EXECUTE format(
      'ALTER ROLE backup_user WITH PASSWORD %L',
      :'backup_password'
    );
    RAISE NOTICE 'Updated password for backup_user';
  END IF;
END;
$$;

-- Grant read-only access to all existing and future tables/sequences/functions
-- pg_read_all_data is a built-in role in PostgreSQL 14+ that grants SELECT on
-- all tables including those created after this script runs.
GRANT pg_read_all_data TO backup_user;

-- Allow connecting to the target database
GRANT CONNECT ON DATABASE :"dbname" TO backup_user;

-- Note: LISTEN is allowed to any connected user by default in PostgreSQL.
-- The backup_user does NOT need any write privileges.
-- The notify_data_change() and notify_ddl_change() functions use SECURITY DEFINER
-- so they run as the superuser who created them.
