import os
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".ts", ".srt", ".ass", ".vtt"}
MUSIC_EXT = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".wma", ".alac", ".aiff", ".lrc"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}  # portadas / pósters

LIBRARIES = {
    "videos": VIDEO_EXT | IMAGE_EXT | {".nfo"},
    "music": MUSIC_EXT | IMAGE_EXT,
}


@dataclass
class Settings:
    media_dir: Path = field(default_factory=lambda: Path(os.getenv("MEDIA_DIR", "/media")))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "/data")))
    panel_password: str = field(default_factory=lambda: os.getenv("PANEL_PASSWORD", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-secret"))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "8192")))
    jellyfin_url: str = field(default_factory=lambda: os.getenv("JELLYFIN_URL", "http://jellyfin:8096"))
    jellyfin_api_key: str = field(default_factory=lambda: os.getenv("JELLYFIN_API_KEY", ""))
    navidrome_url: str = field(default_factory=lambda: os.getenv("NAVIDROME_URL", "http://navidrome:4533"))
    navidrome_user: str = field(default_factory=lambda: os.getenv("NAVIDROME_USER", "admin"))
    navidrome_password: str = field(default_factory=lambda: os.getenv("NAVIDROME_PASSWORD", ""))
    watch_enabled: bool = field(default_factory=lambda: os.getenv("WATCH_ENABLED", "1") == "1")

    def library_root(self, library: str) -> Path:
        return self.media_dir / library


settings = Settings()
