"""Local text-to-speech adapters, each declaring the languages it can speak.

| Provider     | Languages here            | Speed (CPU)  | Quality        | License |
|--------------|---------------------------|--------------|----------------|---------|
| kokoro       | en, hi (+es fr it pt ja zh)| fast        | natural        | Apache 2.0 |
| indic-parler | ta, te, hi, en            | slow (GPU ok)| natural        | Apache 2.0 (gated download on Hugging Face) |
| piper        | any language you add a voice for | very fast | good       | MIT / GPL engine; voice licenses vary |
| espeak       | ta, te, hi, en            | instant      | robotic        | GPL-3.0 |

Models are loaded once per process and reused for every scene.
"""
from __future__ import annotations

import gc
import importlib.util
import os
import re
import shutil
import subprocess
import threading
import wave
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from ..config import Settings
from .base import ProviderError, ProviderUnavailable, VoiceProvider

KOKORO_LANGS = {  # language -> (Kokoro lang code, voices: narrator first)
    "en": ("a", ["af_heart", "am_michael", "bf_emma", "am_adam", "af_bella", "bm_george"]),
    "hi": ("h", ["hf_alpha", "hm_omega", "hf_beta", "hm_psi"]),
    "es": ("e", ["ef_dora", "em_alex"]), "fr": ("f", ["ff_siwis"]), "it": ("i", ["if_sara", "im_nicola"]),
    "pt": ("p", ["pf_dora", "pm_alex"]), "ja": ("j", ["jf_alpha", "jm_kumo"]), "zh": ("z", ["zf_xiaoxiao", "zm_yunjian"]),
}
# Indic Parler-TTS recommended speakers (from the model card); narrator first
PARLER_SPEAKERS = {"ta": ["Jaya", "Kavya"], "te": ["Lalitha", "Prakash"], "hi": ["Divya", "Rohit"], "en": ["Thoma", "Mary"]}


def _write_wav(out: Path, audio: np.ndarray, sr: int) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(out), sr, (np.clip(audio, -1, 1) * 32767).astype(np.int16))
    return out


def _sentences(text: str, max_len: int = 220) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?।॥])\s+", text) if p.strip()]
    out = []
    for p in parts:
        while len(p) > max_len:
            cut = p.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            out.append(p[:cut])
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [text]


class LangVoice(VoiceProvider):
    languages: set[str] = set()
    cpu_rank = 50   # lower = preferred when no GPU
    gpu_rank = 50   # lower = preferred with a CUDA GPU

    def supports(self, language: str = "en", **_) -> bool:
        return language in self.languages

    def voices(self, language: str) -> list[str]:
        return []


class KokoroVoice(LangVoice):
    name = "kokoro"
    limits = "Local; ~1.5 GB VRAM or CPU; fast. English & Hindi here (Hindi needs espeak-ng installed for pronunciation)."
    license = "Apache 2.0 (hexgrad/Kokoro-82M)"
    quality_label = "neural TTS"
    languages = set(KOKORO_LANGS)
    cpu_rank, gpu_rank = 10, 10

    def __init__(self, settings: Settings):
        self.s = settings
        self._pipes: dict[str, object] = {}
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, str]:
        if importlib.util.find_spec("kokoro") is None:
            return False, "not installed (pip install kokoro soundfile)"
        return True, "loaded on first use"

    def voices(self, language: str) -> list[str]:
        return KOKORO_LANGS.get(language, ("a", []))[1]

    def _pipe(self, lang_code: str):
        with self._lock:
            if lang_code not in self._pipes:
                try:
                    from kokoro import KPipeline
                except ImportError as e:
                    raise ProviderUnavailable("kokoro not installed") from e
                self._pipes[lang_code] = KPipeline(lang_code=lang_code)
            return self._pipes[lang_code]

    def synthesize(self, text: str, out: Path, voice: str | None = None, language: str = "en") -> Path:
        if language not in KOKORO_LANGS:
            raise ProviderUnavailable(f"Kokoro has no {language} voice")
        code, voices = KOKORO_LANGS[language]
        v = voice if voice in voices else voices[0]
        chunks = []
        try:
            for _, _, audio in self._pipe(code)(text, voice=v, speed=1.0):
                if audio is not None:
                    chunks.append(np.asarray(audio.cpu() if hasattr(audio, "cpu") else audio, dtype=np.float32))
        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderError(f"kokoro failed: {e}") from e
        if not chunks:
            raise ProviderError("kokoro produced no audio")
        return _write_wav(out, np.concatenate(chunks), 24000)

    def release(self) -> None:
        with self._lock:
            self._pipes.clear()
        gc.collect()


