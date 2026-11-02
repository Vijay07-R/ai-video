"""Test setup. Each test gets an isolated data dir + SQLite DB.

The `fake_*` providers below are TEST DOUBLES used only by the test suite to
exercise the pipeline without AI models. They are never registered by the app.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy.io import wavfile

from app import config, db
from app.providers import set_manager
from app.providers.base import ImageProvider, LLMProvider, QuotaExceeded, VoiceProvider
from app.providers.manager import ProviderManager
from app.providers.motion import MotionComicVideo
from app.providers.procedural import ProceduralMusic, ProceduralSfx


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INLINE_WORKER", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("RENDER_PRESET", "ultrafast")
    config.reset_settings()
    db.reset_engine()
    db.init_db()
    yield
    set_manager(None)
    db.reset_engine()
    config.reset_settings()


STORY = {
    "title": "Little Paws Finds Home",
    "logline": "A lion cub lost in the forest finds his way back to his mother.",
    "analysis": {"genre": "family adventure", "tone": "warm", "audience": "all ages", "themes": ["family"]},
    "visual_style": "cinematic 3D animation",
    "music_theme": "gentle strings, lost then hopeful reunion",
    "characters": [
        {"key": "cub", "name": "Kito", "role": "protagonist", "species": "lion cub", "color": "golden fur",
         "eye_color": "amber", "markings": "faint spots on legs", "voice": "young, curious"},
        {"key": "mother", "name": "Amara", "role": "supporting", "species": "lioness", "color": "tawny fur", "eye_color": "gold"},
    ],
    "scenes": [
        {"number": 1, "duration_s": 4, "description": "Kito wanders into the forest", "characters": ["cub"],
         "environment": "dense forest", "image_prompt": "golden lion cub among tall trees", "video_prompt": "cub walks forward",
         "camera_movement": "slow push in", "narration": "Kito loved to explore.", "sfx": ["birds", "rustle leaves"], "transition": "fade"},
        {"number": 2, "duration_s": 4, "description": "Kito realises he is lost", "characters": ["cub"],
         "environment": "dark forest", "image_prompt": "lonely lion cub at dusk", "camera_movement": "pull out",
         "dialogue": [{"character": "cub", "line": "Mama? Where are you?"}], "sfx": ["wind", "cub mews"], "transition": "dissolve"},
        {"number": 3, "duration_s": 4, "description": "Amara finds him", "characters": ["cub", "mother"],
         "environment": "forest clearing at sunrise", "image_prompt": "lioness nuzzling her cub", "camera_movement": "pan right",
         "narration": "And there she was.", "sfx": ["roar"], "transition": "fadeblack"},
    ],
}


class FakeLLM(LLMProvider):
    name = "fake-llm"

    def __init__(self, story=STORY, quota_first=False):
        self.story, self.calls, self.quota_first = story, 0, quota_first

    def check(self):
        return True, "test double"

    def generate_json(self, system, prompt, temperature=0.8):
        self.calls += 1
        if self.quota_first and self.calls == 1:
            raise QuotaExceeded("test quota", 120)
        return self.story


class FakeImage(ImageProvider):
    name = "fake-image"

    def __init__(self):
        self.calls = 0

    def check(self):
        return True, "test double"

    def generate(self, prompt, negative, width, height, seed, out, init_image=None, denoise=1.0):
        self.calls += 1
        rng = np.random.default_rng(seed)
        img = Image.new("RGB", (width, height), tuple(int(x) for x in rng.integers(30, 120, 3)))
        d = ImageDraw.Draw(img)
        cx, cy, r = width // 2, height // 2, min(width, height) // 4
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(214, 160, 60))  # golden "animal"
        d.ellipse([cx - r // 3, cy - r // 4, cx - r // 6, cy - r // 10], fill=(20, 20, 20))
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        return out


class FakeVoice(VoiceProvider):
    name = "fake-voice"

    def check(self):
        return True, "test double"

    def synthesize(self, text, out, voice=None, language="en"):
        dur = max(0.6, len(text.split()) / 2.5)
        t = np.arange(int(24000 * dur)) / 24000
        sig = 0.3 * np.sin(2 * math.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * math.pi * 3 * t))
        out.parent.mkdir(parents=True, exist_ok=True)
        wavfile.write(str(out), 24000, (sig * 32767).astype(np.int16))
        return out


@pytest.fixture
def test_manager():
    providers = [FakeLLM(), FakeImage(), MotionComicVideo(), FakeVoice(), ProceduralMusic(), ProceduralSfx()]
    s = config.get_settings()
    s.llm_order, s.image_order, s.voice_order = ["fake-llm"], ["fake-image"], ["fake-voice"]
    s.video_order, s.music_order, s.sfx_order = ["motion-comic"], ["procedural-score"], ["procedural-sfx"]
    from app.providers import _cache_get, _cache_put, _usage_hook

    m = ProviderManager(providers, s, _usage_hook, _cache_get, _cache_put)
    set_manager(m)
    return m


def make_project(**settings):
    from app.models import Job, Project
    from app.services.pipeline import STAGES

    st = {"duration_s": 12, "aspect_ratio": "16:9", "quality": "720p", "language": "en", "subtitles": True, **settings}
    with db.session_scope() as s:
        p = Project(title="Untitled lion", animal="lion", prompt="A lion cub gets lost in a forest and finds its mother.", settings=st)
        s.add(p)
        s.flush()
        j = Job(project_id=p.id, stages={k: {"status": "waiting", "detail": ""} for k in STAGES})
        s.add(j)
        s.flush()
        return p.id, j.id


@pytest.fixture
def tiny_png(tmp_path) -> Path:
    p = tmp_path / "img.png"
    Image.new("RGB", (640, 360), (200, 150, 60)).save(p)
    return p
