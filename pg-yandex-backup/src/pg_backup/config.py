"""Application configuration via pydantic-settings."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "postgres"
    postgres_user: str = "backup_user"
    postgres_password: str = ""
    postgres_admin_user: str = "postgres"
    postgres_admin_password: str = ""

    # Yandex.Disk
    yandex_token: str = ""
    yandex_backup_folder: str = "/backups/pg-yandex-backup"

    # Telegram
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # Backup settings
    debounce_seconds: int = 60
    backup_cron: str = "0 3 * * *"
    local_backup_dir: str = "/backups"
    retention_days: int = 30
    min_keep_backups: int = 5
    min_free_bytes: int = 524_288_000  # 500 MB

    @field_validator("debounce_seconds", "retention_days", "min_keep_backups", mode="before")
    @classmethod
    def must_be_positive(cls, v: object) -> object:
        if isinstance(v, (int, str)) and int(v) <= 0:
            raise ValueError("must be positive")
        return v

    @field_validator("yandex_backup_folder")
    @classmethod
    def normalize_folder(cls, v: str) -> str:
        cleaned = v.strip().rstrip("/")
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        return cleaned

    @property
    def postgres_dsn(self) -> str:
        from urllib.parse import quote_plus

        encoded_user = quote_plus(self.postgres_user)
        encoded_pass = quote_plus(self.postgres_password)
        return (
            f"postgresql://{encoded_user}:{encoded_pass}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_admin_dsn(self) -> str:
        from urllib.parse import quote_plus

        encoded_admin = quote_plus(self.postgres_admin_user)
        encoded_pass = quote_plus(self.postgres_admin_password)
        return (
            f"postgresql://{encoded_admin}:{encoded_pass}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
