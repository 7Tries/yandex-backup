"""Notifier implementations."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages via Telegram Bot API."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._client = http_client or httpx.AsyncClient(timeout=10.0)

    async def notify(self, message: str) -> None:
        try:
            r = await self._client.post(
                self._url,
                json={"chat_id": self._chat_id, "text": message, "parse_mode": "HTML"},
            )
            r.raise_for_status()
            log.debug("Telegram notification sent.")
        except Exception:
            log.exception("Failed to send Telegram notification.")

    async def aclose(self) -> None:
        await self._client.aclose()


class LogNotifier:
    """Fallback notifier that just logs messages."""

    async def notify(self, message: str) -> None:
        log.warning("[NOTIFICATION] %s", message)
