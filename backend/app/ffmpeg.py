"""Thin FFmpeg/ffprobe helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FFmpegError("FFmpeg is not installed or not on PATH")


def run(args: list[str], timeout: int = 3600) -> None:
    require_ffmpeg()
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise FFmpegError(f"ffmpeg failed: {p.stderr.strip()[-1500:]}")


def probe(path: Path | str) -> dict:
    require_ffmpeg()
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {p.stderr.strip()[-500:]}")
    return json.loads(p.stdout)


def duration(path: Path | str) -> float:
    return float(probe(path)["format"].get("duration", 0.0))
