"""Integración con Jellyfin y Navidrome: estado y escaneo de bibliotecas."""
import asyncio
import hashlib
import logging
import secrets
import time

import httpx

from .config import settings

log = logging.getLogger("panel.scan")

last_scan: dict[str, dict] = {
    "videos": {"at": None, "ok": None, "detail": "Sin escaneos todavía"},
    "music": {"at": None, "ok": None, "detail": "Sin escaneos todavía"},
}


def _subsonic_params() -> dict:
    salt = secrets.token_hex(6)
    token = hashlib.md5((settings.navidrome_password + salt).encode()).hexdigest()
    return {"u": settings.navidrome_user, "t": token, "s": salt, "v": "1.16.1", "c": "media-panel", "f": "json"}


def _jellyfin_headers() -> dict:
    return {"Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"'}


async def scan_jellyfin() -> tuple[bool, str]:
    if not settings.jellyfin_api_key:
        return False, "Falta JELLYFIN_API_KEY en .env"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{settings.jellyfin_url}/Library/Refresh", headers=_jellyfin_headers())
        if r.status_code in (200, 204):
            return True, "Escaneo de Jellyfin iniciado"
        return False, f"Jellyfin respondió {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"No se pudo contactar a Jellyfin: {exc.__class__.__name__}"


async def scan_navidrome() -> tuple[bool, str]:
    if not settings.navidrome_password:
        return False, "Falta NAVIDROME_PASSWORD en .env"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{settings.navidrome_url}/rest/startScan", params=_subsonic_params())
        body = r.json().get("subsonic-response", {})
        if body.get("status") == "ok":
            return True, "Escaneo de Navidrome iniciado"
        return False, body.get("error", {}).get("message", f"Navidrome respondió {r.status_code}")
    except (httpx.HTTPError, ValueError) as exc:
        return False, f"No se pudo contactar a Navidrome: {exc.__class__.__name__}"


async def scan(library: str) -> dict:
    ok, detail = await (scan_jellyfin() if library == "videos" else scan_navidrome())
    last_scan[library] = {"at": time.time(), "ok": ok, "detail": detail}
    (log.info if ok else log.warning)("scan %s: %s", library, detail)
    return last_scan[library]


async def status() -> dict:
    async def jellyfin():
        try:
            async with httpx.AsyncClient(timeout=4) as c:
                r = await c.get(f"{settings.jellyfin_url}/System/Info/Public")
            return {"online": r.status_code == 200, "version": r.json().get("Version") if r.status_code == 200 else None}
        except (httpx.HTTPError, ValueError):
            return {"online": False, "version": None}

    async def navidrome():
        try:
            async with httpx.AsyncClient(timeout=4) as c:
                r = await c.get(f"{settings.navidrome_url}/ping")
            return {"online": r.status_code == 200, "version": None}
        except httpx.HTTPError:
            return {"online": False, "version": None}

    jf, nd = await asyncio.gather(jellyfin(), navidrome())
    jf.update(configured=bool(settings.jellyfin_api_key), port=8096, last_scan=last_scan["videos"])
    nd.update(configured=bool(settings.navidrome_password), port=4533, last_scan=last_scan["music"])
    return {"videos": jf, "music": nd}
