"""Tests for PgListener reconnect behaviour (using a fake connection factory)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pg_backup.config import Settings
from pg_backup.listener import PgListener


class FakeNotify:
    def __init__(self, payload: str = "") -> None:
        self.payload = payload


async def make_fake_notifies(
    payloads: list[str],
    then_raise: Exception | None = None,
) -> AsyncIterator[FakeNotify]:
    for p in payloads:
        yield FakeNotify(p)
    if then_raise is not None:
        raise then_raise


def make_settings() -> Settings:
    return Settings(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="test",
        postgres_user="test",
        postgres_password="test",
    )


@pytest.mark.asyncio
async def test_listener_calls_on_change_for_each_notify() -> None:
    changes: list[str] = []

    async def on_change() -> None:
        changes.append("change")

    settings = make_settings()
    listener = PgListener(settings=settings, on_change=on_change)
    listener.set_on_change(on_change)

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.notifies = MagicMock(
        return_value=make_fake_notifies(["payload1", "payload2"])
    )
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("psycopg.AsyncConnection.connect", return_value=mock_conn):
        await listener.start()
        await asyncio.sleep(0.1)
        await listener.stop()

    assert len(changes) >= 2


@pytest.mark.asyncio
async def test_listener_reconnects_after_disconnect() -> None:
    """Verify that the listener reconnects and calls on_reconnect."""
    reconnect_calls: list[int] = []
    disconnect_calls: list[str] = []

    async def on_change() -> None:
        pass

    async def on_reconnect() -> None:
        reconnect_calls.append(1)

    async def on_disconnect(exc: Exception) -> None:
        disconnect_calls.append(str(exc))

    settings = make_settings()
    listener = PgListener(
        settings=settings,
        on_change=on_change,
        on_reconnect=on_reconnect,
        on_disconnect=on_disconnect,
    )

    call_count = [0]
    stop_event = asyncio.Event()

    async def notifies_gen() -> AsyncIterator[FakeNotify]:
        call_count[0] += 1
        if call_count[0] == 1:
            # First connection: raise immediately to trigger reconnect
            raise ConnectionError("simulated disconnect")
        # Second connection: signal stop then yield nothing
        stop_event.set()
        return
        yield  # make it an async generator

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    def make_notifies() -> AsyncIterator[FakeNotify]:
        return notifies_gen()

    mock_conn.notifies = make_notifies

    with (
        patch("psycopg.AsyncConnection.connect", return_value=mock_conn),
        patch("pg_backup.listener.INITIAL_BACKOFF", 0.01),
    ):
        await listener.start()
        # Wait until the second connection is established
        await asyncio.wait_for(stop_event.wait(), timeout=3.0)
        await listener.stop()

    assert len(disconnect_calls) >= 1
    # on_reconnect is called on the second (and subsequent) connections
    assert len(reconnect_calls) >= 1
