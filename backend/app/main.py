"""FastAPI application: REST API + file serving + (optional) built frontend."""
from __future__ import annotations

import inspect
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .config import BASE_DIR, get_settings
from .db import get_db, init_db
from .hardware import inspect_hardware
from .models import Asset, Character, ErrorLog, Job, Project, ProviderUsage, Scene
from .providers import get_manager
from .schemas import CharacterUpdate, ProjectCreate, ProjectUpdate, RegenerateRequest, SceneUpdate, VideoSettings
from .services import preflight
from .services.pipeline import STAGES, WEIGHTS, clear_scene_outputs
from .services.story import identity_prompt
from .storage import absolute, project_dir, rel
from .worker import Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
ACTIVE = ("queued", "running", "paused")
UPLOAD_EXT = {".mp4", ".mov", ".webm", ".mkv", ".png", ".jpg", ".jpeg", ".webp"}
_worker: Worker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker
    init_db()
    if get_settings().inline_worker:
        _worker = Worker()
        _worker.start()
    yield
    if _worker:
        _worker.stop()


app = FastAPI(title="Animal Video Engine", version="1.0.0", lifespan=lifespan)
_cors = dict(allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])
_native_pna = "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters
if _native_pna:  # newer Starlette answers Chrome's local-network preflight itself
    _cors["allow_private_network"] = True
app.add_middleware(CORSMiddleware, **_cors)