class IndicParlerVoice(LangVoice):
    name = "indic-parler"
    limits = ("Local AI4Bharat model (~0.9B params, ~4 GB download). Natural Tamil, Telugu & Hindi. "
              "Fast on an NVIDIA GPU; slow on CPU (can take longer than the audio itself). "
              "One-time setup: accept the model terms on huggingface.co and run `huggingface-cli login` (free).")
    license = "Apache 2.0 (ai4bharat/indic-parler-tts)"
    quality_label = "neural TTS"
    languages = {"ta", "te", "hi", "en"}
    cpu_rank, gpu_rank = 30, 5

    def __init__(self, settings: Settings):
        self.s = settings
        self._m = None
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, str]:
        if not self.s.indic_parler:
            return False, "disabled (INDIC_PARLER=false)"
        for mod in ("parler_tts", "transformers", "torch"):
            if importlib.util.find_spec(mod) is None:
                return False, "not installed (pip install git+https://github.com/huggingface/parler-tts.git)"
        return True, "loaded on first use"

    def voices(self, language: str) -> list[str]:
        return PARLER_SPEAKERS.get(language, ["Thoma"])

    def _load(self):
        with self._lock:
            if self._m is None:
                try:
                    import torch
                    from parler_tts import ParlerTTSForConditionalGeneration
                    from transformers import AutoTokenizer
                except ImportError as e:
                    raise ProviderUnavailable("parler-tts not installed") from e
                dev = "cuda:0" if torch.cuda.is_available() else "cpu"
                try:
                    model = ParlerTTSForConditionalGeneration.from_pretrained(self.s.indic_parler_model).to(dev)
                    tok = AutoTokenizer.from_pretrained(self.s.indic_parler_model)
                    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
                except Exception as e:  # gated model, no login, no network...
                    raise ProviderUnavailable(f"could not load {self.s.indic_parler_model}: {e}") from e
                self._m = (torch, model, tok, desc_tok, dev)
            return self._m

    def synthesize(self, text: str, out: Path, voice: str | None = None, language: str = "en") -> Path:
        torch, model, tok, desc_tok, dev = self._load()
        speakers = self.voices(language)
        spk = voice if voice in speakers else speakers[0]
        style = os.getenv("INDIC_PARLER_STYLE", "a warm, expressive storytelling voice at a moderate pace")
        desc = f"{spk} speaks with {style}. The recording is very clear and close-sounding with no background noise."
        d = desc_tok(desc, return_tensors="pt").to(dev)
        pieces = []
        try:
            for sent in _sentences(text):
                p = tok(sent, return_tensors="pt").to(dev)
                with torch.inference_mode():
                    gen = model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                         prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask)
                pieces.append(gen.cpu().numpy().squeeze().astype(np.float32))
                pieces.append(np.zeros(int(model.config.sampling_rate * 0.15), dtype=np.float32))
        except Exception as e:
            raise ProviderError(f"indic-parler failed: {e}") from e
        return _write_wav(out, np.concatenate(pieces), model.config.sampling_rate)

    def release(self) -> None:
        with self._lock:
            if self._m is not None:
                torch = self._m[0]
                self._m = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()


