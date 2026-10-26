"""
Guards for the deployment files the quality bar depends on: a non-root backend
image, nginx settings that let SSE streams through, and a compose file that needs
no configuration.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _nginx_api_block() -> str:
    conf = (ROOT / "frontend" / "nginx.conf").read_text()
    match = re.search(r"location /api/ \{(.*?)\n    \}", conf, re.S)
    assert match, "nginx.conf has no location /api/ block"
    return match.group(1)


def test_backend_image_runs_as_a_non_root_user():
    users = re.findall(
        r"^USER\s+(\S+)", (ROOT / "backend" / "Dockerfile").read_text(), re.M
    )
    assert users, "Dockerfile never switches user"
    assert users[-1] not in ("root", "0"), users[-1]


def test_nginx_streams_sse_without_buffering():
    block = _nginx_api_block()
    for directive in (
        "proxy_buffering off;",
        "proxy_cache off;",
        "proxy_http_version 1.1;",
    ):
        assert directive in block, directive
    timeout = re.search(r"proxy_read_timeout (\d+)s;", block)
    assert timeout and int(timeout.group(1)) >= 300, (
        "SSE streams need a long read timeout"
    )


def test_nginx_overwrites_forwarded_for():
    # Appending ($proxy_add_x_forwarded_for) would let clients spoof their IP for
    # the rate limiter.
    block = _nginx_api_block()
    assert "proxy_set_header X-Forwarded-For   $remote_addr;" in block
    assert "proxy_add_x_forwarded_for" not in block


def test_compose_needs_no_configuration():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    backend = compose["services"]["backend"]
    assert all(
        not isinstance(e, dict) or e.get("required") is False
        for e in backend.get("env_file", [])
    )
    assert "llmwatch_data:/data" in backend["volumes"]
    assert "llmwatch_data" in compose["volumes"]
    # Only the frontend is published; the API is reached through nginx.
    assert "ports" not in backend


def test_the_suite_cannot_reach_the_network():
    import socket

    import pytest

    with (
        socket.socket() as sock,
        pytest.raises(RuntimeError, match="must not use the network"),
    ):
        sock.connect(("203.0.113.1", 80))  # TEST-NET-3, never routed


def test_backend_can_reach_services_on_the_docker_host():
    # Ollama/LM Studio usually run on the host: OLLAMA_BASE_URL=
    # http://host.docker.internal:11434/v1 only resolves on Linux with this entry.
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "host.docker.internal:host-gateway" in compose["services"]["backend"].get(
        "extra_hosts", []
    )
