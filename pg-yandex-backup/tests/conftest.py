"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from tests.fakes import FakeNotifier, FakeYaDiskClient


@pytest.fixture
def fake_client() -> FakeYaDiskClient:
    return FakeYaDiskClient()


@pytest.fixture
def fake_notifier() -> FakeNotifier:
    return FakeNotifier()
