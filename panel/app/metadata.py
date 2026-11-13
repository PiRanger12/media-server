"""Lectura/edición de metadatos: etiquetas de audio (mutagen) e información de video (ffprobe)."""
import hashlib
import json
import subprocess
from pathlib import Path

import mutagen
from fastapi import HTTPException

from .config import settings

EDITABLE_TAGS = ["title", "artist", "album", "albumartist", "genre", "date", "tracknumber", "discnumber"]


def read_tags(path: Path) -> dict:
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as exc:  # archivo dañado o formato raro
        raise HTTPException(422, f"No se pudo leer el archivo: {exc}")
    if audio is None:
        raise HTTPException(415, "Formato de audio no soportado para etiquetas")
    tags = {k: (audio.get(k) or [""])[0] for k in EDITABLE_TAGS}
    info = getattr(audio, "info", None)
    return {
        "tags": tags,
        "duration": round(getattr(info, "length", 0) or 0, 1),
        "bitrate": getattr(info, "bitrate", None),
        "sample_rate": getattr(info, "sample_rate", None),
        "format": type(audio).__name__,
    }


def write_tags(path: Path, new_tags: dict) -> dict:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise HTTPException(415, "Formato de audio no soportado para etiquetas")
    if audio.tags is None:
        audio.add_tags()
    for key in EDITABLE_TAGS:
        if key not in new_tags:
            continue
        value = (new_tags[key] or "").strip()
        try:
            if value:
                audio[key] = value
            elif key in audio:
                del audio[key]
        except (KeyError, ValueError):
            # algunos formatos no soportan ciertas etiquetas (p. ej. WAV)
            continue
    audio.save()
    return read_tags(path)


def probe_video(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        raise HTTPException(422, f"ffprobe falló: {exc}")
    data = json.loads(out or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]
    return {
        "duration": round(float(fmt.get("duration", 0) or 0), 1),
        "size": int(fmt.get("size", 0) or 0),
        "bitrate": int(fmt.get("bit_rate", 0) or 0),
        "container": fmt.get("format_long_name"),
        "video_codec": video.get("codec_name"),
        "resolution": f"{video.get('width')}x{video.get('height')}" if video else None,
        "audio_tracks": [
            {"codec": a.get("codec_name"), "language": a.get("tags", {}).get("language"), "channels": a.get("channels")}
            for a in audios
        ],
        "subtitles": [s.get("tags", {}).get("language") or s.get("codec_name") for s in subs],
    }


def video_thumbnail(path: Path) -> Path:
    """Genera (y cachea) una miniatura JPG tomada al 10 % del video."""
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()
    thumbs = settings.data_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    out = thumbs / f"{key}.jpg"
    if out.exists():
        return out
    try:
        duration = probe_video(path)["duration"]
    except HTTPException:
        duration = 0
    seek = max(1.0, duration * 0.1) if duration else 1.0
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{seek:.1f}", "-i", str(path), "-frames:v", "1",
         "-vf", "scale=320:-2", "-q:v", "5", "-y", str(out)],
        capture_output=True, timeout=60,
    )
    if result.returncode != 0 or not out.exists():
        raise HTTPException(422, "No se pudo generar la miniatura")
    return out
