import pytest

from app import config
from app.providers.base import LLMProvider, ProviderError, ProviderUnavailable, QuotaExceeded
from app.providers.manager import AllProvidersExhausted, ProviderManager


class P(LLMProvider):
    def __init__(self, name, available=True, behaviour=None, free=True, cost=0.0):
        self.name, self._avail, self.behaviour, self.free, self.estimated_cost_usd = name, available, behaviour, free, cost
        self.calls = 0

    def check(self):
        return self._avail, "ok" if self._avail else "down"

    def generate_json(self, system, prompt, temperature=0.8):
        self.calls += 1
        if self.behaviour:
            raise self.behaviour
        return {"from": self.name}


def mgr(*providers, **kw):
    s = config.get_settings()
    s.llm_order = [p.name for p in providers]
    return ProviderManager(list(providers), s, **kw)


def test_first_available_wins():
    a, b = P("a"), P("b")
    r = mgr(a, b).call("llm", lambda p: p.generate_json("", ""))
    assert r.provider == "a" and b.calls == 0


def test_skips_unavailable():
    a, b = P("a", available=False), P("b")
    assert mgr(a, b).call("llm", lambda p: p.generate_json("", "")).provider == "b"
    assert a.calls == 0


def test_quota_triggers_fallback_and_cooldown():
    a, b = P("a", behaviour=QuotaExceeded("429", 300)), P("b")
    m = mgr(a, b)
    assert m.call("llm", lambda p: p.generate_json("", "")).provider == "b"
    assert m.cooldown_remaining("a") > 250
    m.call("llm", lambda p: p.generate_json("", ""))
    assert a.calls == 1  # not retried during cooldown (no duplicate requests)


def test_all_exhausted_reports_retry_time():
    a = P("a", behaviour=QuotaExceeded("429", 90))
    b = P("b", available=False)
    with pytest.raises(AllProvidersExhausted) as e:
        mgr(a, b).call("llm", lambda p: p.generate_json("", ""))
    assert 80 < e.value.retry_after_s <= 90
    assert set(e.value.reasons) == {"a", "b"}


def test_errors_fall_back():
    a, b = P("a", behaviour=ProviderError("boom")), P("b", behaviour=ProviderUnavailable("gone"))
    c = P("c")
    assert mgr(a, b, c).call("llm", lambda p: p.generate_json("", "")).provider == "c"


def test_paid_provider_blocked_by_default():
    paid = P("paid", free=False, cost=0.5)
    free = P("free")
    m = mgr(paid, free)
    assert m.call("llm", lambda p: p.generate_json("", "")).provider == "free"
    assert paid.calls == 0
    with pytest.raises(AllProvidersExhausted) as e:
        m.call("llm", lambda p: p.generate_json("", ""), only=["paid"])
    assert "zero-cost" in str(e.value)


def test_paid_needs_both_optin_and_limit():
    s = config.get_settings()
    s.allow_paid_providers = True
    s.spending_limit_usd = 0
    assert not s.paid_allowed
    s.spending_limit_usd = 5
    assert s.paid_allowed


def test_dedupe_cache():
    store = {}
    a = P("a")
    m = mgr(a, cache_get=store.get, cache_put=lambda k, p, v: store.__setitem__(k, v))
    r1 = m.call("llm", lambda p: p.generate_json("", ""), cache_payload={"q": 1})
    r2 = m.call("llm", lambda p: p.generate_json("", ""), cache_payload={"q": 1})
    assert a.calls == 1 and r2.cached and r2.value == r1.value
