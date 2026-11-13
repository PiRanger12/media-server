import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PANEL_PASSWORD", "secreto")
    monkeypatch.setenv("WATCH_ENABLED", "0")
    for mod in [m for m in sys.modules if m.startswith("app")]:
        del sys.modules[mod]
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(c):
    assert c.post("/api/login", json={"password": "secreto"}).status_code == 200


def test_requires_auth(client):
    assert client.get("/api/videos/list").status_code == 401
    assert client.post("/api/login", json={"password": "mal"}).status_code == 401
    assert client.get("/").status_code in (200, 307)


def test_folder_upload_rename_move_delete(client):
    login(client)
    assert client.post("/api/videos/folder", json={"parent": "", "name": "Peliculas"}).json()["path"] == "Peliculas"
    r = client.put("/api/videos/upload", params={"path": "Peliculas", "name": "demo.mp4"}, content=b"x" * 2048)
    assert r.status_code == 200, r.text
    # nombre duplicado → se agrega sufijo
    r2 = client.put("/api/videos/upload", params={"path": "Peliculas", "name": "demo.mp4"}, content=b"y")
    assert r2.json()["path"] == "Peliculas/demo (1).mp4"
    names = [e["name"] for e in client.get("/api/videos/list", params={"path": "Peliculas"}).json()["entries"]]
    assert names == ["demo (1).mp4", "demo.mp4"]

    assert client.post("/api/videos/rename", json={"path": "Peliculas/demo.mp4", "new_name": "Otra.mp4"}).status_code == 200
    client.post("/api/videos/folder", json={"parent": "", "name": "Series"})
    assert client.post("/api/videos/move", json={"path": "Peliculas/Otra.mp4", "dest": "Series"}).json()["path"] == "Series/Otra.mp4"
    assert client.get("/api/videos/folders").json()["folders"] == ["", "Peliculas", "Series"]
    assert client.delete("/api/videos/item", params={"path": "Series"}).status_code == 200
    assert client.delete("/api/videos/item", params={"path": ""}).status_code == 400


def test_security(client):
    login(client)
    assert client.get("/api/videos/list", params={"path": "../music"}).status_code == 400
    assert client.get("/api/videos/list", params={"path": "../../etc"}).status_code == 400
    assert client.put("/api/videos/upload", params={"name": "../x.mp4"}, content=b"1").status_code == 400
    assert client.put("/api/videos/upload", params={"name": "virus.sh"}, content=b"1").status_code == 415
    assert client.put("/api/music/upload", params={"name": "peli.mkv"}, content=b"1").status_code == 415
    assert client.get("/api/otra/list").status_code == 404
    client.post("/api/music/folder", json={"parent": "", "name": "A"})
    assert client.post("/api/music/move", json={"path": "A", "dest": "A"}).status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg no instalado")
def test_audio_tags_and_video_info(client, tmp_path):
    login(client)
    mp3 = tmp_path / "t.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=2", "-y", str(mp3)], check=True)
    client.put("/api/music/upload", params={"name": "t.mp3"}, content=mp3.read_bytes())
    r = client.put("/api/music/tags", json={"path": "t.mp3", "tags": {"title": "Canción", "artist": "Yo", "tracknumber": "1"}})
    assert r.status_code == 200, r.text
    info = client.get("/api/music/info", params={"path": "t.mp3"}).json()
    assert info["tags"]["title"] == "Canción" and info["tags"]["artist"] == "Yo"

    mp4 = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=3:s=320x240", "-pix_fmt", "yuv420p", "-y", str(mp4)], check=True)
    client.put("/api/videos/upload", params={"name": "v.mp4"}, content=mp4.read_bytes())
    vi = client.get("/api/videos/info", params={"path": "v.mp4"}).json()
    assert vi["resolution"] == "320x240"
    th = client.get("/api/videos/thumb", params={"path": "v.mp4"})
    assert th.status_code == 200 and th.headers["content-type"] == "image/jpeg"
    rng = client.get("/api/videos/stream", params={"path": "v.mp4"}, headers={"Range": "bytes=0-99"})
    assert rng.status_code == 206 and len(rng.content) == 100


def test_scan_without_config(client):
    login(client)
    r = client.post("/api/videos/scan").json()
    assert r["ok"] is False and "JELLYFIN_API_KEY" in r["detail"]
