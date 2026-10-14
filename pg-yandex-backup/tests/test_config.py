"""Tests for configuration parsing and validators."""
from __future__ import annotations

from pg_backup.config import Settings


def test_postgres_dsn_encodes_special_characters() -> None:
    """Special characters in password and user are safely percent-encoded."""
    settings = Settings(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="mydb",
        postgres_user="user@domain",
        postgres_password="p@ss:word/special#123",
    )
    dsn = settings.postgres_dsn
    assert "user%40domain" in dsn
    assert "p%40ss%3Aword%2Fspecial%23123" in dsn


def test_yandex_backup_folder_normalizes_slashes() -> None:
    """Trailing and missing leading slashes are normalized properly."""
    s1 = Settings(yandex_backup_folder="my/backups/")
    assert s1.yandex_backup_folder == "/my/backups"

    s2 = Settings(yandex_backup_folder="/backups/pg-backup///")
    assert s2.yandex_backup_folder == "/backups/pg-backup"
