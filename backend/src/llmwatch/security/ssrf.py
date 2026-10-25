"""
Module: ssrf.py
Purpose: Fetches URLs on behalf of the agent without letting it reach internal networks.
WHY: URLs given to the fetch tool are chosen by an LLM and can be steered by prompt
injection. A naive fetch can read cloud metadata (169.254.169.254), services on
localhost, or anything on the private network the backend sits in.

How the guard works, per request and per redirect hop:
  1. Only http/https, no credentials in the URL.
  2. The host is parsed as an IP literal when possible (including decimal, octal and
     hex IPv4 forms such as http://2130706433/), otherwise resolved through DNS once.
  3. Every resolved address must be public (see is_blocked_ip), unless the host is on
     the explicit allowlist (FETCH_ALLOWED_HOSTS).
  4. The connection goes to the validated IP, with the original Host header and TLS
     SNI/certificate name. A second DNS lookup never happens, which defeats DNS
     rebinding (public answer at check time, private answer at connect time).
  5. Redirects are followed manually so each Location goes through steps 1-4 again.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

DEFAULT_MAX_BYTES = 500_000
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; LLMWatch Agent/1.0)"

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class BlockedURLError(ValueError):
    """Raised when a URL (or a redirect target) is not allowed to be fetched."""


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Returns the IPv4 address tunnelled inside an IPv6 address, if any."""
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_blocked_ip(ip: IPAddress) -> bool:
    """True for anything that is not a plain public unicast address."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(ip)
        if embedded is not None and is_blocked_ip(embedded):
            return True
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def host_is_allowlisted(host: str, allowed_hosts: Iterable[str]) -> bool:
    """Exact host match, or "*.example.com" matching strict subdomains only."""
    host = host.lower().rstrip(".")
    for entry in allowed_hosts:
        entry = entry.strip().lower().rstrip(".")
        if not entry:
            continue
        if entry.startswith("*."):
            if host.endswith(entry[1:]) and host != entry[2:]:
                return True
        elif host == entry:
            return True
    return False


def parse_allowed_hosts(raw: str) -> list[str]:
    """Parses the comma-separated FETCH_ALLOWED_HOSTS setting."""
    return [h.strip() for h in raw.split(",") if h.strip()]


def _parse_ip_literal(host: str) -> IPAddress | None:
    """Parses IP literals, including the legacy inet_aton IPv4 forms."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    # WHY: Browsers and libc accept "2130706433", "0177.0.0.1" and "0x7f.1" as IPv4.
    # Only purely numeric/hex dotted strings are considered, so real hostnames
    # never reach inet_aton.
    if host and all(part for part in host.split(".")):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


async def _system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def _resolve_and_validate(
    host: str, port: int, allowed_hosts: list[str], resolver: Resolver
) -> IPAddress:
    allowlisted = host_is_allowlisted(host, allowed_hosts)

    literal = _parse_ip_literal(host)
    if literal is not None:
        if is_blocked_ip(literal) and not allowlisted:
            raise BlockedURLError(f"Blocked: {host} is not a public address")
        return literal

    try:
        answers = await resolver(host, port)
    except OSError as exc:
        raise BlockedURLError(f"Could not resolve host {host}") from exc

    addresses: list[IPAddress] = []
    for answer in answers:
        try:
            # Strip IPv6 zone ids such as "fe80::1%eth0" before parsing.
            addresses.append(ipaddress.ip_address(answer.split("%")[0]))
        except ValueError:
            raise BlockedURLError(f"Blocked: unexpected DNS answer for {host}")
    if not addresses:
        raise BlockedURLError(f"Could not resolve host {host}")

    if not allowlisted:
        # WHY: Reject if *any* answer is private; otherwise an attacker can publish
        # one public and one private record and win whichever gets picked.
        for addr in addresses:
            if is_blocked_ip(addr):
                raise BlockedURLError(
                    f"Blocked: {host} resolves to a non-public address"
                )
    return addresses[0]


async def ensure_public_host(host: str, port: int) -> None:
    """Raises BlockedURLError unless every address of `host` is public."""
    await _resolve_and_validate(host, port, [], _system_resolver)


def _validate_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as exc:
        raise BlockedURLError(f"Invalid URL: {url}") from exc
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError(f"Invalid URL: {url}. Only http and https are allowed")
    if not parsed.host:
        raise BlockedURLError(f"Invalid URL: {url}. Missing host")
    if parsed.userinfo:
        raise BlockedURLError("Blocked: credentials in URLs are not allowed")
    return parsed


async def safe_fetch(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: Resolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """
    GETs a URL with SSRF protection. See the module docstring for the rules.

    Args:
        url: The absolute http(s) URL to fetch.
        allowed_hosts: Hosts allowed to resolve to private addresses (exact or "*.x").
        max_bytes: Body bytes to read before truncating.
        timeout: Overall timeout for the whole fetch, including redirects.
        max_redirects: Maximum number of redirects to follow.
        resolver: DNS resolver override (tests).
        transport: httpx transport override (tests).

    Raises:
        BlockedURLError: The URL or a redirect target is not allowed.
        httpx.HTTPError: Network-level failure talking to an allowed host.
    """
    allowed = list(allowed_hosts or [])
    resolve = resolver or _system_resolver
    redirects: list[str] = []
    current = url

    # WHY: trust_env=False so HTTP(S)_PROXY variables can't route requests through a
    # proxy that sits inside the private network.
    async with httpx.AsyncClient(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        timeout=timeout,
    ) as client:
        async with asyncio.timeout(timeout):
            for _ in range(max_redirects + 1):
                parsed = _validate_url(current)
                host = parsed.host
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                ip = await _resolve_and_validate(host, port, allowed, resolve)

                # netloc is "host[:port]" with IPv6 brackets; userinfo was rejected.
                host_header = parsed.netloc.decode("ascii")
                extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
                request = client.build_request(
                    "GET",
                    parsed.copy_with(host=str(ip)),
                    headers={
                        "Host": host_header,
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.5",
                    },
                    extensions=extensions,
                )
                response = await client.send(request, stream=True)
                try:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise BlockedURLError("Redirect without a Location header")
                        redirects.append(current)
                        current = urljoin(current, location)
                        continue

                    body = bytearray()
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            truncated = True
                            del body[max_bytes:]
                            break
                    return FetchResult(
                        url=current,
                        status_code=response.status_code,
                        headers=response.headers,
                        content=bytes(body),
                        truncated=truncated,
                        redirects=redirects,
                    )
                finally:
                    await response.aclose()

    raise BlockedURLError(f"Too many redirects (more than {max_redirects})")
