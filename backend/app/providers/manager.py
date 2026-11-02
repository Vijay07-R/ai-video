"""Automatic Free Provider Manager.

- Tries providers of a kind in the configured preference order.
- Skips unavailable providers and providers cooling down after a quota/rate-limit hit.
- Never uses a paid provider unless ALLOW_PAID_PROVIDERS=true AND SPENDING_LIMIT_USD > 0.
- De-duplicates identical requests through a persistent cache (saves free quota).
- Raises AllProvidersExhausted (with the earliest retry time) so the job can pause
  and notify the user instead of failing or silently switching to something paid.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings, get_settings
from .base import Provider, ProviderError, ProviderUnavailable, QuotaExceeded

log = logging.getLogger("providers")


class AllProvidersExhausted(Exception):
    def __init__(self, kind: str, reasons: dict[str, str], retry_after_s: float | None):
        self.kind = kind
        self.reasons = reasons
        self.retry_after_s = retry_after_s
        msg = f"No free {kind} provider available: " + "; ".join(f"{k}: {v}" for k, v in reasons.items())
        super().__init__(msg)


class PaidProviderBlocked(ProviderError):
    pass


@dataclass
class CallResult:
    provider: str
    value: Any
    cached: bool = False


class ProviderManager:
    STATUS_TTL_S = 30.0

    def __init__(self, providers: list[Provider], settings: Settings | None = None,
                 usage_hook: Callable[..., None] | None = None,
                 cache_get: Callable[[str], dict | None] | None = None,
                 cache_put: Callable[[str, str, dict], None] | None = None):
        self.settings = settings or get_settings()
        self.providers = {p.name: p for p in providers}
        self._cooldown: dict[str, float] = {}
        self._status_cache: dict[str, tuple[float, bool, str]] = {}
        self._lock = threading.Lock()
        self._usage_hook = usage_hook
        self._cache_get = cache_get
        self._cache_put = cache_put

    # ------------------------------------------------------------------ helpers
    def order(self, kind: str) -> list[Provider]:
        names = getattr(self.settings, f"{kind}_order", [])
        if names == ["auto"]:  # rank by hardware: e.g. GPU-heavy voices first only when CUDA exists
            from ..hardware import inspect_hardware
            key = "gpu_rank" if inspect_hardware().get("cuda") else "cpu_rank"
            return sorted((p for p in self.providers.values() if p.kind == kind), key=lambda p: getattr(p, key, 100))
        ordered = [self.providers[n] for n in names if n in self.providers and self.providers[n].kind == kind]
        # any registered provider of this kind not in the order list goes last
        ordered += [p for p in self.providers.values() if p.kind == kind and p not in ordered]
        return ordered

    def is_available(self, p: Provider, force: bool = False) -> tuple[bool, str]:
        now = time.time()
        cached = self._status_cache.get(p.name)
        if cached and not force and now - cached[0] < self.STATUS_TTL_S:
            return cached[1], cached[2]
        st = p.status()
        self._status_cache[p.name] = (now, st.available, st.detail)
        return st.available, st.detail

    def cooldown_remaining(self, name: str) -> float:
        return max(0.0, self._cooldown.get(name, 0.0) - time.time())

    def _check_cost_policy(self, p: Provider) -> None:
        if p.free and p.estimated_cost_usd == 0:
            return
        if not self.settings.paid_allowed:
            raise PaidProviderBlocked(f"{p.name} is a paid provider; blocked by zero-cost policy")
        if p.estimated_cost_usd > self.settings.spending_limit_usd:
            raise PaidProviderBlocked(f"{p.name} estimated ${p.estimated_cost_usd:.2f} exceeds limit")

    @staticmethod
    def cache_key(kind: str, provider: str, payload: dict) -> str:
        raw = json.dumps({"k": kind, "p": provider, "d": payload}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _record(self, **kw) -> None:
        if self._usage_hook:
            try:
                self._usage_hook(**kw)
            except Exception:  # usage logging must never break generation
                log.exception("usage hook failed")

    # --------------------------------------------------------------------- call
    def call(self, kind: str, fn: Callable[[Provider], Any], *, cache_payload: dict | None = None,
             serialize: Callable[[Any], dict] | None = None, deserialize: Callable[[dict], Any] | None = None,
             project_id: str | None = None, only: list[str] | None = None, needs: dict | None = None) -> CallResult:
        """Run fn(provider) on the first provider that works.

        cache_payload: if given, identical (kind, provider, payload) calls reuse the stored result.
        """
        reasons: dict[str, str] = {}
        earliest_retry: float | None = None
        candidates = self.order(kind)
        if only:
            candidates = [p for p in candidates if p.name in only]
        if needs:
            unsupported = [p for p in candidates if not p.supports(**needs)]
            for p in unsupported:
                reasons[p.name] = "does not support " + ", ".join(f"{k}={v}" for k, v in needs.items())
            candidates = [p for p in candidates if p.supports(**needs)]
            if not candidates:
                raise AllProvidersExhausted(kind, reasons, None)
        if not candidates:
            raise AllProvidersExhausted(kind, {"-": "no providers registered"}, None)

        for p in candidates:
            try:
                self._check_cost_policy(p)
            except PaidProviderBlocked as e:
                reasons[p.name] = str(e)
                continue
            wait = self.cooldown_remaining(p.name)
            if wait > 0:
                reasons[p.name] = f"quota cooldown, retry in {int(wait)}s"
                earliest_retry = wait if earliest_retry is None else min(earliest_retry, wait)
                continue
            ok, detail = self.is_available(p)
            if not ok:
                reasons[p.name] = f"unavailable ({detail})"
                continue

            key = None
            if cache_payload is not None and self._cache_get:
                key = self.cache_key(kind, p.name, cache_payload)
                hit = self._cache_get(key)
                if hit is not None:
                    value = deserialize(hit) if deserialize else hit
                    if value is not None:
                        self._record(provider=p.name, kind=kind, project_id=project_id, ok=True, cached=True, duration_s=0.0)
                        return CallResult(p.name, value, cached=True)

            t0 = time.time()
            try:
                value = fn(p)
            except QuotaExceeded as e:
                with self._lock:
                    self._cooldown[p.name] = time.time() + e.retry_after_s
                reasons[p.name] = f"quota/rate limit: {e}"
                earliest_retry = e.retry_after_s if earliest_retry is None else min(earliest_retry, e.retry_after_s)
                self._record(provider=p.name, kind=kind, project_id=project_id, ok=False, duration_s=time.time() - t0, error=str(e))
                continue
            except ProviderUnavailable as e:
                self._status_cache[p.name] = (time.time(), False, str(e))
                reasons[p.name] = f"unavailable ({e})"
                self._record(provider=p.name, kind=kind, project_id=project_id, ok=False, duration_s=time.time() - t0, error=str(e))
                continue
            except ProviderError as e:
                reasons[p.name] = f"error: {e}"
                self._record(provider=p.name, kind=kind, project_id=project_id, ok=False, duration_s=time.time() - t0, error=str(e))
                continue

            self._record(provider=p.name, kind=kind, project_id=project_id, ok=True, duration_s=time.time() - t0,
                         cost_usd=p.estimated_cost_usd)
            if key and self._cache_put:
                try:
                    self._cache_put(key, p.name, serialize(value) if serialize else value)
                except Exception:
                    log.exception("cache write failed")
            return CallResult(p.name, value)

        raise AllProvidersExhausted(kind, reasons, earliest_retry)

    def first_available(self, kind: str, **needs) -> tuple[Provider | None, dict[str, str]]:
        """Which provider WOULD be used (no generation, no quota spent)."""
        reasons = {}
        for p in self.order(kind):
            if needs and not p.supports(**needs):
                reasons[p.name] = "does not support " + ", ".join(f"{v}" for v in needs.values())
                continue
            if not (p.free and p.estimated_cost_usd == 0) and not self.settings.paid_allowed:
                reasons[p.name] = "paid (blocked)"
                continue
            ok, detail = self.is_available(p)
            if ok:
                return p, reasons
            reasons[p.name] = detail
        return None, reasons

    def release(self, kind: str | None = None) -> None:
        for p in self.providers.values():
            if kind is None or p.kind == kind:
                try:
                    p.release()
                except Exception:
                    log.exception("release failed for %s", p.name)

    def statuses(self) -> list[dict]:
        out = []
        for p in self.providers.values():
            ok, detail = self.is_available(p, force=True)
            out.append({
                "name": p.name, "kind": p.kind, "available": ok, "detail": detail, "free": p.free,
                "local": p.local, "limits": p.limits, "license": p.license, "quality": p.quality_label,
                "estimated_cost_usd": p.estimated_cost_usd, "cooldown_s": int(self.cooldown_remaining(p.name)),
                "blocked_by_cost_policy": not (p.free and p.estimated_cost_usd == 0) and not self.settings.paid_allowed,
                "languages": sorted(getattr(p, "languages", []) or []),
            })
        return out
