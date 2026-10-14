"""Tests for Uploader — upload, free-space check, md5/size verification."""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from typing import Any

import pytest

from pg_backup.uploader import Uploader
from tests.fakes import FakeNotifier, FakeYaDiskClient

FOLDER = "/backups/test"


def make_uploader(
    client: FakeYaDiskClient,
    notifier: FakeNotifier,
    min_free_bytes: int = 0,
) -> Uploader:
    return Uploader(
        client=client,
        notifier=notifier,
        remote_folder=FOLDER,
        min_free_bytes=min_free_bytes,
    )


@pytest.mark.asyncio
async def test_upload_success(
    tmp_path: Path,
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Happy path: file is uploaded and remote path is returned."""
    data = gzip.compress(b"SELECT 1;")
    f = tmp_path / "backup_20240101_120000.sql.gz"
    f.write_bytes(data)

    uploader = make_uploader(fake_client, fake_notifier)
    remote = await uploader.upload(f)

    assert remote == f"{FOLDER}/{f.name}"
    assert remote in fake_client.files


@pytest.mark.asyncio
async def test_upload_verify_md5_and_size(
    tmp_path: Path,
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Uploaded file's md5 and size match the local file."""
    data = gzip.compress(b"SELECT 2; SELECT 3;")
    f = tmp_path / "backup_20240101_130000.sql.gz"
    f.write_bytes(data)

    uploader = make_uploader(fake_client, fake_notifier)
    remote = await uploader.upload(f)

    meta = await fake_client.get_meta(remote)
    assert meta["md5"] == hashlib.md5(data).hexdigest()
    assert meta["size"] == len(data)


@pytest.mark.asyncio
async def test_upload_fails_on_insufficient_space(
    tmp_path: Path,
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Upload is rejected when free space is below minimum threshold."""
    fake_client.disk_info = {"total_space": 1000, "used_space": 999}
    data = b"x" * 500
    f = tmp_path / "backup_20240101_140000.sql.gz"
    f.write_bytes(data)

    uploader = make_uploader(fake_client, fake_notifier, min_free_bytes=1_000_000)
    with pytest.raises(RuntimeError, match="Insufficient space"):
        await uploader.upload(f)

    # A notification should have been sent
    assert any("Insufficient space" in m for m in fake_notifier.messages)


@pytest.mark.asyncio
async def test_upload_detects_md5_mismatch(
    tmp_path: Path,
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Upload raises when remote md5 does not match local md5."""
    data = b"real backup data"
    f = tmp_path / "backup_20240101_150000.sql.gz"
    f.write_bytes(data)

    # Monkey-patch get_meta to return a corrupt md5
    original_get_meta = fake_client.get_meta

    async def tampered_meta(path: str) -> dict[str, Any]:
        m = dict(await original_get_meta(path))
        m["md5"] = "deadbeef" * 4  # wrong md5
        return m

    fake_client.get_meta = tampered_meta  # type: ignore[method-assign]

    uploader = make_uploader(fake_client, fake_notifier)
    with pytest.raises(RuntimeError, match="Verification FAILED"):
        await uploader.upload(f)

    assert any("Verification FAILED" in m for m in fake_notifier.messages)


@pytest.mark.asyncio
async def test_upload_detects_size_mismatch(
    tmp_path: Path,
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Upload raises when remote size does not match local size."""
    data = b"backup data size test"
    f = tmp_path / "backup_20240101_160000.sql.gz"
    f.write_bytes(data)

    original_get_meta = fake_client.get_meta

    async def tampered_meta(path: str) -> dict[str, Any]:
        m = dict(await original_get_meta(path))
        m["size"] = int(m["size"]) + 999  # wrong size
        return m

    fake_client.get_meta = tampered_meta  # type: ignore[method-assign]

    uploader = make_uploader(fake_client, fake_notifier)
    with pytest.raises(RuntimeError, match="Verification FAILED"):
        await uploader.upload(f)
