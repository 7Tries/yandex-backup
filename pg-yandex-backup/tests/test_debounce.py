"""Tests for DebounceController."""
from __future__ import annotations

import asyncio

import pytest

from pg_backup.debounce import DebounceController


@pytest.mark.asyncio
async def test_debounce_fires_after_delay() -> None:
    """Backup fires exactly once after the quiet period."""
    fired: list[int] = []

    async def cb() -> None:
        fired.append(1)

    ctrl = DebounceController(delay=0.05, callback=cb)
    ctrl.trigger()
    await asyncio.sleep(0.15)
    assert len(fired) == 1


@pytest.mark.asyncio
async def test_debounce_resets_on_retrigger() -> None:
    """Re-triggering within the delay window resets the timer."""
    fired: list[int] = []

    async def cb() -> None:
        fired.append(1)

    ctrl = DebounceController(delay=0.1, callback=cb)
    ctrl.trigger()
    await asyncio.sleep(0.05)
    ctrl.trigger()  # reset — should delay another 0.1s from now
    await asyncio.sleep(0.05)
    # Not enough time has passed since the second trigger
    assert len(fired) == 0
    await asyncio.sleep(0.12)
    assert len(fired) == 1


@pytest.mark.asyncio
async def test_debounce_no_concurrent_backups() -> None:
    """At most one backup runs at a time."""
    running = [0]
    max_concurrent = [0]

    async def cb() -> None:
        running[0] += 1
        max_concurrent[0] = max(max_concurrent[0], running[0])
        await asyncio.sleep(0.1)
        running[0] -= 1

    ctrl = DebounceController(delay=0.01, callback=cb)
    ctrl.trigger()
    await asyncio.sleep(0.02)  # first backup has started
    ctrl.trigger()  # arrives during backup — must not start a second concurrent backup
    await asyncio.sleep(0.4)   # wait for both (sequential) to finish
    assert max_concurrent[0] == 1


@pytest.mark.asyncio
async def test_fire_immediately_skips_delay() -> None:
    """fire_immediately runs backup without waiting for the delay."""
    fired: list[int] = []

    async def cb() -> None:
        fired.append(1)

    ctrl = DebounceController(delay=100.0, callback=cb)
    await ctrl.fire_immediately()
    assert len(fired) == 1


@pytest.mark.asyncio
async def test_pending_backup_runs_after_current() -> None:
    """A change arriving during a backup triggers another one after it finishes."""
    order: list[str] = []

    async def cb() -> None:
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")

    ctrl = DebounceController(delay=0.01, callback=cb)
    ctrl.trigger()           # starts backup 1
    await asyncio.sleep(0.02)  # backup 1 is now running
    ctrl.trigger()           # pending; backup 2 will run after backup 1 ends
    await asyncio.sleep(0.4)   # enough time for both backups
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_stop_cancels_pending_timer() -> None:
    """stop() cancels a pending debounce timer without running the backup."""
    fired: list[int] = []

    async def cb() -> None:
        fired.append(1)

    ctrl = DebounceController(delay=1.0, callback=cb)
    ctrl.trigger()
    await ctrl.stop()
    await asyncio.sleep(0.1)
    assert len(fired) == 0
