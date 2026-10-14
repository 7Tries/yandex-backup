"""Tests for Rotator — rotation logic with min_keep and prefix filter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pg_backup.rotation import Rotator
from tests.fakes import FakeNotifier, FakeYaDiskClient

FOLDER = "/backups/test"
NOW = datetime.now(tz=timezone.utc)


def make_rotator(
    client: FakeYaDiskClient,
    notifier: FakeNotifier,
    retention_days: int = 7,
    min_keep: int = 3,
) -> Rotator:
    return Rotator(
        client=client,
        notifier=notifier,
        remote_folder=FOLDER,
        retention_days=retention_days,
        min_keep=min_keep,
    )


@pytest.mark.asyncio
async def test_rotation_does_not_delete_recent(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Files within retention window are never deleted."""
    for i in range(5):
        fake_client.add_backup(
            f"backup_{i:02d}.sql.gz",
            FOLDER,
            created=NOW - timedelta(days=i),
        )
    rotator = make_rotator(fake_client, fake_notifier, retention_days=30, min_keep=3)
    await rotator.rotate()
    assert len(fake_client.trashed) == 0


@pytest.mark.asyncio
async def test_rotation_deletes_old_beyond_min_keep(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Old backups beyond min_keep are deleted."""
    # 3 recent backups (kept by min_keep)
    for i in range(3):
        fake_client.add_backup(
            f"backup_new_{i}.sql.gz", FOLDER, created=NOW - timedelta(days=i)
        )
    # 3 old backups (should be deleted)
    for i in range(3):
        fake_client.add_backup(
            f"backup_old_{i}.sql.gz", FOLDER, created=NOW - timedelta(days=30 + i)
        )
    rotator = make_rotator(fake_client, fake_notifier, retention_days=7, min_keep=3)
    await rotator.rotate()
    assert len(fake_client.trashed) == 3
    # The trashed files should all be the "old" ones
    trashed_names = {t.split("/")[-1] for t in fake_client.trashed}
    for i in range(3):
        assert f"backup_old_{i}.sql.gz" in trashed_names


@pytest.mark.asyncio
async def test_rotation_keeps_at_least_min_keep(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Even when all backups are old, the K most recent are never deleted."""
    # 5 old backups — all beyond retention
    for i in range(5):
        fake_client.add_backup(
            f"backup_{i:02d}.sql.gz",
            FOLDER,
            created=NOW - timedelta(days=60 + i),  # oldest has highest index
        )
    rotator = make_rotator(fake_client, fake_notifier, retention_days=7, min_keep=3)
    await rotator.rotate()
    # 5 total, keep 3 most recent, delete 2
    assert len(fake_client.trashed) == 2
    # The 3 most recent (index 0, 1, 2 — smallest days-ago) must survive
    remaining_names = {v["name"] for v in fake_client.files.values()}
    assert "backup_00.sql.gz" in remaining_names
    assert "backup_01.sql.gz" in remaining_names
    assert "backup_02.sql.gz" in remaining_names


@pytest.mark.asyncio
async def test_rotation_does_not_touch_foreign_files(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """Files without the backup_ prefix are never touched."""
    # Add one old backup that should be rotated
    fake_client.add_backup(
        "backup_old.sql.gz", FOLDER, created=NOW - timedelta(days=60)
    )
    # Add a foreign file (no backup_ prefix)
    fake_client.files[f"{FOLDER}/important.txt"] = {
        "name": "important.txt",
        "path": f"{FOLDER}/important.txt",
        "type": "file",
        "size": 100,
        "md5": "abc123",
        "created": (NOW - timedelta(days=60)).isoformat(),
    }
    rotator = make_rotator(fake_client, fake_notifier, retention_days=7, min_keep=0)
    await rotator.rotate()

    # Foreign file must still exist
    assert f"{FOLDER}/important.txt" in fake_client.files
    assert f"{FOLDER}/important.txt" not in fake_client.trashed


@pytest.mark.asyncio
async def test_rotation_notifies_on_deletion(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """A notification is sent when files are rotated."""
    for i in range(4):
        fake_client.add_backup(
            f"backup_{i:02d}.sql.gz",
            FOLDER,
            created=NOW - timedelta(days=60 + i),
        )
    rotator = make_rotator(fake_client, fake_notifier, retention_days=7, min_keep=2)
    await rotator.rotate()
    assert len(fake_client.trashed) == 2
    assert any("Rotation" in m for m in fake_notifier.messages)


@pytest.mark.asyncio
async def test_rotation_does_nothing_below_min_keep(
    fake_client: FakeYaDiskClient,
    fake_notifier: FakeNotifier,
) -> None:
    """When count <= min_keep, nothing is deleted regardless of age."""
    for i in range(3):
        fake_client.add_backup(
            f"backup_{i:02d}.sql.gz",
            FOLDER,
            created=NOW - timedelta(days=100 + i),
        )
    rotator = make_rotator(fake_client, fake_notifier, retention_days=7, min_keep=3)
    await rotator.rotate()
    assert len(fake_client.trashed) == 0
