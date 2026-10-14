#!/usr/bin/env python3
"""Smoke test: verifies the backup service can connect, create a backup,
upload to Yandex.Disk, verify, and rotate.

Run with real credentials (YANDEX_TOKEN, POSTGRES_* set in environment or .env):
    python scripts/smoke_test.py
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import sys
import tempfile
from pathlib import Path

import httpx

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pg_backup.config import Settings
from pg_backup.logging_setup import setup_logging
from pg_backup.notifier import LogNotifier
from pg_backup.rotation import Rotator
from pg_backup.uploader import Uploader
from pg_backup.yadisk import YaDiskClient

log = logging.getLogger("smoke_test")


async def main() -> None:
    setup_logging(logging.DEBUG)
    settings = Settings()

    if not settings.yandex_token:
        log.error("YANDEX_TOKEN is not set. Aborting smoke test.")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=120.0) as http:
        client = YaDiskClient(settings.yandex_token, http)
        notifier = LogNotifier()

        # 1. Disk info
        log.info("=== Step 1: Disk info ===")
        info = await client.get_disk_info()
        total = int(info.get("total_space", 0))
        used = int(info.get("used_space", 0))
        log.info(
            "Yandex.Disk: total=%.1f GB  used=%.1f GB  free=%.1f GB",
            total / 1e9,
            used / 1e9,
            (total - used) / 1e9,
        )

        # 2. Ensure folder
        log.info("=== Step 2: Ensure folder ===")
        folder = settings.yandex_backup_folder + "/smoke_test"
        await client.ensure_folder(folder)
        log.info("Folder ensured: %s", folder)

        # 3. Create a fake backup file
        log.info("=== Step 3: Create fake backup ===")
        with tempfile.NamedTemporaryFile(
            suffix=".sql.gz", delete=False, dir="/tmp"
        ) as f:
            with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                gz.write(b"-- smoke test backup\nSELECT 1;\n")
            fake_backup = Path(f.name)
        log.info("Fake backup: %s (%d bytes)", fake_backup, fake_backup.stat().st_size)

        # 4. Upload + verify
        log.info("=== Step 4: Upload + verify ===")
        uploader = Uploader(
            client=client,
            notifier=notifier,
            remote_folder=folder,
            min_free_bytes=1024 * 1024,  # 1 MB minimum free for smoke test
        )
        remote = await uploader.upload(fake_backup)
        log.info("Upload + verify OK: %s", remote)
        fake_backup.unlink()

        # 5. Rotation (dry run with very short retention — will delete the file we just uploaded)
        log.info("=== Step 5: Rotation (retention_days=0, min_keep=0) ===")
        rotator = Rotator(
            client=client,
            notifier=notifier,
            remote_folder=folder,
            retention_days=0,
            min_keep=0,
        )
        await rotator.rotate()
        log.info("Rotation OK.")

        log.info("=== Smoke test PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
