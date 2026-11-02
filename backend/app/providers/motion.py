"""Animated image montage ("motion comic") provider (CPU friendly, no AI model).

Animates a still AI image with a camera move (push in, pull out, pans, tilts),
gentle "breathing" and a vignette. This is NOT AI video generation and is
labelled as "motion comic" everywhere in the UI. It is the fallback when the
machine cannot run Wan 2.2.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import ffmpeg
from .base import ClipRequest, ProviderError, VideoProvider


def camera_expr(camera: str, frames: int) -> tuple[str, str, str]:
    """Return zoompan (z, x, y) expressions for a camera instruction."""
    c = camera.lower()
    n = max(frames - 1, 1)
    t = f"(on/{n})"  # 0 -> 1 over the clip
    ease = f"(0.5-0.5*cos(PI*{t}))"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if any(k in c for k in ("pull", "out", "reveal", "wide")):
        return f"1.25-0.2*{ease}", cx, cy
    if "left" in c:
        return "1.18", f"(iw-iw/zoom)*(1-{ease})", cy
    if "right" in c or "track" in c or "follow" in c or "pan" in c:
        return "1.18", f"(iw-iw/zoom)*{ease}", cy
    if "tilt up" in c or "rise" in c or "crane" in c:
        return "1.18", cx, f"(ih-ih/zoom)*(1-{ease})"
    if "tilt" in c or "down" in c:
        return "1.18", cx, f"(ih-ih/zoom)*{ease}"
    if "static" in c or "still" in c or "locked" in c:
        return f"1.04+0.01*sin(2*PI*{t})", cx, cy
    if "close" in c or "fast" in c or "dramatic" in c:
        return f"1.0+0.35*{ease}", cx, cy
    return f"1.0+0.18*{ease}", cx, cy  # default slow push in


class MotionComicVideo(VideoProvider):
    name = "motion-comic"
    limits = "Runs on any CPU with FFmpeg. Animates still images with camera moves; not AI-generated motion."
    license = "Uses FFmpeg (LGPL/GPL); output is your own"
    quality_label = "animated image montage (not AI video)"

    def check(self) -> tuple[bool, str]:
        if not shutil.which("ffmpeg"):
            return False, "FFmpeg not installed"
        return True, "FFmpeg"

    def generate(self, req: ClipRequest, out: Path) -> Path:
        if not req.image.exists():
            raise ProviderError(f"image missing: {req.image}")
        frames = max(1, int(round(req.duration_s * req.fps)))
        z, x, y = camera_expr(req.camera, frames)
        w, h = req.width, req.height
        # Upscale first so zoompan has pixels to move through (reduces jitter).
        vf = (
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={req.fps},"
            f"vignette=PI/5,format=yuv420p"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.run(["-loop", "1", "-i", str(req.image), "-vf", vf, "-frames:v", str(frames),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(req.fps), str(out)])
        return out
