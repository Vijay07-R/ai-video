"""Engine configuration, loaded from environment variables / .env.

Zero-cost policy is enforced here: paid providers are disabled and the
spending limit is $0 unless the user explicitly changes both settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def _pairs(name: str) -> dict:
    out = {}
    for part in os.getenv(name, "").replace(",", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # --- storage / database ---
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # --- security ---
    # If set, every API call must send "Authorization: Bearer <token>".
    access_token: str = field(default_factory=lambda: os.getenv("ENGINE_ACCESS_TOKEN", ""))
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://animal-video-engine.vercel.app"))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "200")))

    # --- zero-cost policy ---
    allow_paid_providers: bool = field(default_factory=lambda: _bool("ALLOW_PAID_PROVIDERS", False))
    spending_limit_usd: float = field(default_factory=lambda: float(os.getenv("SPENDING_LIMIT_USD", "0")))

    # --- LLM: Gemini free tier (text only) ---
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    # Aliases resolve to Google's current Flash / Flash-Lite models. Override with exact IDs if you prefer.
    gemini_models: list[str] = field(default_factory=lambda: _list("GEMINI_MODELS", "gemini-flash-latest,gemini-flash-lite-latest"))

    # --- LLM: local Ollama fallback ---
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma3:4b"))

    # --- ComfyUI (local image / video / music) ---
    comfyui_url: str = field(default_factory=lambda: os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"))
    comfy_image_checkpoint: str = field(default_factory=lambda: os.getenv("COMFY_IMAGE_CHECKPOINT", "flux1-schnell-fp8.safetensors"))
    comfy_image_steps: int = field(default_factory=lambda: int(os.getenv("COMFY_IMAGE_STEPS", "4")))
    comfy_image_cfg: float = field(default_factory=lambda: float(os.getenv("COMFY_IMAGE_CFG", "1.0")))
    comfy_wan_unet: str = field(default_factory=lambda: os.getenv("COMFY_WAN_UNET", "wan2.2_ti2v_5B_fp16.safetensors"))
    comfy_wan_clip: str = field(default_factory=lambda: os.getenv("COMFY_WAN_CLIP", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"))
    comfy_wan_vae: str = field(default_factory=lambda: os.getenv("COMFY_WAN_VAE", "wan2.2_vae.safetensors"))
    comfy_wan_steps: int = field(default_factory=lambda: int(os.getenv("COMFY_WAN_STEPS", "20")))
    comfy_music_checkpoint: str = field(default_factory=lambda: os.getenv("COMFY_MUSIC_CHECKPOINT", "ace_step_v1_3.5b.safetensors"))
    comfy_timeout_s: int = field(default_factory=lambda: int(os.getenv("COMFY_TIMEOUT_S", "3600")))
    # "auto" = use Wan only when a capable GPU is detected; "on" / "off" to force.
    ai_video_mode: str = field(default_factory=lambda: os.getenv("AI_VIDEO_MODE", "auto"))

    # --- voices ---
    kokoro_voice: str = field(default_factory=lambda: os.getenv("KOKORO_VOICE", "af_heart"))
    kokoro_lang: str = field(default_factory=lambda: os.getenv("KOKORO_LANG", "a"))
    piper_bin: str = field(default_factory=lambda: os.getenv("PIPER_BIN", "piper"))
    piper_model: str = field(default_factory=lambda: os.getenv("PIPER_MODEL", ""))  # legacy: one English voice
    # One Piper voice per language: "ta=C:/voices/ta_IN-x.onnx;te=...;hi=...;en=..."
    piper_voices: dict = field(default_factory=lambda: _pairs("PIPER_VOICES"))
    indic_parler: bool = field(default_factory=lambda: _bool("INDIC_PARLER", True))
    indic_parler_model: str = field(default_factory=lambda: os.getenv("INDIC_PARLER_MODEL", "ai4bharat/indic-parler-tts"))
    espeak_bin: str = field(default_factory=lambda: os.getenv("ESPEAK_BIN", ""))

    # --- provider preference order per kind (first available wins) ---
    llm_order: list[str] = field(default_factory=lambda: _list("LLM_ORDER", "gemini,ollama"))
    image_order: list[str] = field(default_factory=lambda: _list("IMAGE_ORDER", "comfyui-image"))
    video_order: list[str] = field(default_factory=lambda: _list("VIDEO_ORDER", "comfyui-wan,motion-comic"))
    # "auto" = fastest good voice for the language on this hardware (see providers/voice.py)
    voice_order: list[str] = field(default_factory=lambda: _list("VOICE_ORDER", "auto"))
    music_order: list[str] = field(default_factory=lambda: _list("MUSIC_ORDER", "comfyui-acestep,procedural-score"))
    sfx_order: list[str] = field(default_factory=lambda: _list("SFX_ORDER", "procedural-sfx"))

    # --- speed ---
    # AI video (Wan) is used for as many scenes as fit in this budget; the rest use animated montage.
    ai_video_budget_min: float = field(default_factory=lambda: float(os.getenv("AI_VIDEO_BUDGET_MIN", "10")))
    image_long_side: int = field(default_factory=lambda: int(os.getenv("IMAGE_LONG_SIDE", "0")))  # 0 = auto from VRAM
    parallel_jobs: int = field(default_factory=lambda: int(os.getenv("PARALLEL_JOBS", "0")))  # 0 = auto (CPU cores)

    # --- worker ---
    inline_worker: bool = field(default_factory=lambda: _bool("INLINE_WORKER", True))
    worker_poll_s: float = field(default_factory=lambda: float(os.getenv("WORKER_POLL_S", "2")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "2")))

    def __post_init__(self) -> None:
        self.data_dir = self.data_dir.resolve()  # absolute paths keep FFmpeg happy
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "projects").mkdir(exist_ok=True)
        (self.data_dir / "cache").mkdir(exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'engine.db'}"

    @property
    def paid_allowed(self) -> bool:
        """Paid providers need BOTH an explicit opt-in and a non-zero limit."""
        return self.allow_paid_providers and self.spending_limit_usd > 0


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Used by tests to reload settings after changing env vars."""
    global _settings
    _settings = None
