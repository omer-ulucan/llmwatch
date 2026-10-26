"""
Tests for client IP resolution behind proxies and per-identity rate limits.

WHY: Behind nginx every request arrives from the proxy's address, so keying limits
on the TCP peer put all users into one shared bucket (one heavy user throttled
everyone, and the limit protected nothing per user). X-Forwarded-For must only be
trusted when the peer is a configured proxy, otherwise clients can spoof it.
"""

import hashlib

import pytest
from starlette.requests import Request

from llmwatch.auth.jwt_handler import create_access_token
from llmwatch.config import settings
from llmwatch.rate_limit import client_ip, limiter, rate_limit_key

TRUSTED = "10.0.0.0/8, 172.16.0.0/12"


def make_request(peer: str, headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw,
            "client": (peer, 1234),
        }
    )


@pytest.fixture
def trusted_proxies(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", TRUSTED)


# ── client_ip ───────────────────────────────────────────────


def test_peer_used_when_no_proxy_is_trusted():
    req = make_request("203.0.113.9", {"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req) == "203.0.113.9"


def test_spoofed_forwarded_for_from_untrusted_peer_is_ignored(trusted_proxies):
    req = make_request("203.0.113.9", {"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req) == "203.0.113.9"


def test_forwarded_for_used_when_peer_is_trusted_proxy(trusted_proxies):
    req = make_request("172.18.0.5", {"X-Forwarded-For": "198.51.100.7"})
    assert client_ip(req) == "198.51.100.7"


def test_rightmost_untrusted_hop_wins_over_client_supplied_entries(trusted_proxies):
    # The client sent "X-Forwarded-For: 6.6.6.6"; nginx appended the real address,
    # then an internal load balancer appended nginx's.
    req = make_request(
        "10.0.0.3", {"X-Forwarded-For": "6.6.6.6, 198.51.100.7, 172.18.0.5"}
    )
    assert client_ip(req) == "198.51.100.7"


def test_all_hops_trusted_falls_back_to_leftmost(trusted_proxies):
    req = make_request("10.0.0.3", {"X-Forwarded-For": "10.1.1.1, 172.18.0.5"})
    assert client_ip(req) == "10.1.1.1"


def test_garbage_forwarded_for_from_trusted_proxy_is_not_trusted(trusted_proxies):
    req = make_request("10.0.0.3", {"X-Forwarded-For": "not-an-ip"})
    assert client_ip(req) == "10.0.0.3"


def test_multiple_forwarded_for_headers_are_combined(trusted_proxies):
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"x-forwarded-for", b"6.6.6.6"),
                (b"x-forwarded-for", b"198.51.100.7"),
            ],
            "client": ("10.0.0.3", 1234),
        }
    )
    assert client_ip(req) == "198.51.100.7"


def test_ipv6_peer_and_forwarded_for(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "fd00::/8")
    req = make_request("fd00::5", {"X-Forwarded-For": "2001:db8::1"})
    assert client_ip(req) == "2001:db8::1"


# ── rate_limit_key ──────────────────────────────────────────


def test_api_key_requests_are_keyed_by_key_hash():
    req = make_request("203.0.113.9", {"X-API-Key": "lw_abc"})
    expected = hashlib.sha256(b"lw_abc").hexdigest()[:32]
    assert rate_limit_key(req) == f"key:{expected}"


def test_valid_jwt_requests_are_keyed_by_user():
    token = create_access_token({"sub": "user-1", "company_id": "c1"})
    req = make_request("203.0.113.9", {"Authorization": f"Bearer {token}"})
    assert rate_limit_key(req) == "user:user-1"


def test_invalid_jwt_falls_back_to_client_ip():
    req = make_request("203.0.113.9", {"Authorization": "Bearer garbage"})
    assert rate_limit_key(req) == "ip:203.0.113.9"


def test_anonymous_requests_are_keyed_by_client_ip(trusted_proxies):
    req = make_request("172.18.0.5", {"X-Forwarded-For": "198.51.100.7"})
    assert rate_limit_key(req) == "ip:198.51.100.7"


# ── Endpoint limits ─────────────────────────────────────────


@pytest.fixture
async def proxied(app_db, trusted_proxies, monkeypatch, fake_llm):
    """The real app behind "nginx": every request comes from the proxy address.

    Chat goes to the fake OpenAI-compatible server; auth uses the test database.
    """
    import httpx

    from llmwatch.main import app

    monkeypatch.setattr(settings, "rate_limit_chat", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_per_ip", "1000/minute")
    limiter.reset()
    transport = httpx.ASGITransport(app=app, client=("172.18.0.5", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    limiter.reset()


@pytest.fixture
def new_user(make_account, add_model):
    """An account whose workspace has the fake chat model."""

    async def _new():
        account = await make_account()
        await add_model(account)
        return account

    return _new


async def _chat(client, account, ip: str = "198.51.100.7"):
    return await client.post(
        "/chat/completions",
        json={"prompt": "hello", "model": "fake-model"},
        headers={**account.headers, "X-Forwarded-For": ip},
    )


async def test_chat_completions_is_rate_limited(proxied, new_user):
    alice = await new_user()
    assert (await _chat(proxied, alice)).status_code == 200
    assert (await _chat(proxied, alice)).status_code == 200
    assert (await _chat(proxied, alice)).status_code == 429


async def test_users_behind_the_same_proxy_have_separate_buckets(proxied, new_user):
    """Regression: all users used to share the proxy's IP bucket."""
    alice = await new_user()
    bob = await new_user()
    for _ in range(2):
        assert (await _chat(proxied, alice, ip="198.51.100.7")).status_code == 200
    assert (await _chat(proxied, alice, ip="198.51.100.7")).status_code == 429
    # Bob, a different user from a different address behind the same nginx.
    assert (await _chat(proxied, bob, ip="198.51.100.8")).status_code == 200


async def test_per_ip_limit_still_applies_across_identities(
    proxied, new_user, monkeypatch
):
    """Rotating API keys or accounts from one address doesn't escape the IP cap."""
    monkeypatch.setattr(settings, "rate_limit_chat", "100/minute")
    monkeypatch.setattr(settings, "rate_limit_per_ip", "3/minute")
    users = [await new_user() for _ in range(4)]
    statuses = [(await _chat(proxied, u)).status_code for u in users]
    assert statuses == [200, 200, 200, 429]


async def test_agent_run_is_rate_limited(client, new_user, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_agent", "1/minute")
    alice = await new_user()
    body = {"prompt": "hi", "model": "fake-model", "tools": []}
    first = await client.post("/agent/run", json=body, headers=alice.headers)
    second = await client.post("/agent/run", json=body, headers=alice.headers)
    assert first.status_code == 200
    assert second.status_code == 429


async def test_rate_limit_response_uses_error_envelope(proxied, new_user):
    carol = await new_user()
    for _ in range(2):
        await _chat(proxied, carol)
    resp = await _chat(proxied, carol)
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMITED"
    assert resp.headers["retry-after"] == "60"  # window of the 2/minute limit
