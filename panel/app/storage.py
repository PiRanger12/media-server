"""Operaciones sobre el sistema de archivos, siempre confinadas a la carpeta de cada biblioteca."""
import os
import re
import shutil
from pathlib import Path

from fastapi import HTTPException

from .config import LIBRARIES, settings

_INVALID_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def check_library(library: str) -> Path:
    if library not in LIBRARIES:
        raise HTTPException(404, f"Biblioteca desconocida: {library}")
    root = settings.library_root(library)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def safe_path(library: str, rel: str = "") -> Path:
    """Convierte una ruta relativa en absoluta y verifica que no se salga de la biblioteca."""
    root = check_library(library)
    target = (root / rel.strip("/")).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(400, "Ruta fuera de la biblioteca")
    return target


def clean_name(name: str) -> str:
    name = name.strip()
    if not name or name in {".", ".."} or _INVALID_NAME.search(name):
        raise HTTPException(400, f"Nombre no válido: {name!r}")
    return name


def check_extension(library: str, filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in LIBRARIES[library]:
        raise HTTPException(415, f"Tipo de archivo no permitido en {library}: {ext or 'sin extensión'}")


def rel_to(library: str, path: Path) -> str:
    return path.relative_to(check_library(library)).as_posix()


def list_dir(library: str, rel: str) -> dict:
    folder = safe_path(library, rel)
    if not folder.is_dir():
        raise HTTPException(404, "La carpeta no existe")
    entries = []
    with os.scandir(folder) as it:
        for e in it:
            if e.name.startswith("."):
                continue
            st = e.stat()
            is_dir = e.is_dir()
            entries.append({
                "name": e.name,
                "path": rel_to(library, Path(e.path)),
                "type": "dir" if is_dir else "file",
                "size": None if is_dir else st.st_size,
                "modified": st.st_mtime,
                "ext": "" if is_dir else Path(e.name).suffix.lower(),
            })
    entries.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    return {"library": library, "path": rel_to(library, folder), "entries": entries}


def make_dir(library: str, parent: str, name: str) -> str:
    target = safe_path(library, parent) / clean_name(name)
    if target.exists():
        raise HTTPException(409, "Ya existe un elemento con ese nombre")
    target.mkdir(parents=True)
    return rel_to(library, target)


def rename(library: str, rel: str, new_name: str) -> str:
    src = safe_path(library, rel)
    if src == check_library(library):
        raise HTTPException(400, "No se puede renombrar la raíz")
    if not src.exists():
        raise HTTPException(404, "No existe")
    new_name = clean_name(new_name)
    if src.is_file():
        check_extension(library, new_name)
    dst = src.with_name(new_name)
    if dst.exists():
        raise HTTPException(409, "Ya existe un elemento con ese nombre")
    src.rename(dst)
    return rel_to(library, dst)


def move(library: str, rel: str, dest_folder: str) -> str:
    src = safe_path(library, rel)
    dest = safe_path(library, dest_folder)
    if src == check_library(library):
        raise HTTPException(400, "No se puede mover la raíz")
    if not src.exists():
        raise HTTPException(404, "No existe")
    if not dest.is_dir():
        raise HTTPException(404, "La carpeta destino no existe")
    if src.is_dir() and (dest == src or src in dest.parents):
        raise HTTPException(400, "No se puede mover una carpeta dentro de sí misma")
    target = dest / src.name
    if target.exists():
        raise HTTPException(409, "Ya existe un elemento con ese nombre en el destino")
    shutil.move(str(src), str(target))
    return rel_to(library, target)


def delete(library: str, rel: str) -> None:
    target = safe_path(library, rel)
    if target == check_library(library):
        raise HTTPException(400, "No se puede borrar la raíz")
    if not target.exists():
        raise HTTPException(404, "No existe")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def unique_path(path: Path) -> Path:
    """Si el archivo ya existe, agrega ' (1)', ' (2)', ... al nombre."""
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def dir_size(path: Path) -> tuple[int, int]:
    total, count = 0, 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
                count += 1
            except OSError:
                pass
    return total, count
