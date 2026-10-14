"""Interactive restore CLI."""
from __future__ import annotations

import gzip
import logging
import os
import subprocess
import tempfile
from getpass import getpass
from pathlib import Path

import httpx

from pg_backup.config import Settings
from pg_backup.yadisk import YaDiskClient

log = logging.getLogger(__name__)


async def list_remote_backups(
    client: YaDiskClient, folder: str
) -> list[dict[str, object]]:
    items = await client.list_folder(folder)
    backups = [
        i
        for i in items
        if i.get("type") == "file" and str(i.get("name", "")).startswith("backup_")
    ]
    backups.sort(key=lambda x: str(x.get("created", "")), reverse=True)
    return backups


async def download_backup(
    client: YaDiskClient, remote_path: str, dest: Path
) -> None:
    """Download a file from Yandex.Disk to a local path."""
    meta = await client.get_meta(remote_path)
    download_url = str(meta.get("file", ""))
    if not download_url:
        # Use the download link API endpoint
        async with httpx.AsyncClient(timeout=120.0) as hc:
            r = await hc.get(
                "https://cloud-api.yandex.net/v1/disk/resources/download",
                headers={"Authorization": f"OAuth {client._token}"},
                params={"path": remote_path},
            )
            r.raise_for_status()
            download_url = str(r.json()["href"])

    async with httpx.AsyncClient(timeout=300.0) as hc:
        r = await hc.get(download_url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    print(f"Downloaded {remote_path} -> {dest}")


def restore_sql(
    sql_gz_path: Path,
    host: str,
    port: int,
    db: str,
    user: str,
    password: str,
) -> None:
    """Decompress and feed the SQL dump into psql."""
    print(
        f"Restoring {sql_gz_path} into database '{db}' "
        f"on {host}:{port} as user '{user}'..."
    )
    env = {**os.environ, "PGPASSWORD": password}
    with gzip.open(sql_gz_path, "rb") as f:
        sql = f.read()
    proc = subprocess.run(
        ["psql", "-h", host, "-p", str(port), "-U", user, "-d", db],
        input=sql,
        env=env,
        capture_output=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed with return code {proc.returncode}")
    print("Restore complete.")


async def interactive_restore(settings: Settings) -> None:
    """Interactive restore wizard."""
    token = settings.yandex_token
    folder = settings.yandex_backup_folder

    async with httpx.AsyncClient(timeout=60.0) as http:
        client = YaDiskClient(token, http)

        print("\n=== pg-yandex-backup restore ===")
        print(f"Listing backups in {folder}...\n")

        backups = await list_remote_backups(client, folder)
        if not backups:
            print("No backups found.")
            return

        for i, b in enumerate(backups, 1):
            print(
                f"  [{i}] {b['name']}  "
                f"created={b.get('created', '?')}  "
                f"size={b.get('size', '?')}"
            )

        choice_str = input("\nEnter backup number to restore (or q to quit): ").strip()
        if choice_str.lower() == "q":
            return
        try:
            choice = int(choice_str) - 1
            selected = backups[choice]
        except (ValueError, IndexError):
            print("Invalid choice.")
            return

        remote_path = str(selected.get("path", f"{folder}/{selected['name']}"))
        print(f"\nSelected: {selected['name']}")

        target_db = (
            input(
                f"Target database name [default: restore_{settings.postgres_db}]: "
            ).strip()
            or f"restore_{settings.postgres_db}"
        )

        target_host = (
            input(f"Target host [{settings.postgres_host}]: ").strip()
            or settings.postgres_host
        )
        target_port_str = input(
            f"Target port [{settings.postgres_port}]: "
        ).strip()
        target_port = int(target_port_str) if target_port_str else settings.postgres_port
        target_user = input("Target admin user [postgres]: ").strip() or "postgres"
        target_password = getpass(f"Password for {target_user}@{target_host}: ")

        print(
            f"\n⚠ This will restore into database '{target_db}' "
            f"on {target_host}:{target_port}."
        )
        confirm = input("Type 'yes' to confirm: ").strip()
        if confirm != "yes":
            print("Aborted.")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / str(selected["name"])
            await download_backup(client, remote_path, local_path)
            restore_sql(
                local_path,
                host=target_host,
                port=target_port,
                db=target_db,
                user=target_user,
                password=target_password,
            )
