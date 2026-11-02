"""API tests against a real uvicorn server (inline worker on, test-double AI providers)."""
import socket
import threading
import time

import pytest
import requests
import uvicorn

from app import config


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(test_manager, monkeypatch):
    monkeypatch.setenv("ENGINE_ACCESS_TOKEN", "secret")
    s = config.get_settings()
    s.access_token, s.inline_worker, s.worker_poll_s = "secret", True, 0.2
    from app.main import app

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)


H = {"Authorization": "Bearer secret"}


def test_auth_required(server):
    assert requests.get(f"{server}/api/projects").status_code == 401
    assert requests.get(f"{server}/api/health").status_code == 200


def test_validation(server):
    r = requests.post(f"{server}/api/projects", headers=H, json={"animal": "l", "prompt": "x"})
    assert r.status_code == 422
    r = requests.post(f"{server}/api/projects", headers=H, json={"animal": "lion", "prompt": "a lost cub", "settings": {"duration_s": 5000}})
    assert r.status_code == 422


def test_create_generate_poll_download_and_edit(server):
    r = requests.post(f"{server}/api/projects", headers=H, json={
        "animal": "Lion", "prompt": "A lion cub gets lost in a forest and finds its mother.",
        "settings": {"duration_s": 12, "aspect_ratio": "16:9", "quality": "720p"}})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    for _ in range(600):
        p = requests.get(f"{server}/api/projects/{pid}", headers=H).json()
        if p["job"]["status"] in ("completed", "failed", "paused"):
            break
        time.sleep(0.3)
    assert p["job"]["status"] == "completed", p["job"]
    assert p["final_video"].endswith(".mp4")
    vid = requests.get(f"{server}{p['final_video']}?token=secret")
    assert vid.status_code == 200 and len(vid.content) > 10000

    # system / providers / usage endpoints
    assert "hardware" in requests.get(f"{server}/api/system", headers=H).json()
    assert any(x["name"] == "motion-comic" for x in requests.get(f"{server}/api/providers", headers=H).json())
    assert requests.get(f"{server}/api/usage", headers=H).json()["total_cost_usd"] == 0

    # edit a scene's narration -> voice/video/sfx cleared, then regenerate
    sid = p["scenes"][0]["id"]
    r = requests.put(f"{server}/api/scenes/{sid}", headers=H, json={"narration": "A brand new line for scene one."})
    assert set(r.json()["cleared"]) >= {"voice"}
    r = requests.post(f"{server}/api/projects/{pid}/generate", headers=H)
    assert r.status_code == 200
    for _ in range(600):
        p = requests.get(f"{server}/api/projects/{pid}", headers=H).json()
        if p["job"]["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)
    assert p["job"]["status"] == "completed" and p["final_video"]

    # path traversal blocked
    assert requests.get(f"{server}/files/../../etc/passwd?token=secret").status_code in (400, 404)


def test_upload_rejects_bad_type(server):
    pid = requests.post(f"{server}/api/projects", headers=H, json={"animal": "fox", "prompt": "a clever fox", "auto_start": False}).json()["id"]
    r = requests.post(f"{server}/api/projects/{pid}/reference", headers=H, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_hosted_ui_cors_and_private_network(server):
    origin = "https://animal-video-engine.vercel.app"
    r = requests.options(f"{server}/api/system", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization", "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-private-network") == "true"
    r = requests.options(f"{server}/api/system", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET", "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers  # unknown sites are refused


def test_cast_and_queue_explanation(server):
    from app import db as _db
    from app.models import Job
    r = requests.post(f"{server}/api/projects", headers=H, json={"animal": "Lion", "cast": ["Lion", "Rabbit", "lion"], "prompt": "a lion and a rabbit", "auto_start": False})
    assert r.status_code == 201
    p = r.json()
    assert p["animal"] == "Lion, Rabbit" and p["settings"]["cast"] == ["Lion", "Rabbit"]
    # simulate another video running: a queued job must explain what it waits for
    with _db.session_scope() as s:
        s.add(Job(project_id=p["id"], status="running", stages={"images": {"status": "processing"}}, progress=40))
    other = requests.post(f"{server}/api/projects", headers=H, json={"animal": "Dog", "prompt": "a brave puppy", "auto_start": False}).json()
    with _db.session_scope() as s:
        s.add(Job(project_id=other["id"], status="queued"))
    job = requests.get(f"{server}/api/projects/{other['id']}", headers=H).json()["job"]
    assert job["status"] == "queued" and job["queue"]["position"] == 1
    assert job["queue"]["running"][0]["title"].startswith("Untitled Lion") and job["queue"]["running"][0]["step"] == "images"
    assert job["queue"]["worker_running"] is True
    assert requests.get(f"{server}/api/health").json()["worker_running"] is True
