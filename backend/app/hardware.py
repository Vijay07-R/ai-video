"""Inspects the machine the engine runs on and recommends a generation tier.

Tiers
- "gpu-video":  NVIDIA GPU with >= 8 GB VRAM -> Wan 2.2 TI2V-5B AI video (slow but real)
- "gpu-image":  NVIDIA GPU with >= 4 GB VRAM -> AI images + motion-comic animation
- "cpu":        no usable GPU -> AI images on CPU (very slow) + motion-comic animation
Apple Silicon is reported as "gpu-image" (ComfyUI supports MPS; Wan on Mac is very slow).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache

import psutil


def _nvidia() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            gpus.append({"vendor": "nvidia", "name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1),
                         "vram_free_gb": round(float(parts[2]) / 1024, 1), "driver": parts[3], "cuda": True})
    return gpus


def _cpu_name() -> str:
    name = platform.processor()
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    return name or platform.machine()


@lru_cache(maxsize=1)
def inspect_hardware() -> dict:
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage(os.getenv("DATA_DIR", "."))
    gpus = _nvidia()
    apple = platform.system() == "Darwin" and platform.machine() == "arm64"
    if apple:
        gpus.append({"vendor": "apple", "name": "Apple Silicon (unified memory)", "vram_gb": round(vm.total / 2**30, 1), "cuda": False})

    best = max((g["vram_gb"] for g in gpus if g["vendor"] == "nvidia"), default=0)
    if best >= 8:
        tier = "gpu-video"
    elif best >= 4 or apple:
        tier = "gpu-image"
    else:
        tier = "cpu"

    notes = {
        "gpu-video": "AI video with Wan 2.2 TI2V-5B is possible. Expect several minutes per 5-second clip; 8 GB cards need the GGUF/fp8 models.",
        "gpu-image": "AI images run well; full AI video is not practical on this GPU, so scenes are animated with the motion-comic renderer.",
        "cpu": "No usable GPU found. Image generation on CPU is very slow (minutes per image) and AI video is not practical; scenes use motion-comic animation.",
    }[tier]

    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": _cpu_name(),
        "cpu_cores": psutil.cpu_count(logical=False) or psutil.cpu_count(),
        "ram_gb": round(vm.total / 2**30, 1),
        "disk_free_gb": round(disk.free / 2**30, 1),
        "gpus": gpus,
        "cuda": any(g.get("cuda") for g in gpus),
        "tier": tier,
        "recommendation": notes,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "note": "This describes the machine running the backend. ComfyUI may run on a different machine (COMFYUI_URL).",
    }
