"""End-to-end: user input -> story -> characters -> voice -> images -> clips ->
music -> sfx -> render -> validated MP4, through the real worker and FFmpeg.
LLM, image and voice are test doubles (AI models are not available in CI)."""
from app import db, ffmpeg
from app.models import Job, Project, ProviderUsage, Scene
from app.storage import absolute
from app.worker import claim_next, recover_stale_jobs, run_job

from .conftest import FakeLLM, make_project


def test_full_pipeline_produces_valid_mp4(test_manager):
    pid, jid = make_project(aspect_ratio="9:16")
    assert claim_next() == jid
    assert run_job(jid) == "completed"
    with db.session_scope() as s:
        p, j = s.get(Project, pid), s.get(Job, jid)
        assert j.status == "completed" and j.progress == 100.0
        assert all(v["status"] in ("completed", "skipped") for v in j.stages.values()), j.stages
        assert p.title == "Little Paws Finds Home" and len(p.characters) == 2 and len(p.scenes) == 3
        assert all(c.reference_image for c in p.characters)
        assert all(sc.video_provider == "motion-comic" for sc in p.scenes)
        info = ffmpeg.probe(absolute(p.final_video))
        v = next(x for x in info["streams"] if x["codec_type"] == "video")
        assert (v["width"], v["height"]) == (720, 1280)
        assert any(x["codec_type"] == "audio" for x in info["streams"])
        final = next(a for a in p.assets if a.kind == "final")
        assert final.meta["ok"] and any("animated image montage" in n for n in final.meta["notes"])
        assert s.query(ProviderUsage).filter(ProviderUsage.cost_usd > 0).count() == 0


def test_resume_skips_finished_work(test_manager):
    pid, jid = make_project()
    run_job(jid)
    image = test_manager.providers["fake-image"]
    calls_before = image.calls
    with db.session_scope() as s:
        sc = s.query(Scene).filter(Scene.project_id == pid, Scene.number == 2).one()
        sid = sc.id
    from app.services.pipeline import clear_scene_outputs

    def rerun():
        with db.session_scope() as s:
            j = Job(project_id=pid)
            s.add(j)
            s.flush()
            jid2 = j.id
        assert run_job(jid2) == "completed"

    # unchanged request -> served from the cache, no GPU work
    clear_scene_outputs(pid, sid, ["image"])
    rerun()
    assert image.calls == calls_before
    # "New image" (new variant/seed) -> exactly one scene is redrawn
    with db.session_scope() as s:
        sc = s.get(Scene, sid)
        sc.data = {**sc.data, "variant": 1}
    clear_scene_outputs(pid, sid, ["image"])
    rerun()
    assert image.calls == calls_before + 1
    assert test_manager.providers["fake-llm"].calls == 1  # story not rewritten


def test_quota_pauses_job_then_resumes(test_manager):
    test_manager.providers.clear()
    llm = FakeLLM(quota_first=True)
    from .conftest import FakeImage, FakeVoice
    from app.providers.motion import MotionComicVideo
    from app.providers.procedural import ProceduralMusic, ProceduralSfx
    for p in [llm, FakeImage(), MotionComicVideo(), FakeVoice(), ProceduralMusic(), ProceduralSfx()]:
        test_manager.providers[p.name] = p
    pid, jid = make_project()
    assert run_job(jid) == "paused"
    with db.session_scope() as s:
        j = s.get(Job, jid)
        assert j.status == "paused" and j.resume_after is not None and "quota" in j.message
    test_manager._cooldown.clear()
    assert run_job(jid) == "completed"


def test_cancel_and_approval_gate(test_manager):
    pid, jid = make_project(approve_storyboard=True)
    assert run_job(jid) == "awaiting_approval"
    with db.session_scope() as s:
        assert s.get(Project, pid).status == "awaiting_approval"
        assert not s.get(Project, pid).final_video
        j2 = Job(project_id=pid, params={"approved": True}, cancel_requested=True)
        s.add(j2)
        s.flush()
        j2id = j2.id
    assert run_job(j2id) == "cancelled"


def test_stale_running_jobs_recovered(test_manager):
    pid, jid = make_project()
    with db.session_scope() as s:
        s.get(Job, jid).status = "running"
    assert recover_stale_jobs() == 1
    assert claim_next() == jid
