"""Acceptance run: Lion cub, 60 s, 9:16, cinematic 3D, in a given language.

Real: language validation, voice synthesis (eSpeak NG, the voice available in the
build machine), animated montage clips, procedural music + SFX, subtitles with
native fonts, FFmpeg editing, MP4 validation, timings.
Test doubles: the story text (stands in for Gemini) and the images (no image
model in the build machine).

usage: python tests/acceptance_run.py ta [subtitle_lang]
"""
import json
import os
import sys
import time

os.environ.setdefault("DATA_DIR", "/tmp/accept")
os.environ["INLINE_WORKER"] = "false"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config, db  # noqa: E402
from app.models import Job, Project  # noqa: E402
from app.providers import _cache_get, _cache_put, _usage_hook, set_manager  # noqa: E402
from app.providers.manager import ProviderManager  # noqa: E402
from app.providers.motion import MotionComicVideo  # noqa: E402
from app.providers.procedural import ProceduralMusic, ProceduralSfx  # noqa: E402
from app.providers.voice import EspeakVoice, KokoroVoice  # noqa: E402
from app.services import preflight  # noqa: E402
from app.services.pipeline import STAGES  # noqa: E402
from app.storage import absolute  # noqa: E402
from app.worker import claim_next, run_job  # noqa: E402

import conftest  # noqa: E402
import fixtures_lion  # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "ta"
sub = sys.argv[2] if len(sys.argv) > 2 else "same"
db.init_db()
s = config.get_settings()
s.llm_order, s.image_order = ["fake-llm"], ["fake-image"]
s.video_order, s.music_order, s.sfx_order, s.voice_order = ["comfyui-wan", "motion-comic"], ["procedural-score"], ["procedural-sfx"], ["auto"]
providers = [conftest.FakeLLM(fixtures_lion.story(lang, None if sub == "same" else sub)), conftest.FakeImage(),
             MotionComicVideo(), KokoroVoice(s), EspeakVoice(s), ProceduralMusic(), ProceduralSfx()]
set_manager(ProviderManager(providers, s, _usage_hook, _cache_get, _cache_put))

settings = {"duration_s": 60, "aspect_ratio": "9:16", "quality": "720p", "style": "cinematic 3D animation",
            "language": lang, "subtitles": True, "subtitle_language": sub, "motion": "auto"}
pre = preflight.run(settings)
print("PREFLIGHT", json.dumps(pre, ensure_ascii=False))
with db.session_scope() as d:
    p = Project(title="Untitled lion cub", animal="Lion cub", prompt="A lion cub makes a new friend in the forest.", settings=settings)
    d.add(p)
    d.flush()
    j = Job(project_id=p.id, stages={k: {"status": "waiting", "detail": ""} for k in STAGES})
    d.add(j)
    d.flush()
    pid, jid = p.id, j.id
assert claim_next() == jid
t0 = time.time()
result = run_job(jid)
total = time.time() - t0
with db.session_scope() as d:
    p, j = d.get(Project, pid), d.get(Job, jid)
    stages = {k: (v.get("status"), v.get("elapsed_s")) for k, v in j.stages.items()}
    final = next((a for a in p.assets if a.kind == "final"), None)
    print("RESULT", result, "| job:", j.status, j.progress, "|", j.message)
    print("TITLE", p.title)
    print("STAGES", json.dumps(stages))
    print("TOTAL_S", round(total, 1))
    if final:
        print("FINAL", absolute(final.path), json.dumps({k: final.meta[k] for k in ("duration_s", "width", "height", "ok", "problems", "notes")}, ensure_ascii=False))
    print("VOICES", sorted({sc.data.get("voice_provider") for sc in p.scenes}))
    print("CUES", json.dumps(p.scenes[3].data.get("cues"), ensure_ascii=False))
