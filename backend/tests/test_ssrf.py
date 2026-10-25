"""
Tests for the SSRF guard (security/ssrf.py) and the doc_analyzer tool that uses it.

WHY: The agent's URL-fetch tool takes URLs chosen by an LLM, which can be steered by
prompt injection. Without a guard it can read cloud metadata (169.254.169.254),
localhost services and private networks. These tests use a fake DNS resolver and an
httpx transport stub, so no real network access happens. See also the tool-level
regression tests in test_tools.py that hit a throwaway server bound to 127.0.0.1.
"""

import asyncio
import ipaddress

import httpx
import pytest

from llmwatch.security.ssrf import (
    BlockedURLError,
    host_is_allowlisted,
    is_blocked_ip,
    safe_fetch,
)

PUBLIC_V4 = "93.184.215.14"
PUBLIC_V4_B = "93.184.215.15"


class FakeResolver:
    """Maps hostnames to a sequence of answers; records every lookup."""

    def __init__(self, answers: dict[str, list[list[str]] | list[str]]):
        self._answers = {}
        for host, value in answers.items():
            # A flat list means "always answer this"; a list of lists is a sequence.
            if value and isinstance(value[0], list):
                self._answers[host] = list(value)
            else:
                self._answers[host] = [value]
        self.calls: list[str] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.calls.append(host)
        seq = self._answers.get(host)
        if not seq:
            raise OSError(f"NXDOMAIN {host}")
        return seq.pop(0) if len(seq) > 1 else seq[0]


class RecordingTransport(httpx.AsyncBaseTransport):
    """Returns canned responses keyed by "host/path" or, failing that, by host.

    Keys use the original Host header, since the request URL carries the pinned IP.
    """

    def __init__(self, routes: dict[str, httpx.Response] | None = None):
        self.routes = routes or {}
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.headers["host"]
        resp = self.routes.get(
            host + request.url.path,
            self.routes.get(host, httpx.Response(200, text="ok")),
        )
        return httpx.Response(
            resp.status_code, headers=resp.headers, content=resp.content
        )


def run(coro):
    return asyncio.run(coro)


# ── is_blocked_ip ───────────────────────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.1.2.3",
        "0.0.0.0",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # AWS/GCP/Azure metadata
        "100.64.0.1",  # carrier-grade NAT
        "100.100.100.200",  # Alibaba metadata (inside 100.64/10)
        "224.0.0.1",  # multicast
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd00:ec2::254",  # AWS IPv6 metadata
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "ff02::1",
    ],
)
def test_private_and_special_addresses_are_blocked(ip):
    assert is_blocked_ip(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", [PUBLIC_V4, "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(ip):
    assert is_blocked_ip(ipaddress.ip_address(ip)) is False


# ── allowlist matching ──────────────────────────────────────


def test_allowlist_exact_and_wildcard():
    allowed = ["docs.internal", "*.corp.example"]
    assert host_is_allowlisted("docs.internal", allowed)
    assert host_is_allowlisted("DOCS.INTERNAL", allowed)
    assert host_is_allowlisted("wiki.corp.example", allowed)
    assert host_is_allowlisted("a.b.corp.example", allowed)
    # Suffix tricks must not match
    assert not host_is_allowlisted("docs.internal.evil.com", allowed)
    assert not host_is_allowlisted("evildocs.internal", allowed)
    assert not host_is_allowlisted("corp.example", allowed)
    assert not host_is_allowlisted("corp.example.evil.com", allowed)
    assert not host_is_allowlisted("evilcorp.example", allowed)


# ── safe_fetch: literal IPs and odd encodings ───────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:8000/health",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/",
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0177.0.0.1/",  # octal
        "http://0x7f000001/",  # hex
        "http://0x7f.1/",  # short form
        "http://0/",
    ],
)
def test_literal_private_ips_blocked_without_dns_or_request(url):
    resolver = FakeResolver({})
    transport = RecordingTransport()
    with pytest.raises(BlockedURLError):
        run(safe_fetch(url, resolver=resolver, transport=transport))
    assert resolver.calls == []
    assert transport.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http://user:pass@example.com/",
        "http:///nohost",
        "not a url",
    ],
)
def test_bad_schemes_credentials_and_garbage_rejected(url):
    transport = RecordingTransport()
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                url,
                resolver=FakeResolver({"example.com": [PUBLIC_V4]}),
                transport=transport,
            )
        )
    assert transport.requests == []


# ── safe_fetch: DNS-based checks ────────────────────────────


def test_hostname_resolving_to_private_ip_blocked():
    resolver = FakeResolver({"internal.example.com": ["10.0.0.5"]})
    transport = RecordingTransport()
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                "https://internal.example.com/", resolver=resolver, transport=transport
            )
        )
    assert transport.requests == []


def test_hostname_with_any_private_answer_blocked():
    resolver = FakeResolver({"mixed.example.com": [PUBLIC_V4, "127.0.0.1"]})
    transport = RecordingTransport()
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                "https://mixed.example.com/", resolver=resolver, transport=transport
            )
        )
    assert transport.requests == []


def test_unresolvable_host_is_an_error():
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                "https://nxdomain.example/",
                resolver=FakeResolver({}),
                transport=RecordingTransport(),
            )
        )


def test_public_host_is_fetched_via_pinned_ip_with_original_host_and_sni():
    resolver = FakeResolver({"example.com": [PUBLIC_V4]})
    transport = RecordingTransport(
        {"example.com": httpx.Response(200, text="<p>Hello</p>")}
    )
    result = run(
        safe_fetch(
            "https://example.com/page?q=1", resolver=resolver, transport=transport
        )
    )

    assert result.status_code == 200
    assert result.text == "<p>Hello</p>"
    assert result.url == "https://example.com/page?q=1"
    (req,) = transport.requests
    # The connection goes to the vetted IP, never back through DNS.
    assert req.url.host == PUBLIC_V4
    assert req.url.path == "/page"
    assert req.url.query == b"q=1"
    assert req.headers["host"] == "example.com"
    assert req.extensions["sni_hostname"] == "example.com"


