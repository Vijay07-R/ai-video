"""Text intelligence: Gemini free tier first, local Ollama as fallback."""
from __future__ import annotations

import json
import re

import requests

from ..config import Settings
from .base import LLMProvider, ProviderError, ProviderUnavailable, QuotaExceeded

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def parse_json_loose(text: str) -> dict:
    """Parse JSON even when a model wraps it in ```json fences or adds chatter."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError as e:
                raise ProviderError(f"model returned invalid JSON: {e}") from e
        raise ProviderError("model returned no JSON object")


def _retry_after(resp: requests.Response, default: float) -> float:
    try:
        body = resp.json()
        for d in body.get("error", {}).get("details", []):
            if "retryDelay" in d:  # e.g. "37s"
                return float(str(d["retryDelay"]).rstrip("s")) + 1
            # daily quota violations -> wait longer
            for v in d.get("violations", []) or []:
                if "PerDay" in str(v.get("quotaId", "")):
                    return 3600.0
    except Exception:
        pass
    ra = resp.headers.get("Retry-After")
    return float(ra) if ra and ra.isdigit() else default


class GeminiLLM(LLMProvider):
    """Google Gemini API, free tier (Google AI Studio key, no billing account).

    Tries each configured model in order; a 429 on one model moves to the next.
    """
    name = "gemini"
    local = False
    limits = ("Free tier: Flash / Flash-Lite models only, per-model requests-per-minute and requests-per-day "
              "limits (see your project in Google AI Studio). Free-tier prompts may be used by Google to improve products.")
    license = "Google Gemini API Terms (free tier)"
    quality_label = "cloud LLM"

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.s = settings
        self.http = session or requests.Session()
        self._model_cooldown: dict[str, float] = {}

    def check(self) -> tuple[bool, str]:
        if not self.s.gemini_api_key:
            return False, "GEMINI_API_KEY not set"
        return True, f"models: {', '.join(self.s.gemini_models)}"

    def generate_json(self, system: str, prompt: str, temperature: float = 0.8) -> dict:
        import time

        if not self.s.gemini_api_key:
            raise ProviderUnavailable("GEMINI_API_KEY not set")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        }
        last_quota: QuotaExceeded | None = None
        errors = []
        for model in self.s.gemini_models:
            if self._model_cooldown.get(model, 0) > time.time():
                continue
            try:
                r = self.http.post(f"{GEMINI_BASE}/models/{model}:generateContent", json=body,
                                   headers={"x-goog-api-key": self.s.gemini_api_key}, timeout=180)
            except requests.RequestException as e:
                raise ProviderUnavailable(f"network error: {e}") from e
            if r.status_code == 429:
                wait = _retry_after(r, 60.0)
                self._model_cooldown[model] = time.time() + wait
                last_quota = QuotaExceeded(f"{model} rate/quota limit", wait)
                continue
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"API key rejected ({r.status_code})")
            if r.status_code == 404:
                errors.append(f"{model}: not found")
                continue
            if r.status_code >= 400:
                errors.append(f"{model}: HTTP {r.status_code} {r.text[:200]}")
                continue
            data = r.json()
            try:
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            except (KeyError, IndexError) as e:
                reason = data.get("promptFeedback", {}).get("blockReason") or data.get("candidates", [{}])[0].get("finishReason")
                errors.append(f"{model}: empty response ({reason})")
                continue
            return parse_json_loose(text)
        if last_quota and not errors:
            raise last_quota
        if last_quota:
            raise QuotaExceeded(f"{last_quota}; other errors: {'; '.join(errors)}", last_quota.retry_after_s)
        raise ProviderError("; ".join(errors) or "no Gemini model available")


class OllamaLLM(LLMProvider):
    """Local open-weight LLM through Ollama (https://ollama.com). Free, offline."""
    name = "ollama"
    limits = "Runs on your computer; speed depends on CPU/GPU. No quotas."
    license = "Depends on the model (e.g. Gemma terms of use)"
    quality_label = "local LLM"

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.s = settings
        self.http = session or requests.Session()

    def check(self) -> tuple[bool, str]:
        try:
            r = self.http.get(f"{self.s.ollama_url}/api/tags", timeout=3)
            r.raise_for_status()
        except requests.RequestException:
            return False, f"Ollama not running at {self.s.ollama_url}"
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if not any(n == self.s.ollama_model or n.startswith(self.s.ollama_model + ":") for n in names):
            return False, f"model '{self.s.ollama_model}' not pulled (run: ollama pull {self.s.ollama_model})"
        return True, self.s.ollama_model

    def generate_json(self, system: str, prompt: str, temperature: float = 0.8) -> dict:
        try:
            r = self.http.post(f"{self.s.ollama_url}/api/chat", timeout=1800, json={
                "model": self.s.ollama_model, "stream": False, "format": "json",
                "options": {"temperature": temperature, "num_ctx": 8192},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            })
        except requests.RequestException as e:
            raise ProviderUnavailable(f"Ollama unreachable: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
        return parse_json_loose(r.json().get("message", {}).get("content", ""))
