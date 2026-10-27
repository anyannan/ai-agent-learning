"""鉴权 / 限流 / 配额测试。

这三层的作用是"请求根本到不了 LLM"。所以这里的断言有两条：
1. 该拒的要拒（401 / 429），
2. 拒绝发生在花 token 之前 —— 除了 /quota，测试里不会触发任何模型调用。
"""

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from api import routes
from core.auth import require_api_key
from core.limits import DailyQuota, SlidingWindow

BODY = {"source_name": "demo.py", "source_code": "x = 1\n", "intent": "fix"}


def make_request(host="127.0.0.1") -> Request:
    return Request({"type": "http", "client": (host, 12345), "headers": []})


# ---------- 1. 鉴权：无 key 配置时只放行本机 ----------

def test_no_keys_allows_local(monkeypatch):
    monkeypatch.delenv("AUTOFIX_API_KEYS", raising=False)
    assert require_api_key(make_request("127.0.0.1"), x_api_key="") == "local:127.0.0.1"


def test_no_keys_rejects_remote(monkeypatch):
    monkeypatch.delenv("AUTOFIX_API_KEYS", raising=False)
    with pytest.raises(Exception) as e:
        require_api_key(make_request("203.0.113.9"), x_api_key="")
    assert getattr(e.value, "status_code", None) == 401


# ---------- 2. 鉴权：有 key 时必须带且匹配 ----------

def test_configured_key_required(monkeypatch):
    monkeypatch.setenv("AUTOFIX_API_KEYS", "alpha, beta")
    with pytest.raises(Exception) as e:
        require_api_key(make_request(), x_api_key="")
    assert e.value.status_code == 401

    with pytest.raises(Exception) as e:
        require_api_key(make_request(), x_api_key="wrong")
    assert e.value.status_code == 401

    assert require_api_key(make_request(), x_api_key="beta") == "key:beta"


def test_identity_does_not_leak_full_key(monkeypatch):
    monkeypatch.setenv("AUTOFIX_API_KEYS", "super-secret-key")
    identity = require_api_key(make_request(), x_api_key="super-secret-key")
    assert identity == "key:supe"
    assert "secret" not in identity


# ---------- 3. 限流 ----------

def test_sliding_window_blocks_after_limit():
    limiter = SlidingWindow(limit=3, window_sec=60)
    results = [limiter.allow("k")[0] for _ in range(3)]
    assert results == [True, True, True]
    ok, retry_after = limiter.allow("k")
    assert ok is False and retry_after > 0


def test_sliding_window_is_per_key():
    limiter = SlidingWindow(limit=1, window_sec=60)
    assert limiter.allow("a")[0] is True
    assert limiter.allow("a")[0] is False
    assert limiter.allow("b")[0] is True


def test_zero_limit_blocks_everything():
    """limit=0 是紧急刹车开关，不是"不限"。"""
    assert SlidingWindow(limit=0).allow("k") == (False, 60.0)


# ---------- 4. 配额 ----------

def test_daily_quota_counts_down():
    quota = DailyQuota(limit=2)
    assert quota.consume("k") == (True, 1)
    assert quota.consume("k") == (True, 0)
    assert quota.consume("k") == (False, 0)
    assert quota.remaining("k") == 0


def test_daily_quota_is_per_key():
    quota = DailyQuota(limit=1)
    quota.consume("a")
    assert quota.consume("a")[0] is False
    assert quota.consume("b")[0] is True


# ---------- 5. 接口层：拒绝发生在花 token 之前 ----------

def test_fix_returns_401_without_key(monkeypatch):
    monkeypatch.setenv("AUTOFIX_API_KEYS", "alpha")
    from main import app

    resp = TestClient(app).post("/api/v1/fix", json=BODY)
    assert resp.status_code == 401


def test_fix_returns_429_when_rate_limited(monkeypatch):
    monkeypatch.delenv("AUTOFIX_API_KEYS", raising=False)
    monkeypatch.setattr(routes, "rate_limiter", SlidingWindow(limit=0))
    from main import app

    resp = TestClient(app).post("/api/v1/fix", json=BODY)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_fix_returns_429_when_quota_exhausted(monkeypatch):
    monkeypatch.delenv("AUTOFIX_API_KEYS", raising=False)
    monkeypatch.setattr(routes, "rate_limiter", SlidingWindow(limit=100))
    monkeypatch.setattr(routes, "daily_quota", DailyQuota(limit=0))
    from main import app

    resp = TestClient(app).post("/api/v1/fix", json=BODY)
    assert resp.status_code == 429
    assert "配额" in resp.json()["detail"]


def test_quota_endpoint_reports_remaining(monkeypatch):
    monkeypatch.delenv("AUTOFIX_API_KEYS", raising=False)
    monkeypatch.setattr(routes, "rate_limiter", SlidingWindow(limit=100))
    monkeypatch.setattr(routes, "daily_quota", DailyQuota(limit=5))
    from main import app

    resp = TestClient(app).get("/api/v1/quota")
    assert resp.status_code == 200
    data = resp.json()
    assert data["daily_limit"] == 5
    assert data["remaining_today"] == 5
    assert resp.headers["X-Quota-Remaining"] == "5"


def test_enforce_limits_sets_remaining_header(monkeypatch):
    monkeypatch.setattr(routes, "rate_limiter", SlidingWindow(limit=100))
    monkeypatch.setattr(routes, "daily_quota", DailyQuota(limit=3))

    resp = Response()
    routes._enforce_limits("unit-test", resp)
    assert resp.headers["X-Quota-Remaining"] == "2"
