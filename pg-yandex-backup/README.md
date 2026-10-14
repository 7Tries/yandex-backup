# pg-yandex-backup

Automatic PostgreSQL backup to [Yandex.Disk](https://disk.yandex.com/) via LISTEN/NOTIFY + cron scheduling.

## Features

| Feature | Details |
|---|---|
| **Change detection** | `pg_notify` on every DML/DDL change in the `public` schema |
| **Debounce** | Coalesces rapid changes into one backup (configurable delay) |
| **Cron schedule** | Independent nightly backup via APScheduler (default `0 3 * * *`) |
| **Upload** | Streams `pg_dump` output, gzip-compresses, uploads to Yandex.Disk |
| **Verification** | MD5 + size checked after upload; failure triggers a notification |
| **Rotation** | Deletes backups older than `RETENTION_DAYS`, always keeping `MIN_KEEP_BACKUPS` |
| **Notifications** | Telegram Bot API or fallback to log output |
| **Reconnect** | Exponential-backoff reconnect with missed-notification backup on reconnect |
| **Restore** | Interactive CLI wizard (`pg-restore`) |

## Quick Start

```bash
# 1. Copy and edit configuration
cp .env.example .env
$EDITOR .env   # set YANDEX_TOKEN, POSTGRES_PASSWORD, TELEGRAM_TOKEN, etc.

# 2. Start everything
docker compose up -d
```

## Configuration

All settings are read from environment variables (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `postgres` | Database name |
| `POSTGRES_USER` | `backup_user` | Backup role |
| `POSTGRES_PASSWORD` | | Backup role password |
| `POSTGRES_ADMIN_USER` | `postgres` | Superuser (for init scripts) |
| `POSTGRES_ADMIN_PASSWORD` | | Superuser password |
| `YANDEX_TOKEN` | | OAuth token for Yandex.Disk |
| `YANDEX_BACKUP_FOLDER` | `/backups/pg-yandex-backup` | Remote folder path |
| `TELEGRAM_TOKEN` | | Bot token (optional) |
| `TELEGRAM_CHAT_ID` | | Chat/channel ID (optional) |
| `DEBOUNCE_SECONDS` | `60` | Wait after last change before backup |
| `BACKUP_CRON` | `0 3 * * *` | Cron schedule for nightly backup |
| `LOCAL_BACKUP_DIR` | `/backups` | Staging directory inside container |
| `RETENTION_DAYS` | `30` | Delete backups older than this |
| `MIN_KEEP_BACKUPS` | `5` | Always keep at least this many |
| `MIN_FREE_BYTES` | `524288000` | Refuse upload if less than 500 MB free |

## Architecture

```
PostgreSQL ──NOTIFY──► PgListener ──trigger──► DebounceController
                                                       │
APScheduler (cron) ─────────────────────────────────► │
                                                       ▼
                                               BackupPipeline
                                                 │   │   │
                                            pg_dump  │  Rotator
                                                     │
                                                  Uploader ──► Yandex.Disk
                                                     │
                                                 TelegramNotifier
```

## Database Setup

The init scripts run automatically when the Docker container starts.

To run manually:

```bash
export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"
psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" \
  -f sql/01_notify_triggers.sql

psql -h "$POSTGRES_HOST" -U "$POSTGRES_ADMIN_USER" -d "$POSTGRES_DB" \
  -v backup_password="$POSTGRES_PASSWORD" \
  -v dbname="$POSTGRES_DB" \
  -f sql/02_backup_role.sql
```

## Restore

```bash
# Inside the container or with the package installed
pg-restore
```

The wizard lists all available backups on Yandex.Disk and prompts for target
database connection details before restoring.

## Development

```bash
pip install -e ".[dev]"          # or: pip install -r requirements-dev.txt

# Lint
ruff check src tests
mypy src

# Tests (no PostgreSQL or Yandex.Disk required)
pytest -v

# Smoke test (requires real credentials in .env)
python scripts/smoke_test.py
```

## Yandex.Disk OAuth Token

1. Create an application at <https://oauth.yandex.com/>
2. Grant it `cloud_api:disk.write` + `cloud_api:disk.read` scopes
3. Obtain a token via the OAuth flow and set it as `YANDEX_TOKEN`

## License

MIT
