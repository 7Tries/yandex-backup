"""Fake implementations for testing — no real network or DB calls."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


class FakeYaDiskClient:
    """In-memory fake for YandexDiskClient protocol."""

    def __init__(self) -> None:
        self.files: dict[str, dict[str, Any]] = {}
        self.folders: set[str] = set()
        self.trashed: list[str] = []
        self.disk_info: dict[str, Any] = {
            "total_space": 10 * 1024**3,
            "used_space": 1 * 1024**3,
        }

    async def get_disk_info(self) -> dict[str, object]:
        return dict(self.disk_info)

    async def ensure_folder(self, path: str) -> None:
        self.folders.add(path)

    async def get_upload_url(self, remote_path: str, overwrite: bool = False) -> str:
        return f"fake://upload{remote_path}"

    async def upload_file(self, upload_url: str, data: bytes) -> None:
        # Derive the remote path from the upload URL
        path = upload_url.replace("fake://upload", "")
        name = path.split("/")[-1]
        self.files[path] = {
            "data": data,
            "size": len(data),
            "md5": hashlib.md5(data).hexdigest(),
            "name": name,
            "path": path,
            "type": "file",
            "created": datetime.now(tz=timezone.utc).isoformat(),
        }

    async def get_meta(self, remote_path: str) -> dict[str, object]:
        if remote_path not in self.files:
            raise KeyError(f"Not found: {remote_path}")
        f = self.files[remote_path]
        return {"size": f["size"], "md5": f["md5"], "name": f["name"]}

    async def list_folder(self, path: str) -> list[dict[str, object]]:
        return [
            {k: v for k, v in f.items() if k != "data"}
            for f in self.files.values()
            if f.get("type") == "file"
        ]

    async def move_to_trash(self, remote_path: str) -> None:
        self.trashed.append(remote_path)
        self.files.pop(remote_path, None)

    def add_backup(
        self,
        name: str,
        folder: str,
        created: datetime,
        size: int = 1000,
    ) -> None:
        """Helper to pre-populate the fake with a backup file."""
        data = b"x" * size
        path = f"{folder}/{name}"
        self.files[path] = {
            "data": data,
            "size": size,
            "md5": hashlib.md5(data).hexdigest(),
            "name": name,
            "path": path,
            "type": "file",
            "created": created.isoformat(),
        }


class FakeNotifier:
    """Notifier that records all messages for test assertions."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def notify(self, message: str) -> None:
        self.messages.append(message)
