"""Yandex.Disk REST API client."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://cloud-api.yandex.net/v1/disk"


class YaDiskClient:
    """Thin async wrapper around Yandex.Disk REST API."""

    def __init__(self, token: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._headers = {"Authorization": f"OAuth {token}"}
        self._client = http_client or httpx.AsyncClient(timeout=60.0)

    async def get_disk_info(self) -> dict[str, object]:
        r = await self._client.get(BASE_URL, headers=self._headers)
        r.raise_for_status()
        data: dict[str, object] = r.json()
        return data

    async def ensure_folder(self, path: str) -> None:
        """Create folder (and parents) if it doesn't exist."""
        parts = [p for p in path.strip("/").split("/") if p]
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            r = await self._client.put(
                f"{BASE_URL}/resources",
                headers=self._headers,
                params={"path": current},
            )
            if r.status_code not in (201, 409):  # 409 = already exists
                r.raise_for_status()

    async def get_upload_url(self, remote_path: str, overwrite: bool = False) -> str:
        r = await self._client.get(
            f"{BASE_URL}/resources/upload",
            headers=self._headers,
            params={"path": remote_path, "overwrite": str(overwrite).lower()},
        )
        r.raise_for_status()
        return str(r.json()["href"])

    async def upload_file(self, upload_url: str, data: bytes) -> None:
        r = await self._client.put(upload_url, content=data)
        r.raise_for_status()

    async def get_meta(self, remote_path: str) -> dict[str, object]:
        r = await self._client.get(
            f"{BASE_URL}/resources",
            headers=self._headers,
            params={"path": remote_path, "fields": "size,md5,name,created,modified,file"},
        )
        r.raise_for_status()
        data: dict[str, object] = r.json()
        return data

    async def list_folder(self, path: str) -> list[dict[str, object]]:
        r = await self._client.get(
            f"{BASE_URL}/resources",
            headers=self._headers,
            params={"path": path, "limit": 1000, "fields": "_embedded.items"},
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        resp_data = r.json()
        if "_embedded" in resp_data and "items" in resp_data["_embedded"]:
            items: list[dict[str, object]] = resp_data["_embedded"]["items"]
            return items
        return []

    async def move_to_trash(self, remote_path: str) -> None:
        r = await self._client.delete(
            f"{BASE_URL}/resources",
            headers=self._headers,
            params={"path": remote_path, "permanently": "false"},
        )
        # 204 No Content, 202 Accepted, 200 OK, 404 Not Found (already deleted)
        if r.status_code not in (200, 202, 204, 404):
            r.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
