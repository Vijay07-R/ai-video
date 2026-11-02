"""One-time setup helper for the free AI pieces (Windows, macOS, Linux).

Run from the project folder AFTER scripts\\start.bat has run once:
    backend\\.venv\\Scripts\\python scripts\\setup_free_ai.py        (Windows)
    backend/.venv/bin/python scripts/setup_free_ai.py              (macOS / Linux)

It will:
  1. ask for your free Gemini API key and save it in backend/.env
  2. install Piper TTS and download a Tamil + an English Piper voice (free) into backend/voices
  3. check ComfyUI and (optionally) download the free FLUX schnell image model into your ComfyUI folder
Nothing here costs money or needs a credit card.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ENV = BACKEND / ".env"
VOICES = BACKEND / "voices"

PIPER_VOICES = {
    # language: (folder-free file name, download base URL)
    "ta": ("ta_IN-rasa_male-medium", "https://huggingface.co/tinisoft/piper-ta_IN-rasa_male-medium/resolve/main/"),
    "en": ("en_US-lessac-medium", "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/"),
}
FLUX_URL = "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors"
FLUX_FILE = "flux1-schnell-fp8.safetensors"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def ask(q: str, default: str = "") -> str:
    try:
        a = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        a = ""
    return a or default


def yes(q: str, default: bool = True) -> bool:
    a = ask(q + (" (Y/n)" if default else " (y/N)")).lower()
    return default if not a else a.startswith("y")


def set_env(key: str, value: str) -> None:
    """Set KEY=value in backend/.env, replacing an existing line or appending one."""
    if not ENV.exists():
        example = BACKEND / ".env.example"
        ENV.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")
    lines = ENV.read_text(encoding="utf-8").splitlines()
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def get_env(key: str) -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            return line.split("=", 1)[1].strip()
    return ""


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        say(f"   already there: {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "animal-video-engine-setup"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                got += len(chunk)
                if total:
                    print(f"\r   {dest.name}: {got / 2**20:,.0f} / {total / 2**20:,.0f} MB", end="", flush=True)
        print()
        tmp.replace(dest)
        return True
    except Exception as e:
        print()
        say(f"   ! download failed ({e}). You can download it in your browser instead:\n     {url}\n     and save it as {dest}")
        tmp.unlink(missing_ok=True)
        return False


def step_gemini() -> None:
    say("\n1) Story AI: Google Gemini (free, no credit card)")
    if get_env("GEMINI_API_KEY"):
        say("   A key is already saved.")
        if not yes("   Replace it?", False):
            return
    say("   Open https://aistudio.google.com/apikey , sign in with Google, click 'Create API key', copy it.")
    key = ask("   Paste your key here (or press Enter to skip)")
    if key:
        set_env("GEMINI_API_KEY", key)
        say("   Saved to backend/.env")


def step_voices() -> None:
    say("\n2) Voices: Piper (free, fast on any computer)")
    try:
        import piper  # noqa: F401
        say("   piper-tts is already installed.")
    except ImportError:
        say("   Installing piper-tts ...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts"], text=True)
        if r.returncode != 0:
            say("   ! pip install piper-tts failed. Run it again later; voices will still be downloaded.")
    pairs = []
    for lang, (name, base) in PIPER_VOICES.items():
        ok = download(base + name + ".onnx", VOICES / f"{name}.onnx")
        ok = download(base + name + ".onnx.json", VOICES / f"{name}.onnx.json") and ok
        if ok:
            pairs.append(f"{lang}={(VOICES / (name + '.onnx')).as_posix()}")
    existing = [p for p in get_env("PIPER_VOICES").replace(",", ";").split(";") if "=" in p]
    merged = {p.split("=", 1)[0]: p for p in existing}
    merged.update({p.split("=", 1)[0]: p for p in pairs})
    if merged:
        set_env("PIPER_VOICES", ";".join(merged.values()))
        say(f"   Voices ready for: {', '.join(sorted(merged))}")
    say("   Telugu / Hindi: Indic Parler-TTS gives natural voices (see README section 2), or add a Piper voice to PIPER_VOICES.")


def step_comfy() -> None:
    say("\n3) Images: ComfyUI (free)")
    url = get_env("COMFYUI_URL") or "http://127.0.0.1:8188"
    try:
        with urllib.request.urlopen(url + "/system_stats", timeout=3) as r:
            stats = json.load(r)
        devs = stats.get("devices", [])
        vram = max((d.get("vram_total", 0) for d in devs), default=0) / 2**30
        say(f"   ComfyUI is running at {url}" + (f" (GPU memory {vram:.1f} GB)" if vram else ""))
    except Exception:
        say(f"   ComfyUI is NOT reachable at {url}.")
        say("   Install it from https://www.comfy.org/download and start it.")
        say("   NOTE: this engine uses port 8000. If ComfyUI Desktop also uses 8000, change ComfyUI's port to 8188")
        say("   (ComfyUI Settings -> Server-Config -> Port), or set COMFYUI_URL in backend/.env to ComfyUI's address.")
        new = ask("   ComfyUI address if different (Enter to keep)", url)
        if new != url:
            set_env("COMFYUI_URL", new.rstrip("/"))
    say(f"   The image model file is {FLUX_FILE} (about 17 GB, Apache 2.0 license).")
    folder = ask("   Your ComfyUI folder to download it into (contains 'models'), or Enter to skip")
    if folder:
        dest = Path(folder.strip('"')) / "models" / "checkpoints" / FLUX_FILE
        if yes(f"   Download to {dest}? This is large and can take a long time", True):
            download(FLUX_URL, dest)
    else:
        say(f"   Skipped. Download it in your browser: {FLUX_URL}\n   and put it in ComfyUI\\models\\checkpoints\\")


def main() -> None:
    say("Animal Video Engine - free AI setup (nothing here costs money)")
    if not BACKEND.exists():
        say("Run this from the project folder.")
        sys.exit(1)
    step_gemini()
    step_voices()
    step_comfy()
    say("\nDone. Close the engine window, run scripts\\start.bat again, and open http://localhost:8000/#/create")
    say("The red boxes on the Create page will disappear as each piece becomes ready.")
    if os.name == "nt":
        ask("Press Enter to close")


if __name__ == "__main__":
    main()
