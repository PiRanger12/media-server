import asyncio
import logging
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import metadata, scanners, storage, watcher
from .config import LIBRARIES, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    for lib in LIBRARIES:
        settings.library_root(lib).mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[asyncio.Task] = []
    watcher.start(tasks)
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Media Panel", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=7 * 24 * 3600, same_site="lax")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ── Autenticación ───────────────────────────────────────────────────────
def require_auth(request: Request) -> None:
    if not request.session.get("auth"):
        raise HTTPException(401, "Inicia sesión")


class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
async def login(body: LoginIn, request: Request):
    if not settings.panel_password:
        raise HTTPException(503, "Configura PANEL_PASSWORD en el archivo .env")
    if not secrets.compare_digest(body.password.encode(), settings.panel_password.encode()):
        await asyncio.sleep(1)  # frena intentos por fuerza bruta
        raise HTTPException(401, "Contraseña incorrecta")
    request.session["auth"] = True
    return {"ok": True}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/", include_in_schema=False)
async def index(request: Request):
    if not request.session.get("auth"):
        return RedirectResponse("/login")
    return FileResponse(STATIC / "index.html")


@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(STATIC / "login.html")


# ── Estado general ──────────────────────────────────────────────────────
@app.get("/api/status", dependencies=[Depends(require_auth)])
async def status():
    return await scanners.status()


@app.get("/api/stats", dependencies=[Depends(require_auth)])
async def stats():
    disk = shutil.disk_usage(settings.media_dir)
    libs = {}
    for lib in LIBRARIES:
        size, count = await asyncio.to_thread(storage.dir_size, settings.library_root(lib))
        libs[lib] = {"size": size, "files": count}
    return {"disk": {"total": disk.total, "used": disk.used, "free": disk.free}, "libraries": libs}


# ── Navegación y organización ──────────────────────────────────────────
class FolderIn(BaseModel):
    parent: str = ""
    name: str


class RenameIn(BaseModel):
    path: str
    new_name: str


class MoveIn(BaseModel):
    path: str
    dest: str


@app.get("/api/{library}/list", dependencies=[Depends(require_auth)])
async def list_dir(library: str, path: str = ""):
    return storage.list_dir(library, path)


@app.get("/api/{library}/folders", dependencies=[Depends(require_auth)])
async def all_folders(library: str):
    root = storage.check_library(library)
    folders = [""] + sorted(
        storage.rel_to(library, p) for p in root.rglob("*") if p.is_dir() and not p.name.startswith(".")
    )
    return {"folders": folders}


@app.post("/api/{library}/folder", dependencies=[Depends(require_auth)])
async def create_folder(library: str, body: FolderIn):
    return {"path": storage.make_dir(library, body.parent, body.name)}


@app.post("/api/{library}/rename", dependencies=[Depends(require_auth)])
async def rename(library: str, body: RenameIn):
    return {"path": storage.rename(library, body.path, body.new_name)}


@app.post("/api/{library}/move", dependencies=[Depends(require_auth)])
async def move(library: str, body: MoveIn):
    return {"path": storage.move(library, body.path, body.dest)}


@app.delete("/api/{library}/item", dependencies=[Depends(require_auth)])
async def delete(library: str, path: str = Query(...)):
    storage.delete(library, path)
    return {"ok": True}


# ── Subida (cuerpo binario directo, sin multipart, para no duplicar archivos grandes en /tmp) ──
@app.put("/api/{library}/upload", dependencies=[Depends(require_auth)])
async def upload(library: str, request: Request, path: str = "", name: str = Query(...)):
    filename = storage.clean_name(unquote(name))
    storage.check_extension(library, filename)
    folder = storage.safe_path(library, path)
    if not folder.is_dir():
        raise HTTPException(404, "La carpeta destino no existe")

    limit = settings.max_upload_mb * 1024 * 1024
    declared = int(request.headers.get("content-length") or 0)
    if declared > limit:
        raise HTTPException(413, f"El archivo supera {settings.max_upload_mb} MB")

    final = storage.unique_path(folder / filename)
    tmp = folder / f".upload-{secrets.token_hex(6)}-{filename}"  # oculto: el vigilante lo ignora
    written = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, f"El archivo supera {settings.max_upload_mb} MB")
                await asyncio.to_thread(f.write, chunk)
        if written == 0:
            raise HTTPException(400, "Archivo vacío")
        tmp.rename(final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return {"path": storage.rel_to(library, final), "size": written}


# ── Metadatos, miniaturas y vista previa ───────────────────────────────
class TagsIn(BaseModel):
    path: str
    tags: dict[str, str]


@app.get("/api/{library}/info", dependencies=[Depends(require_auth)])
async def info(library: str, path: str = Query(...)):
    target = storage.safe_path(library, path)
    if not target.is_file():
        raise HTTPException(404, "No es un archivo")
    if library == "music":
        return {"kind": "audio", **await asyncio.to_thread(metadata.read_tags, target)}
    return {"kind": "video", **await asyncio.to_thread(metadata.probe_video, target)}


@app.put("/api/music/tags", dependencies=[Depends(require_auth)])
async def update_tags(body: TagsIn):
    target = storage.safe_path("music", body.path)
    if not target.is_file():
        raise HTTPException(404, "No es un archivo")
    return await asyncio.to_thread(metadata.write_tags, target, body.tags)


@app.get("/api/videos/thumb", dependencies=[Depends(require_auth)])
async def thumb(path: str = Query(...)):
    target = storage.safe_path("videos", path)
    if not target.is_file():
        raise HTTPException(404, "No es un archivo")
    out = await asyncio.to_thread(metadata.video_thumbnail, target)
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/{library}/stream", dependencies=[Depends(require_auth)])
async def stream(library: str, path: str = Query(...)):
    target = storage.safe_path(library, path)
    if not target.is_file():
        raise HTTPException(404, "No es un archivo")
    return FileResponse(target)  # soporta Range: el navegador puede adelantar/retroceder


# ── Escaneo manual ─────────────────────────────────────────────────────
@app.post("/api/{library}/scan", dependencies=[Depends(require_auth)])
async def scan(library: str):
    storage.check_library(library)
    return await scanners.scan(library)