class PiperVoice(LangVoice):
    name = "piper"
    limits = "Local, very fast on any CPU. Needs one downloaded .onnx voice per language (PIPER_VOICES)."
    license = "Piper engine MIT (rhasspy) / GPL-3.0 (piper1-gpl); each voice has its own license"
    quality_label = "neural TTS"
    cpu_rank, gpu_rank = 20, 20

    def __init__(self, settings: Settings):
        self.s = settings
        self.models = {k: v for k, v in settings.piper_voices.items()}
        if settings.piper_model and "en" not in self.models:
            self.models["en"] = settings.piper_model
        self.languages = {k for k, v in self.models.items() if v and Path(v).exists()}
        self._loaded: dict[str, object] = {}
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, str]:
        if not self.models:
            return False, "no voices configured (set PIPER_VOICES, e.g. ta=C:/voices/ta_IN-....onnx)"
        missing = [k for k, v in self.models.items() if not Path(v).exists()]
        if not self.languages:
            return False, f"voice files not found: {', '.join(missing)}"
        api = importlib.util.find_spec("piper") is not None
        if not api and not shutil.which(self.s.piper_bin):
            return False, "piper not installed (pip install piper-tts)"
        return True, "voices: " + ", ".join(sorted(self.languages)) + (f" (missing: {', '.join(missing)})" if missing else "")

    def voices(self, language: str) -> list[str]:
        return [Path(self.models[language]).stem] if language in self.models else []

    def synthesize(self, text: str, out: Path, voice: str | None = None, language: str = "en") -> Path:
        model = self.models.get(language)
        if not model or not Path(model).exists():
            raise ProviderUnavailable(f"no Piper voice for {language}")
        out.parent.mkdir(parents=True, exist_ok=True)
        if importlib.util.find_spec("piper") is not None:
            try:
                from piper import PiperVoice as _PV
                with self._lock:
                    if language not in self._loaded:
                        self._loaded[language] = _PV.load(model)
                v = self._loaded[language]
                with wave.open(str(out), "wb") as w:
                    if hasattr(v, "synthesize_wav"):
                        v.synthesize_wav(text, w)
                    else:
                        v.synthesize(text, w)
                return out
            except Exception as e:
                if not shutil.which(self.s.piper_bin):
                    raise ProviderError(f"piper failed: {e}") from e
        p = subprocess.run([self.s.piper_bin, "--model", model, "--output_file", str(out)],
                           input=text, capture_output=True, text=True, encoding="utf-8", timeout=600)
        if p.returncode != 0 or not out.exists():
            raise ProviderError(f"piper failed: {p.stderr[-300:]}")
        return out

    def release(self) -> None:
        with self._lock:
            self._loaded.clear()


def _espeak_exe(configured: str) -> str | None:
    for c in (configured, shutil.which("espeak-ng") or "", shutil.which("espeak") or "",
              r"C:\Program Files\eSpeak NG\espeak-ng.exe", r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe"):
        if c and Path(c).exists():
            return c
    return None


class EspeakVoice(LangVoice):
    name = "espeak"
    limits = "Instant, any CPU, but ROBOTIC. Used only when no natural voice is installed for the language (you are warned)."
    license = "GPL-3.0 (eSpeak NG)"
    quality_label = "robotic TTS"
    languages = {"en", "hi", "ta", "te"}
    cpu_rank, gpu_rank = 90, 90

    def __init__(self, settings: Settings | None = None):
        self.s = settings

    def check(self) -> tuple[bool, str]:
        exe = _espeak_exe(self.s.espeak_bin if self.s else "")
        return (True, exe) if exe else (False, "espeak-ng not installed")

    def synthesize(self, text: str, out: Path, voice: str | None = None, language: str = "en") -> Path:
        exe = _espeak_exe(self.s.espeak_bin if self.s else "")
        if not exe:
            raise ProviderUnavailable("espeak-ng not installed")
        out.parent.mkdir(parents=True, exist_ok=True)
        speed = "160"
        p = subprocess.run([exe, "-v", language, "-s", speed, "-w", str(out), text], capture_output=True, timeout=300)
        if p.returncode != 0 or not out.exists():
            raise ProviderError(p.stderr.decode("utf-8", "replace")[-300:])
        return out
