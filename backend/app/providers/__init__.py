"""Provider registry: builds the manager with every adapter wired to the DB
(usage logging + de-duplication cache)."""
from __future__ import annotations

from ..config import Settings, get_settings
from .comfyui import ComfyAceStepMusic, ComfyClient, ComfyImage, ComfyWanVideo
from .llm import GeminiLLM, OllamaLLM
from .manager import AllProvidersExhausted, ProviderManager
from .motion import MotionComicVideo
from .procedural import ProceduralMusic, ProceduralSfx
from .voice import EspeakVoice, IndicParlerVoice, KokoroVoice, PiperVoice

__all__ = ["build_manager", "get_manager", "AllProvidersExhausted", "ProviderManager"]


def _usage_hook(**kw):
    from ..db import session_scope
    from ..models import ProviderUsage

    with session_scope() as s:
        s.add(ProviderUsage(**kw))


def _cache_get(key: str):
    from ..db import session_scope
    from ..models import GenerationCache

    with session_scope() as s:
        row = s.get(GenerationCache, key)
        return dict(row.result) if row else None


def _cache_put(key: str, provider: str, result: dict):
    from ..db import session_scope
    from ..models import GenerationCache

    with session_scope() as s:
        s.merge(GenerationCache(key=key, provider=provider, result=result))


def build_manager(settings: Settings | None = None, with_db: bool = True) -> ProviderManager:
    s = settings or get_settings()
    comfy = ComfyClient(s.comfyui_url, s.comfy_timeout_s)
    providers = [
        GeminiLLM(s), OllamaLLM(s),
        ComfyImage(s, comfy),
        ComfyWanVideo(s, comfy), MotionComicVideo(),
        KokoroVoice(s), IndicParlerVoice(s), PiperVoice(s), EspeakVoice(s),
        ComfyAceStepMusic(s, comfy), ProceduralMusic(),
        ProceduralSfx(),
    ]
    if with_db:
        return ProviderManager(providers, s, _usage_hook, _cache_get, _cache_put)
    return ProviderManager(providers, s)


_manager: ProviderManager | None = None


def get_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = build_manager()
    return _manager


def set_manager(m: ProviderManager | None) -> None:
    global _manager
    _manager = m
