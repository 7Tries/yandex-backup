"""Protocol definitions — all abstractions live here."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

# Type alias for change callbacks
ChangeCallback = Callable[[], Awaitable[None]]


@runtime_checkable
class ChangeListener(Protocol):
    """Listens for DB change notifications."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def set_on_change(self, callback: ChangeCallback) -> None: ...


@runtime_checkable
class BackupService(Protocol):
    """Creates local backup files."""

    async def create_backup(self) -> Path: ...


@runtime_checkable
class YandexDiskClient(Protocol):
    """Low-level Yandex.Disk REST client."""

    async def get_disk_info(self) -> dict[str, object]: ...

    async def ensure_folder(self, path: str) -> None: ...

    async def get_upload_url(self, remote_path: str, overwrite: bool = False) -> str: ...

    async def upload_file(self, upload_url: str, data: bytes) -> None: ...

    async def get_meta(self, remote_path: str) -> dict[str, object]: ...

    async def list_folder(self, path: str) -> list[dict[str, object]]: ...

    async def move_to_trash(self, remote_path: str) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Sends admin notifications."""

    async def notify(self, message: str) -> None: ...
