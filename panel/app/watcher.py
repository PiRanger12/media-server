"""Escaneo automático: vigila videos/ y music/ y, tras unos segundos sin cambios, avisa a Jellyfin/Navidrome."""
import asyncio
import logging

from watchfiles import awatch

from . import scanners
from .config import settings

log = logging.getLogger("panel.watcher")
DEBOUNCE_MS = 15_000  # espera 15 s de calma antes de escanear (subidas grandes generan muchos eventos)


async def watch_library(library: str) -> None:
    root = settings.library_root(library)
    root.mkdir(parents=True, exist_ok=True)
    log.info("Vigilando %s", root)
    async for changes in awatch(root, debounce=DEBOUNCE_MS, recursive=True, force_polling=False):
        relevant = [p for _, p in changes if not p.rsplit("/", 1)[-1].startswith(".")]
        if relevant:
            log.info("%d cambios en %s → escaneando", len(relevant), library)
            await scanners.scan(library)


def start(loop_tasks: list) -> None:
    if not settings.watch_enabled:
        return
    for lib in ("videos", "music"):
        loop_tasks.append(asyncio.create_task(watch_library(lib)))
