-- 01_notify_triggers.sql
-- Creates statement-level triggers on all existing tables in the public schema,
-- an event trigger to auto-attach them to new tables (including CREATE TABLE AS),
-- and an event trigger to notify on DROP events.
-- Run as superuser.

SET search_path = public;

-- ─── DML Trigger Function ────────────────────────────────────────────────────
-- Sends pg_notify('data_changed', ...) on any INSERT/UPDATE/DELETE/TRUNCATE
CREATE OR REPLACE FUNCTION public.notify_data_change()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
AS $$
BEGIN
  PERFORM pg_notify(
    'data_changed',
    json_build_object(
      'table', TG_TABLE_NAME,
      'op',    TG_OP
    )::text
  );
  RETURN NULL;
END;
$$;

-- ─── Attach to all existing tables in public schema ──────────────────────────
DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN
    SELECT tablename
    FROM   pg_tables
    WHERE  schemaname = 'public'
  LOOP
    EXECUTE format(
      'DROP TRIGGER IF EXISTS trg_notify_change ON public.%I;
       CREATE TRIGGER trg_notify_change
       AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
       ON public.%I
       FOR EACH STATEMENT
       EXECUTE FUNCTION public.notify_data_change();',
      tbl, tbl
    );
  END LOOP;
END;
$$;

-- ─── DDL Event Trigger Function ──────────────────────────────────────────────
-- On CREATE TABLE / CREATE TABLE AS / SELECT INTO: attaches the DML trigger automatically.
-- On ALTER TABLE / CREATE INDEX: sends a notification.
CREATE OR REPLACE FUNCTION public.notify_ddl_change()
  RETURNS event_trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
AS $$
DECLARE
  obj record;
BEGIN
  FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
    -- Attach DML trigger to newly created tables
    IF obj.command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO') AND obj.schema_name = 'public' THEN
      EXECUTE format(
        'DROP TRIGGER IF EXISTS trg_notify_change ON %s;
         CREATE TRIGGER trg_notify_change
         AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
         ON %s
         FOR EACH STATEMENT
         EXECUTE FUNCTION public.notify_data_change();',
        obj.object_identity,
        obj.object_identity
      );
    END IF;

    -- Always send a notification for tracked DDL events
    PERFORM pg_notify(
      'data_changed',
      json_build_object(
        'ddl', obj.command_tag,
        'obj', obj.object_identity
      )::text
    );
  END LOOP;
END;
$$;

-- ─── DDL Event Trigger ───────────────────────────────────────────────────────
DROP EVENT TRIGGER IF EXISTS trg_ddl_notify;
CREATE EVENT TRIGGER trg_ddl_notify
  ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO', 'ALTER TABLE', 'CREATE INDEX')
  EXECUTE FUNCTION public.notify_ddl_change();

-- ─── SQL Drop Event Trigger Function ─────────────────────────────────────────
-- Catches DROP TABLE, DROP VIEW, DROP INDEX, etc. (which do not appear in pg_event_trigger_ddl_commands)
CREATE OR REPLACE FUNCTION public.notify_sql_drop()
  RETURNS event_trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
AS $$
DECLARE
  obj record;
BEGIN
  FOR obj IN SELECT * FROM pg_event_trigger_dropped_objects() LOOP
    IF obj.schema_name = 'public' THEN
      PERFORM pg_notify(
        'data_changed',
        json_build_object(
          'ddl', 'DROP',
          'type', obj.object_type,
          'obj', obj.object_identity
        )::text
      );
    END IF;
  END LOOP;
END;
$$;

-- ─── SQL Drop Event Trigger ──────────────────────────────────────────────────
DROP EVENT TRIGGER IF EXISTS trg_sql_drop_notify;
CREATE EVENT TRIGGER trg_sql_drop_notify
  ON sql_drop
  EXECUTE FUNCTION public.notify_sql_drop();
