"""Local file storage. All stored paths are relative to DATA_DIR so the data
folder can be moved (or swapped for S3-compatible storage later)."""
from __future__ import annotations

from pathlib import Path

from .config import get_settings


def data_dir() -> Path:
    return get_settings().data_dir


def project_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id
    for sub in ("characters", "images", "clips", "voice", "sfx", "music", "render", "uploads"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


def rel(path: Path | str) -> str:
    # always forward slashes: these strings become URLs (/files/...) and must work on Windows too
    return Path(path).resolve().relative_to(data_dir().resolve()).as_posix()


def absolute(relpath: str) -> Path:
    p = (data_dir() / relpath).resolve()
    if not str(p).startswith(str(data_dir().resolve())):
        raise ValueError("path escapes data directory")
    return p
