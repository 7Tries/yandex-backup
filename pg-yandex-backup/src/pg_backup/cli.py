"""CLI entry point for restore."""
from __future__ import annotations

import asyncio
import sys

from pg_backup.config import get_settings
from pg_backup.logging_setup import setup_logging
from pg_backup.restore import interactive_restore


def restore_main() -> None:
    setup_logging()
    settings = get_settings()
    try:
        asyncio.run(interactive_restore(settings))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
