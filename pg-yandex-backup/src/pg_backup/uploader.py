"""Upload logic: free-space check, upload, verify."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

from pg_backup.interfaces import Notifier, YandexDiskClient

log = logging.getLogger(__name__)

MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0


def _to_int(val: object, default: int = 0) -> int:
    if val is None:
        return default
    if isinstance(val, int):
        return val
    try:
        return int(str(val))
    except (ValueError, TypeError):
        return default


class Uploader:
    """Uploads a local file to Yandex.Disk with verification."""

    def __init__(
        self,
        client: YandexDiskClient,
        notifier: Notifier,
        remote_folder: str,
        min_free_bytes: int,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._remote_folder = remote_folder
        self._min_free_bytes = min_free_bytes

    async def upload(self, local_path: Path) -> str:
        """Upload file; return remote path. Raises on failure."""
        await self._check_free_space(local_path)
        await self._client.ensure_folder(self._remote_folder)

        remote_path = f"{self._remote_folder}/{local_path.name}"
        data = local_path.read_bytes()
        local_md5 = hashlib.md5(data).hexdigest()
        local_size = len(data)

        log.info("Uploading %s to %s", local_path.name, remote_path)
        await self._upload_with_retry(remote_path, data)

        # Verify
        meta = await self._client.get_meta(remote_path)
        remote_md5 = str(meta.get("md5", ""))
        remote_size = _to_int(meta.get("size", -1), -1)

        if remote_md5 != local_md5 or remote_size != local_size:
            msg = (
                f"Verification FAILED for {local_path.name}: "
                f"local_md5={local_md5} remote_md5={remote_md5} "
                f"local_size={local_size} remote_size={remote_size}"
            )
            log.error(msg)
            await self._notifier.notify(f"⚠️ {msg}")
            raise RuntimeError(msg)

        log.info("Verified: %s md5=%s size=%d", local_path.name, remote_md5, remote_size)
        return remote_path

    async def _check_free_space(self, local_path: Path) -> None:
        info = await self._client.get_disk_info()
        total = _to_int(info.get("total_space", 0))
        used = _to_int(info.get("used_space", 0))
        trash = _to_int(info.get("trash_size", 0))
        free = total - used - trash
        needed = local_path.stat().st_size
        if free - needed < self._min_free_bytes:
            msg = (
                f"Insufficient space on Yandex.Disk: "
                f"free={free} needed={needed} min_free={self._min_free_bytes} "
                f"(total={total}, used={used}, trash={trash})"
            )
            log.error(msg)
            await self._notifier.notify(f"⚠️ {msg}")
            raise RuntimeError(msg)

    async def _upload_with_retry(self, remote_path: str, data: bytes) -> None:
        backoff = INITIAL_BACKOFF
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                url = await self._client.get_upload_url(remote_path, overwrite=False)
                await self._client.upload_file(url, data)
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    msg = (
                        f"Rate limited by Yandex.Disk (attempt {attempt}). "
                        f"Pausing {backoff}s."
                    )
                    log.warning(msg)
                    await self._notifier.notify(f"⏸ {msg}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 120.0)
                    last_exc = exc
                    continue
                raise
            except Exception as exc:
                log.warning("Upload attempt %d failed: %s", attempt, exc)
                last_exc = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 120.0)

        raise RuntimeError(f"Upload failed after {MAX_RETRIES} attempts") from last_exc
