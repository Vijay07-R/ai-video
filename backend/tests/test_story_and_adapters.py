import json

import pytest

from app import config
from app.providers.base import ProviderError, ProviderUnavailable, QuotaExceeded
from app.providers.comfyui import ComfyClient, ComfyImage, ComfyWanVideo, image_workflow, load_override, wan_workflow
from app.providers.llm import GeminiLLM, OllamaLLM, parse_json_loose
from app.services.story import build_prompt, identity_prompt, normalize_story, scene_count

from .conftest import STORY


def test_scene_count_bounds():
    assert scene_count(10) == 3 and scene_count(60) == 12 and scene_count(180) == 24


def test_normalize_scales_durations_and_cleans():
    raw = json.loads(json.dumps(STORY))
    raw["scenes"][1]["characters"] = ["unknown"]
    raw["scenes"][2]["transition"] = "spin-o-rama"
    out = normalize_story(raw, 60, "lion")
    # scenes are 0.5 s longer per crossfade so the finished film is exactly 60 s
    assert abs(sum(s["duration_s"] for s in out["scenes"]) - (60 + 0.5 * 2)) < 0.1
    assert out["scenes"][1]["characters"] == ["cub"]  # unknown key replaced by protagonist
    assert out["scenes"][2]["transition"] == "dissolve"
    assert [s["number"] for s in out["scenes"]] == [1, 2, 3]


def test_normalize_rejects_empty():
    with pytest.raises(ProviderError):
        normalize_story({"characters": [{"key": "a"}], "scenes": []}, 30, "lion")
    with pytest.raises(ProviderError):
        normalize_story({"characters": [], "scenes": [{"image_prompt": "x"}]}, 30, "lion")


def test_identity_prompt_has_traits():
    c = normalize_story(STORY, 12, "lion")["characters"][0]
    p = identity_prompt(c)
    assert "golden fur" in p and "amber" in p and "Kito" in p


def test_build_prompt_contains_requirements():
    system, prompt = build_prompt({"animal": "lion", "prompt": "lost cub", "settings": {"duration_s": 60, "language": "hi"}})
    assert "12 scenes" in prompt and "hi" in prompt and "JSON" in system


def test_parse_json_loose():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Sure! {"a": 2} hope this helps') == {"a": 2}
    with pytest.raises(ProviderError):
        parse_json_loose("no json here")


class Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = code, body or {}, headers or {}, json.dumps(body or {})

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)


def gemini(responses, models=("m1", "m2")):
    s = config.get_settings()
    s.gemini_api_key, s.gemini_models = "test-key", list(models)
    return GeminiLLM(s, Session(responses))


def ok_body(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


def test_gemini_success_uses_header_key_and_json_mode():
    g = gemini([Resp(200, ok_body({"x": 1}))])
    assert g.generate_json("sys", "hi") == {"x": 1}
    url, kw = g.http.calls[0]
    assert url.endswith("/models/m1:generateContent")
    assert kw["headers"]["x-goog-api-key"] == "test-key"
    assert kw["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_429_moves_to_next_model():
    rate = {"error": {"details": [{"retryDelay": "30s"}]}}
    g = gemini([Resp(429, rate), Resp(200, ok_body({"y": 2}))])
    assert g.generate_json("s", "p") == {"y": 2}
    assert g.http.calls[1][0].endswith("/models/m2:generateContent")


def test_gemini_all_models_quota():
    rate = {"error": {"details": [{"retryDelay": "30s"}]}}
    g = gemini([Resp(429, rate), Resp(429, rate)])
    with pytest.raises(QuotaExceeded) as e:
        g.generate_json("s", "p")
    assert e.value.retry_after_s == 31


def test_gemini_bad_key_and_missing_key():
    with pytest.raises(ProviderUnavailable):
        gemini([Resp(403, {})]).generate_json("s", "p")
    s = config.get_settings()
    s.gemini_api_key = ""
    assert GeminiLLM(s).check()[0] is False


def test_ollama_check_reports_missing_model():
    s = config.get_settings()
    o = OllamaLLM(s, Session([Resp(200, {"models": [{"name": "llama3:8b"}]})]))
    ok, detail = o.check()
    assert not ok and "ollama pull" in detail


def test_image_workflow_txt2img_and_img2img():
    s = config.get_settings()
    wf = image_workflow(s, "lion", "bad", 1024, 576, 7, None, 1.0)
    assert wf["3"]["inputs"]["seed"] == 7 and wf["5"]["inputs"]["width"] == 1024
    wf2 = image_workflow(s, "lion", "bad", 1024, 576, 7, "ref.png", 0.8)
    assert "5" not in wf2 and wf2["3"]["inputs"]["latent_image"] == ["11", 0] and wf2["3"]["inputs"]["denoise"] == 0.8


def test_wan_workflow_shape():
    s = config.get_settings()
    wf = wan_workflow(s, "in.png", "walk", "bad", 832, 480, 121, 3, 24)
    assert wf["7"]["class_type"] == "Wan22ImageToVideoLatent" and wf["7"]["inputs"]["length"] == 121
    assert ComfyWanVideo.dims(1280, 720) == (832, 480) and ComfyWanVideo.dims(720, 1280) == (480, 832)


def test_workflow_override_placeholders(tmp_path, monkeypatch):
    from app.providers import comfyui
    monkeypatch.setattr(comfyui, "WORKFLOW_DIR", tmp_path)
    (tmp_path / "image.json").write_text('{"1": {"inputs": {"text": "{{prompt}}", "seed": "{{seed}}"}}}')
    wf = load_override("image", {"prompt": 'a "lion"', "seed": 5})
    assert wf["1"]["inputs"] == {"text": 'a "lion"', "seed": 5}


def test_comfy_unreachable_is_unavailable():
    s = config.get_settings()
    s.comfyui_url = "http://127.0.0.1:9"  # nothing listens here
    ok, detail = ComfyImage(s, ComfyClient(s.comfyui_url)).check()
    assert not ok and "not reachable" in detail


def test_wan_auto_mode_respects_hardware(monkeypatch):
    from app.providers import comfyui
    s = config.get_settings()
    s.ai_video_mode = "auto"
    monkeypatch.setattr(comfyui, "inspect_hardware", lambda: {"tier": "cpu"})
    ok, detail = ComfyWanVideo(s).check()
    assert not ok and "cpu" in detail