class PrivateNetworkAccess:
    """Chrome asks before a public site (e.g. the UI on Vercel) talks to localhost.
    Answer that preflight, but only for origins already allowed by CORS_ORIGINS."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        origin = headers.get(b"origin", b"").decode()
        wants = headers.get(b"access-control-request-private-network") == b"true"
        allowed = wants and origin in get_settings().cors_origins

        async def _send(message):
            if allowed and message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"access-control-allow-private-network", b"true")]
            await send(message)

        await self.app(scope, receive, _send)


if not _native_pna:
    app.add_middleware(PrivateNetworkAccess)


def auth(request: Request) -> None:
    token = get_settings().access_token
    if not token:
        return
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or request.query_params.get("token", "")
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(401, "missing or invalid access token")


# ------------------------------------------------------------------ serializers
def _file_url(path: str | None) -> str | None:
    return f"/files/{path}" if path else None


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _history(db: Session) -> dict[str, float]:
    """Measured seconds per scene for each stage, averaged over recent completed jobs."""
    rows = db.query(Job).filter(Job.status == "completed").order_by(Job.created_at.desc()).limit(10).all()
    acc: dict[str, list[float]] = {}
    for r in rows:
        n = max(1, max((v.get("total") or 0) for v in (r.stages or {}).values()) if r.stages else 1)
        for k, v in (r.stages or {}).items():
            if v.get("status") == "completed" and "elapsed_s" in v:
                acc.setdefault(k, []).append(v["elapsed_s"] / n)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def eta_seconds(j: Job, db: Session | None) -> float | None:
    """Remaining time from measurements only; None when not measurable yet (no guessing)."""
    if j.status != "running" or not j.stages:
        return None
    hist = _history(db) if db else {}
    scenes = max([v.get("total") or 0 for v in j.stages.values()] + [1])
    remaining = 0.0
    for k in STAGES:
        v = j.stages.get(k, {})
        st = v.get("status")
        if st in ("completed", "skipped"):
            continue
        if st == "processing" and v.get("done") and v.get("total"):
            remaining += v.get("elapsed_s", 0) / v["done"] * (v["total"] - v["done"])
        elif k in hist:
            remaining += hist[k] * scenes
        elif WEIGHTS[k] >= 4:  # a significant stage we have never measured
            return None
    return round(remaining)


STALL_MIN = 15


def stalled_minutes(j: Job) -> int | None:
    """Minutes since a RUNNING job last reported progress, if suspiciously long."""
    if j.status != "running" or not j.updated_at:
        return None
    mins = (datetime.now(timezone.utc) - _aware(j.updated_at)).total_seconds() / 60
    return int(mins) if mins >= STALL_MIN else None


def queue_info(j: Job, db: Session | None) -> dict | None:
    """Why a queued job is waiting: the video(s) ahead of it, or a worker that is not running."""
    if j.status != "queued" or db is None:
        return None
    from .worker import HEARTBEAT
    import time as _t

    running = db.query(Job).filter(Job.status == "running").all()
    ahead = db.query(Job).filter(Job.status == "queued", Job.created_at < j.created_at).count()
    worker_ok = not get_settings().inline_worker or (_t.time() - HEARTBEAT["t"]) < 30
    blocking = []
    for r in running:
        p = db.get(Project, r.project_id)
        step = next((k for k, v in (r.stages or {}).items() if v.get("status") == "processing"), None)
        blocking.append({"job_id": r.id, "project_id": r.project_id, "title": p.title if p else "?",
                         "step": step, "progress": r.progress, "stalled_min": stalled_minutes(r)})
    return {"position": ahead + 1, "running": blocking, "worker_running": worker_ok}


def job_out(j: Job | None, db: Session | None = None) -> dict | None:
    if not j:
        return None
    now = datetime.now(timezone.utc)
    started, finished = _aware(j.started_at), _aware(j.finished_at)
    elapsed = ((finished or now) - started).total_seconds() if started else None
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "message": j.message,
            "queue": queue_info(j, db), "stalled_min": stalled_minutes(j),
            "stages": {k: (j.stages or {}).get(k, {"status": "waiting", "detail": ""}) for k in STAGES},
            "attempts": j.attempts, "resume_after": j.resume_after.isoformat() if j.resume_after else None,
            "elapsed_s": round(elapsed) if elapsed is not None else None, "eta_s": eta_seconds(j, db),
            "created_at": j.created_at.isoformat(), "updated_at": j.updated_at.isoformat() if j.updated_at else None}


def project_out(p: Project, full: bool = False, db: Session | None = None) -> dict:
    latest = max(p.jobs, key=lambda j: j.created_at) if p.jobs else None
    thumb = next((s.image_path for s in p.scenes if s.image_path), None)
    d = {"id": p.id, "title": p.title, "animal": p.animal, "prompt": p.prompt, "status": p.status, "settings": p.settings,
         "final_video": _file_url(p.final_video), "thumbnail": _file_url(thumb), "created_at": p.created_at.isoformat(),
         "scene_count": len(p.scenes), "job": job_out(latest, db)}
    if full:
        d.update({
            "script": p.script, "reference_url": p.reference_url, "reference_file": _file_url(p.reference_file), "story": p.story,
            "characters": [{"id": c.id, "key": c.key, "name": c.name, "profile": c.profile, "identity_prompt": c.identity_prompt,
                            "reference_image": _file_url(c.reference_image)} for c in p.characters],
            "scenes": [{"id": s.id, "number": s.number, "duration_s": s.duration_s, "data": s.data, "status": s.status,
                        "image": _file_url(s.image_path), "video": _file_url(s.video_path), "voice": _file_url(s.voice_path),
                        "sfx": _file_url(s.sfx_path), "video_provider": s.video_provider,
                        "consistency_score": s.consistency_score, "consistency_flag": s.consistency_flag} for s in p.scenes],
        })
    return d


def _get_project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def _queue(db: Session, p: Project, kind: str = "generate", params: dict | None = None) -> Job:
    check = preflight.run(p.settings or {})
    if not check["ok"]:
        raise HTTPException(422, {"message": "The video cannot be generated yet.", **check})
    active = db.query(Job).filter(Job.project_id == p.id, Job.status.in_(ACTIVE)).first()
    if active:
        if active.status == "paused":  # resume the paused job instead of stacking another
            active.status, active.resume_after, active.cancel_requested = "queued", None, False
            if params:
                active.params = {**(active.params or {}), **params}
            db.commit()
            return active
        raise HTTPException(409, "a job is already running for this project")
    job = Job(project_id=p.id, kind=kind, params=params or {}, stages={k: {"status": "waiting", "detail": ""} for k in STAGES})
    p.status = "queued"
    db.add(job)
    db.commit()
    return job


# ------------------------------------------------------------------ system
@app.get("/api/health")
def health():
    from .worker import HEARTBEAT
    import time as _t

    return {"ok": True, "worker_running": not get_settings().inline_worker or (_t.time() - HEARTBEAT["t"]) < 30}


@app.get("/api/jobs", dependencies=[Depends(auth)])
def list_jobs(db: Session = Depends(get_db)):
    """Active jobs (running, queued, paused) across all projects."""
    rows = db.query(Job).filter(Job.status.in_(("running", "queued", "paused", "awaiting_approval"))).order_by(Job.created_at).all()
    return [{**job_out(r, db), "project_id": r.project_id, "title": (db.get(Project, r.project_id).title if db.get(Project, r.project_id) else "?")}
            for r in rows]


@app.get("/api/system", dependencies=[Depends(auth)])
def system():
    s = get_settings()
    return {
        "hardware": inspect_hardware(),
        "cost_policy": {"spending_limit_usd": s.spending_limit_usd, "paid_providers_allowed": s.paid_allowed,
                        "statement": "Zero-cost mode: only free/local providers are used. No paid API is ever called automatically."},
        "comfyui_url": s.comfyui_url, "ai_video_mode": s.ai_video_mode,
        "orders": {k: getattr(s, f"{k}_order") for k in ("llm", "image", "video", "voice", "music", "sfx")},
    }


@app.get("/api/languages", dependencies=[Depends(auth)])
def langs():
    return preflight.language_report()


@app.post("/api/preflight", dependencies=[Depends(auth)])
def preflight_check(body: VideoSettings):
    return preflight.run(body.model_dump())


@app.get("/api/providers", dependencies=[Depends(auth)])
def providers():
    return get_manager().statuses()


@app.get("/api/usage", dependencies=[Depends(auth)])
def usage(db: Session = Depends(get_db)):
    rows = db.query(ProviderUsage.provider, ProviderUsage.kind, func.count(), func.sum(ProviderUsage.duration_s),
                    func.sum(ProviderUsage.cost_usd), func.sum(case((ProviderUsage.cached.is_(True), 1), else_=0))) \
        .group_by(ProviderUsage.provider, ProviderUsage.kind).all()
    fails = dict(db.query(ProviderUsage.provider, func.count()).filter(ProviderUsage.ok.is_(False)).group_by(ProviderUsage.provider).all())
    items = [{"provider": r[0], "kind": r[1], "calls": r[2], "seconds": round(r[3] or 0, 1), "cost_usd": round(r[4] or 0, 4),
              "cached": int(r[5] or 0), "failures": fails.get(r[0], 0)} for r in rows]
    return {"total_cost_usd": round(sum(i["cost_usd"] for i in items), 4), "items": items}


@app.get("/api/errors", dependencies=[Depends(auth)])
def errors(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(ErrorLog).order_by(ErrorLog.id.desc()).limit(min(limit, 200)).all()
    return [{"id": e.id, "project_id": e.project_id, "job_id": e.job_id, "where": e.where, "message": e.message,
             "created_at": e.created_at.isoformat()} for e in rows]


# ------------------------------------------------------------------ projects
@app.get("/api/projects", dependencies=[Depends(auth)])
def list_projects(db: Session = Depends(get_db)):
    return [project_out(p) for p in db.query(Project).order_by(Project.created_at.desc()).all()]


@app.post("/api/projects", dependencies=[Depends(auth)], status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    cast = body.cast or [a.strip() for a in body.animal.split(",") if a.strip()]
    p = Project(title=body.title or f"Untitled {cast[0] if cast else body.animal}", animal=", ".join(cast) or body.animal.strip(),
                prompt=body.prompt.strip(), script=(body.script or "").strip() or None, reference_url=body.reference_url,
                settings={**body.settings.model_dump(), "cast": cast})
    db.add(p)
    db.commit()
    project_dir(p.id)
    pre = None
    if body.auto_start:
        try:
            _queue(db, p)
        except HTTPException as e:
            if e.status_code != 422:
                raise
            pre = e.detail
            p.status = "blocked"
            db.commit()
    db.refresh(p)
    return {**project_out(p, full=True, db=db), "preflight": pre}


@app.get("/api/projects/{pid}", dependencies=[Depends(auth)])
def get_project(pid: str, db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    out = project_out(p, full=True, db=db)
    if not out["job"] or out["job"]["status"] in ("failed", "cancelled", "paused") or p.status == "blocked":
        out["preflight"] = preflight.run(p.settings or {})
    return out


@app.patch("/api/projects/{pid}", dependencies=[Depends(auth)])
def update_project(pid: str, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    story_inputs_changed = False
    if body.title is not None:
        p.title = body.title
    if body.prompt is not None and body.prompt != p.prompt:
        p.prompt, story_inputs_changed = body.prompt, True
    if body.script is not None and body.script != (p.script or ""):
        p.script, story_inputs_changed = body.script or None, True
    if body.settings is not None:
        old = p.settings or {}
        new = body.settings.model_dump()
        if any(old.get(k) != new[k] for k in ("duration_s", "language", "style", "subtitle_language")):
            story_inputs_changed = True
        p.settings = {**old, **new}
    if story_inputs_changed:  # next run writes a fresh story
        p.story, p.final_video = None, None
        for c in list(p.characters):
            db.delete(c)
        for s in list(p.scenes):
            db.delete(s)
    db.commit()
    return project_out(p, full=True)


@app.delete("/api/projects/{pid}", dependencies=[Depends(auth)], status_code=204)
def delete_project(pid: str, db: Session = Depends(get_db)):
    import shutil

    p = _get_project(db, pid)
    if any(j.status == "running" for j in p.jobs):
        raise HTTPException(409, "cancel the running job first")
    db.delete(p)
    db.commit()
    shutil.rmtree(project_dir(pid), ignore_errors=True)


@app.post("/api/projects/{pid}/reference", dependencies=[Depends(auth)])
async def upload_reference(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in UPLOAD_EXT:
        raise HTTPException(400, f"unsupported file type {ext}; allowed: {', '.join(sorted(UPLOAD_EXT))}")
    limit = get_settings().max_upload_mb * 2**20
    dest = project_dir(pid) / "uploads" / f"reference_{uuid.uuid4().hex[:8]}{ext}"
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"file larger than {get_settings().max_upload_mb} MB")
            f.write(chunk)
    p.reference_file = rel(dest)
    p.settings = {k: v for k, v in (p.settings or {}).items() if k not in ("reference_analysis", "reference_notes")}
    db.add(Asset(project_id=pid, kind="reference", path=rel(dest), meta={"original_name": file.filename}))
    db.commit()
    return {"reference_file": _file_url(p.reference_file)}


@app.post("/api/projects/{pid}/generate", dependencies=[Depends(auth)])
def generate(pid: str, db: Session = Depends(get_db)):
    return job_out(_queue(db, _get_project(db, pid)))


@app.post("/api/projects/{pid}/approve", dependencies=[Depends(auth)])
def approve(pid: str, db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    if p.status != "awaiting_approval":
        raise HTTPException(400, "project is not waiting for approval")
    return job_out(_queue(db, p, params={"approved": True}))


@app.get("/api/projects/{pid}/assets", dependencies=[Depends(auth)])
def assets(pid: str, db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    return [{"id": a.id, "kind": a.kind, "url": _file_url(a.path), "provider": a.provider, "meta": a.meta,
             "created_at": a.created_at.isoformat()} for a in sorted(p.assets, key=lambda a: a.created_at, reverse=True)
            if absolute(a.path).exists()]


@app.get("/api/assets", dependencies=[Depends(auth)])
def all_assets(kind: str | None = None, db: Session = Depends(get_db), limit: int = 200):
    q = db.query(Asset).order_by(Asset.created_at.desc())
    if kind:
        q = q.filter(Asset.kind == kind)
    return [{"id": a.id, "project_id": a.project_id, "kind": a.kind, "url": _file_url(a.path), "provider": a.provider,
             "meta": a.meta, "created_at": a.created_at.isoformat()} for a in q.limit(min(limit, 1000)).all()]


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs/{jid}", dependencies=[Depends(auth)])
def get_job(jid: str, db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "job not found")
    return job_out(j, db)


@app.post("/api/jobs/{jid}/cancel", dependencies=[Depends(auth)])
def cancel_job(jid: str, db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "job not found")
    if j.status == "running":
        j.cancel_requested = True
        j.message = "Cancelling after the current step..."
    elif j.status in ("queued", "paused"):
        j.status, j.message = "cancelled", "Cancelled by user."
        db.get(Project, j.project_id).status = "cancelled"
    db.commit()
    return job_out(j)


@app.post("/api/jobs/{jid}/resume", dependencies=[Depends(auth)])
def resume_job(jid: str, db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404, "job not found")
    get_manager()._cooldown.clear()  # user asked to retry now
    return job_out(_queue(db, db.get(Project, j.project_id)))


# ------------------------------------------------------------------ scenes / characters
@app.put("/api/scenes/{sid}", dependencies=[Depends(auth)])
def update_scene(sid: str, body: SceneUpdate, db: Session = Depends(get_db)):
    sc = db.get(Scene, sid)
    if not sc:
        raise HTTPException(404, "scene not found")
    changes = body.model_dump(exclude_none=True)
    data = {**sc.data, **changes}
    sc.data = data
    if "duration_s" in changes:
        sc.duration_s = changes["duration_s"]
    db.commit()
    parts = set()
    if {"image_prompt", "camera_angle", "lighting", "description"} & changes.keys():
        parts |= {"image", "video"}
    if {"video_prompt", "camera_movement", "duration_s"} & changes.keys():
        parts.add("video")
    if "narration" in changes:
        parts.add("voice")
    if "sfx" in changes or "duration_s" in changes:
        parts.add("sfx")
    if parts:
        clear_scene_outputs(sc.project_id, sid, sorted(parts))
    else:
        db.get(Project, sc.project_id).final_video = None
        db.commit()
    db.refresh(sc)
    return {"id": sc.id, "data": sc.data, "cleared": sorted(parts)}


@app.post("/api/scenes/{sid}/regenerate", dependencies=[Depends(auth)])
def regenerate_scene(sid: str, body: RegenerateRequest, db: Session = Depends(get_db)):
    sc = db.get(Scene, sid)
    if not sc:
        raise HTTPException(404, "scene not found")
    if "image" in body.parts:  # new seed so the image actually changes
        sc.data = {**sc.data, "variant": int(sc.data.get("variant", 0)) + 1, "image_prompt": sc.data["image_prompt"]}
        db.commit()
    clear_scene_outputs(sc.project_id, sid, list(body.parts))
    db.expire_all()
    return job_out(_queue(db, db.get(Project, sc.project_id), kind="regenerate_scene", params={"scene_id": sid, "parts": body.parts}))


@app.put("/api/characters/{cid}", dependencies=[Depends(auth)])
def update_character(cid: str, body: CharacterUpdate, db: Session = Depends(get_db)):
    c = db.get(Character, cid)
    if not c:
        raise HTTPException(404, "character not found")
    changes = body.model_dump(exclude_none=True)
    c.profile = {**c.profile, **changes}
    if "name" in changes:
        c.name = changes["name"]
    c.identity_prompt = identity_prompt(c.profile)
    c.reference_image = None  # redesign; scenes with this character must be redrawn
    p = db.get(Project, c.project_id)
    db.commit()
    for sc in p.scenes:
        if c.key in (sc.data.get("characters") or []):
            clear_scene_outputs(p.id, sc.id, ["image"])
    return {"id": c.id, "profile": c.profile, "identity_prompt": c.identity_prompt}


# ------------------------------------------------------------------ files + frontend
@app.get("/files/{path:path}", dependencies=[Depends(auth)])
def files(path: str):
    try:
        p = absolute(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not p.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(p)


@app.exception_handler(ValueError)
async def value_error(_, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


_dist = BASE_DIR.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
