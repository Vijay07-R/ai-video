"""Checks run BEFORE a job is queued, so "Generate" never silently starts a job
that cannot finish. Nothing here generates anything or spends quota."""
from __future__ import annotations

import shutil

from .. import languages
from ..providers import get_manager

FIX = {
    "llm": "Add your free GEMINI_API_KEY to backend/.env (https://aistudio.google.com/apikey) or install Ollama and run "
           "`ollama pull gemma3:4b`, then restart the engine.",
    "image": "Start ComfyUI (http://127.0.0.1:8188) and put the image model (COMFY_IMAGE_CHECKPOINT) in ComfyUI/models/checkpoints.",
}
VOICE_FIX = {
    "en": "pip install kokoro soundfile",
    "hi": "pip install kokoro soundfile (and install espeak-ng), or set up Indic Parler-TTS / a Piper Hindi voice",
    "ta": "set up Indic Parler-TTS, or download a Piper Tamil voice and set PIPER_VOICES=ta=<path>.onnx",
    "te": "set up Indic Parler-TTS, or download a Piper Telugu voice and set PIPER_VOICES=te=<path>.onnx",
}


def run(settings: dict) -> dict:
    m = get_manager()
    problems, warnings, plan = [], [], {}
    lang = settings.get("language", "en")
    L = languages.get(lang)
    if lang not in languages.LANGUAGES:
        problems.append(f"Language '{lang}' is not supported. Choose one of: {', '.join(languages.SUPPORTED)}.")

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        problems.append("FFmpeg is not installed or not on PATH (Windows: winget install Gyan.FFmpeg).")

    for kind in ("llm", "image"):
        p, reasons = m.first_available(kind)
        plan[kind] = p.name if p else None
        if not p:
            why = "; ".join(f"{k}: {v}" for k, v in reasons.items())
            problems.append(f"No free {'story AI' if kind == 'llm' else 'image generator'} is ready ({why}). {FIX[kind]}")

    v, reasons = m.first_available("voice", language=lang)
    plan["voice"] = v.name if v else None
    if not v:
        problems.append(f"No free {L.name} voice is installed, so the video cannot be narrated in {L.name}. "
                        f"Fix: {VOICE_FIX.get(lang, 'install a voice for this language')}. "
                        "(The engine will not switch to another language on its own.)")
    elif v.name == "espeak":
        warnings.append(f"Only the robotic eSpeak voice is available for {L.name}. Fix for natural speech: {VOICE_FIX.get(lang, '')}.")

    vid, vreasons = m.first_available("video")
    plan["video"] = vid.name if vid else None
    motion = settings.get("motion", "auto")
    if motion == "montage":
        warnings.append("You chose animated image montage: scenes are still AI images with camera moves, not AI video.")
    elif not vid or vid.name == "motion-comic":
        why = vreasons.get("comfyui-wan", "not available")
        warnings.append(f"AI video (Wan 2.2) is not available ({why}). Scenes will be an animated image montage, not AI video.")

    for kind in ("music", "sfx"):
        p, _ = m.first_available(kind)
        plan[kind] = p.name if p else None

    sub = (settings.get("subtitle_language") or "same").lower()
    if settings.get("subtitles", True) and sub not in ("same", lang) and sub not in languages.LANGUAGES:
        problems.append(f"Subtitle language '{sub}' is not supported.")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "plan": plan, "language": L.name}


def language_report() -> list[dict]:
    """Which voice each language would use right now."""
    m = get_manager()
    out = []
    for code, L in languages.LANGUAGES.items():
        v, reasons = m.first_available("voice", language=code)
        out.append({"code": code, "name": L.name, "native": L.native,
                    "voice": v.name if v else None, "natural": bool(v and v.name != "espeak"),
                    "fix": VOICE_FIX.get(code, ""), "reasons": reasons})
    return out