def test_explicit_port_preserved_in_host_header():
    resolver = FakeResolver({"example.com": [PUBLIC_V4]})
    transport = RecordingTransport()
    run(safe_fetch("http://example.com:8080/", resolver=resolver, transport=transport))
    (req,) = transport.requests
    assert req.url.port == 8080
    assert req.headers["host"] == "example.com:8080"
    assert "sni_hostname" not in req.extensions


def test_dns_rebinding_cannot_swap_address_after_validation():
    """First answer is public, any later answer would be private.

    The guard must resolve once per hop and connect to the address it validated,
    so a second lookup (where the attacker flips the record) never happens.
    """
    resolver = FakeResolver({"rebind.example.com": [[PUBLIC_V4], ["127.0.0.1"]]})
    transport = RecordingTransport()
    run(
        safe_fetch("http://rebind.example.com/", resolver=resolver, transport=transport)
    )
    assert resolver.calls == ["rebind.example.com"]
    (req,) = transport.requests
    assert req.url.host == PUBLIC_V4


# ── safe_fetch: redirects ───────────────────────────────────


def test_redirect_to_metadata_ip_blocked():
    resolver = FakeResolver({"example.com": [PUBLIC_V4]})
    transport = RecordingTransport(
        {
            "example.com": httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
        }
    )
    with pytest.raises(BlockedURLError):
        run(safe_fetch("http://example.com/", resolver=resolver, transport=transport))
    assert len(transport.requests) == 1


def test_redirect_to_host_resolving_private_blocked():
    resolver = FakeResolver(
        {"example.com": [PUBLIC_V4], "evil.example.net": ["192.168.0.10"]}
    )
    transport = RecordingTransport(
        {
            "example.com": httpx.Response(
                301, headers={"location": "https://evil.example.net/admin"}
            )
        }
    )
    with pytest.raises(BlockedURLError):
        run(safe_fetch("http://example.com/", resolver=resolver, transport=transport))
    assert len(transport.requests) == 1


def test_safe_redirects_are_followed_and_revalidated():
    resolver = FakeResolver(
        {"example.com": [PUBLIC_V4], "www.example.com": [PUBLIC_V4_B]}
    )
    transport = RecordingTransport(
        {
            "example.com": httpx.Response(
                301, headers={"location": "https://www.example.com/start"}
            ),
            "www.example.com/start": httpx.Response(
                302,
                headers={"location": "/final"},  # relative redirect
            ),
            "www.example.com/final": httpx.Response(200, text="done"),
        }
    )
    result = run(
        safe_fetch("http://example.com/", resolver=resolver, transport=transport)
    )
    assert result.text == "done"
    assert result.url == "https://www.example.com/final"
    assert [r.url.host for r in transport.requests] == [
        PUBLIC_V4,
        PUBLIC_V4_B,
        PUBLIC_V4_B,
    ]
    # Every hop is resolved and validated again.
    assert resolver.calls == ["example.com", "www.example.com", "www.example.com"]


def test_too_many_redirects():
    resolver = FakeResolver({"example.com": [PUBLIC_V4]})
    transport = RecordingTransport(
        {"example.com": httpx.Response(302, headers={"location": "/again"})}
    )
    with pytest.raises(BlockedURLError, match="redirect"):
        run(
            safe_fetch(
                "http://example.com/",
                resolver=resolver,
                transport=transport,
                max_redirects=3,
            )
        )
    assert len(transport.requests) == 4


# ── safe_fetch: allowlist and limits ────────────────────────


def test_allowlisted_host_may_resolve_to_private_ip():
    resolver = FakeResolver({"docs.internal": ["10.0.0.7"]})
    transport = RecordingTransport(
        {"docs.internal": httpx.Response(200, text="intranet")}
    )
    result = run(
        safe_fetch(
            "http://docs.internal/",
            allowed_hosts=["docs.internal"],
            resolver=resolver,
            transport=transport,
        )
    )
    assert result.text == "intranet"
    assert transport.requests[0].url.host == "10.0.0.7"


def test_allowlist_does_not_cover_redirect_to_other_private_host():
    resolver = FakeResolver({"docs.internal": ["10.0.0.7"]})
    transport = RecordingTransport(
        {
            "docs.internal": httpx.Response(
                302, headers={"location": "http://169.254.169.254/"}
            )
        }
    )
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                "http://docs.internal/",
                allowed_hosts=["docs.internal"],
                resolver=resolver,
                transport=transport,
            )
        )


def test_allowlist_suffix_trick_still_blocked():
    resolver = FakeResolver({"docs.internal.attacker.com": ["127.0.0.1"]})
    with pytest.raises(BlockedURLError):
        run(
            safe_fetch(
                "http://docs.internal.attacker.com/",
                allowed_hosts=["docs.internal"],
                resolver=resolver,
                transport=RecordingTransport(),
            )
        )


def test_response_body_is_capped():
    resolver = FakeResolver({"example.com": [PUBLIC_V4]})
    transport = RecordingTransport(
        {"example.com": httpx.Response(200, content=b"a" * 5000)}
    )
    result = run(
        safe_fetch(
            "http://example.com/",
            resolver=resolver,
            transport=transport,
            max_bytes=1000,
        )
    )
    assert len(result.content) == 1000
    assert result.truncated is True
