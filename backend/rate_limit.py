"""
Module: rate_limit.py
Purpose: Shared slowapi Limiter, client IP resolution behind proxies, and limit keys.
WHY: Extracting the limiter into its own module breaks the circular import
between main.py (which creates the app) and routers (which need the limiter
at decoration time).

Client IP: behind nginx, the TCP peer is the proxy for every user. X-Forwarded-For
is only honoured when the peer is in TRUSTED_PROXIES, and the client is the
right-most address not belonging to a trusted proxy (entries further left are
whatever the client chose to send, so they are never trusted).

Limit keys: authenticated requests are limited per API key or per user, so users
behind the same proxy or NAT don't share a bucket. A coarser per-IP limit is stacked
on top so rotating accounts or fake keys from one address doesn't escape limits.
"""

import hashlib
import ipaddress
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from config import settings

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=8)
def _parse_networks(raw: str) -> tuple[IPNetwork, ...]:
    networks = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            networks.append(ipaddress.ip_network(part, strict=False))
    return tuple(networks)


def _is_trusted(addr: str, networks: tuple[IPNetwork, ...]) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def _valid_ip(addr: str) -> bool:
    try:
        ipaddress.ip_address(addr)
        return True
    except ValueError:
        return False


def client_ip(request: Request) -> str:
    """The originating client address, honouring X-Forwarded-For only from proxies."""
    peer = request.client.host if request.client else "unknown"
    networks = _parse_networks(settings.trusted_proxies)
    if not networks or not _is_trusted(peer, networks):
        return peer

    hops: list[str] = []
    for header in request.headers.getlist("x-forwarded-for"):
        hops.extend(h.strip() for h in header.split(",") if h.strip())

    # Walk from the proxy towards the client; stop at the first untrusted hop.
    last_trusted = peer
    for hop in reversed(hops):
        if not _valid_ip(hop):
            # A trusted proxy never appends garbage, so this came from the client.
            return last_trusted
        if not _is_trusted(hop, networks):
            return hop
        last_trusted = hop
    return last_trusted


def ip_key(request: Request) -> str:
    return f"ip:{client_ip(request)}"


def rate_limit_key(request: Request) -> str:
    """Per-identity key: API key hash, else JWT subject, else client IP."""
    api_key = request.headers.get("x-api-key")
    if api_key:
        # WHY: Hash so raw keys never sit in the limiter's storage.
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:32]

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        from auth.jwt_handler import decode_access_token
        from exceptions import AuthenticationException

        try:
            sub = decode_access_token(auth[7:].strip()).get("sub")
        except AuthenticationException:
            sub = None
        if sub:
            return f"user:{sub}"

    return ip_key(request)


# WHY: Callables are evaluated on every request, so limits follow the current
# settings (and tests can tighten them) without re-decorating routes.
def chat_limit() -> str:
    return settings.rate_limit_chat


def agent_limit() -> str:
    return settings.rate_limit_agent


def per_ip_limit() -> str:
    return settings.rate_limit_per_ip


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Returns 429 in the API's standard error envelope."""
    # WHY: The window length is a safe upper bound for when the bucket refills.
    try:
        retry_after = str(int(exc.limit.limit.get_expiry()))
    except AttributeError:
        retry_after = "60"
    return JSONResponse(
        status_code=429,
        content={
            "error": f"Rate limit exceeded: {exc.detail}",
            "code": "RATE_LIMITED",
        },
        headers={"Retry-After": retry_after},
    )


limiter = Limiter(
    key_func=ip_key,
    storage_uri=settings.rate_limit_storage_uri,
    enabled=settings.rate_limit_enabled,
)
