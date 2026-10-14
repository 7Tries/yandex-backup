-- 01_notify_triggers.sql
-- Creates statement-level triggers on all existing tables in the public schema
-- and an event trigger to auto-attach them to new tables.
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
-- On CREATE TABLE: attaches the DML trigger automatically.
-- On ALTER TABLE / DROP TABLE: sends a notification.
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
    IF obj.command_tag = 'CREATE TABLE' AND obj.schema_name = 'public' THEN
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

-- ─── Event Trigger ───────────────────────────────────────────────────────────
DROP EVENT TRIGGER IF EXISTS trg_ddl_notify;
CREATE EVENT TRIGGER trg_ddl_notify
  ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'ALTER TABLE', 'DROP TABLE')
  EXECUTE FUNCTION public.notify_ddl_change();
