"""Standard provider interfaces. Every AI backend is an adapter implementing
one of these, so models can be swapped without touching the pipeline."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class ProviderError(Exception):
    """Generic failure; the manager may retry or fall back."""


class ProviderUnavailable(ProviderError):
    """Provider is not installed / not running / not configured."""


class QuotaExceeded(ProviderError):
    """Free quota or rate limit hit. retry_after_s tells when to try again."""

    def __init__(self, msg: str, retry_after_s: float = 60.0):
        super().__init__(msg)
        self.retry_after_s = retry_after_s


@dataclass
class ProviderStatus:
    name: str
    kind: str
    available: bool
    detail: str = ""
    free: bool = True
    local: bool = True
    limits: str = ""
    license: str = ""


class Provider(ABC):
    name: str = ""
    kind: str = ""
    free: bool = True             # paid providers are blocked by the zero-cost policy
    local: bool = True
    estimated_cost_usd: float = 0.0
    limits: str = ""
    license: str = ""
    quality_label: str = ""       # shown in UI, e.g. "AI video" vs "motion comic"

    @abstractmethod
    def check(self) -> tuple[bool, str]:
        """Return (available, detail). Must be cheap and must not spend quota."""

    def supports(self, **request) -> bool:
        """Can this provider handle the request (e.g. language="ta")? Default: yes."""
        return True

    def release(self) -> None:
        """Free models / GPU memory. Called between pipeline stages."""

    def status(self) -> ProviderStatus:
        try:
            ok, detail = self.check()
        except Exception as e:  # never let a status check crash the app
            ok, detail = False, f"check failed: {e}"
        return ProviderStatus(self.name, self.kind, ok, detail, self.free, self.local, self.limits, self.license)


class LLMProvider(Provider):
    kind = "llm"

    @abstractmethod
    def generate_json(self, system: str, prompt: str, temperature: float = 0.8) -> dict:
        """Return a parsed JSON object."""


class ImageProvider(Provider):
    kind = "image"

    @abstractmethod
    def generate(self, prompt: str, negative: str, width: int, height: int, seed: int, out: Path,
                 init_image: Path | None = None, denoise: float = 1.0) -> Path:
        ...


@dataclass
class ClipRequest:
    image: Path
    prompt: str
    duration_s: float
    width: int
    height: int
    fps: int = 24
    camera: str = "slow push in"
    seed: int = 0
    extra: dict = field(default_factory=dict)


class VideoProvider(Provider):
    kind = "video"

    @abstractmethod
    def generate(self, req: ClipRequest, out: Path) -> Path:
        ...


class VoiceProvider(Provider):
    kind = "voice"

    @abstractmethod
    def synthesize(self, text: str, out: Path, voice: str | None = None, language: str = "en") -> Path:
        ...


class MusicProvider(Provider):
    kind = "music"

    @abstractmethod
    def compose(self, description: str, duration_s: float, out: Path, seed: int = 0) -> Path:
        ...


class SfxProvider(Provider):
    kind = "sfx"

    @abstractmethod
    def create(self, cues: list[str], duration_s: float, out: Path, seed: int = 0) -> Path:
        ...
