"""
Tests for server secret handling and JWT signing.

WHY: One server secret protects both session tokens (JWT) and stored provider API
keys (Fernet). It must be strong, survive restarts, and work with zero
configuration (docker compose up), so when SECRET_KEY is unset a random secret is
generated once and persisted next to the database.
"""

import base64
import os
import stat
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from llmwatch.auth.jwt_handler import create_access_token, decode_access_token
from llmwatch.config import Settings, settings
from llmwatch.exceptions import AuthenticationException
from llmwatch.security import secrets as secret_mod


@pytest.fixture
def fresh_secret(monkeypatch, tmp_path):
    """No SECRET_KEY / JWT_SECRET_KEY, secret file in a temp dir, cache cleared."""
    monkeypatch.setattr(settings, "secret_key", "")
    monkeypatch.setattr(settings, "jwt_secret_key", "")
    path = tmp_path / "data" / "secret_key"
    monkeypatch.setattr(settings, "secret_key_file", str(path))
    secret_mod.reset_cache()
    yield path
    secret_mod.reset_cache()


@pytest.fixture(autouse=True)
def _reset_after_each_test():
    yield
    secret_mod.reset_cache()


# ── Resolving the secret ────────────────────────────────────


def test_explicit_secret_key_is_used(monkeypatch, fresh_secret):
    monkeypatch.setattr(settings, "secret_key", "s" * 40)
    assert secret_mod.server_secret() == "s" * 40
    assert not fresh_secret.exists()


def test_legacy_jwt_secret_key_is_used_when_secret_key_unset(monkeypatch, fresh_secret):
    monkeypatch.setattr(settings, "jwt_secret_key", "j" * 40)
    assert secret_mod.server_secret() == "j" * 40
    assert not fresh_secret.exists()


def test_secret_is_generated_and_persisted_when_unset(fresh_secret):
    generated = secret_mod.server_secret()

    assert len(generated) >= 32
    assert fresh_secret.read_text().strip() == generated
    mode = stat.S_IMODE(os.stat(fresh_secret).st_mode)
    assert mode == 0o600

    secret_mod.reset_cache()  # simulate a restart
    assert secret_mod.server_secret() == generated


def test_existing_secret_file_is_reused(fresh_secret):
    fresh_secret.parent.mkdir(parents=True)
    fresh_secret.write_text("f" * 50 + "\n")
    assert secret_mod.server_secret() == "f" * 50


def test_weak_secret_file_is_refused(fresh_secret):
    fresh_secret.parent.mkdir(parents=True)
    fresh_secret.write_text("short")
    with pytest.raises(RuntimeError, match="at least 32"):
        secret_mod.server_secret()


def test_secret_file_created_concurrently_is_reused(fresh_secret, monkeypatch):
    """If another worker writes the file first, use its secret, don't overwrite."""
    real_open = os.open

    def racing_open(path, flags, mode=0o777):
        if str(path) == str(fresh_secret) and flags & os.O_EXCL:
            fresh_secret.write_text("w" * 48)
            raise FileExistsError(path)
        return real_open(path, flags, mode)

    fresh_secret.parent.mkdir(parents=True)
    monkeypatch.setattr(secret_mod.os, "open", racing_open)
    assert secret_mod.server_secret() == "w" * 48


# ── Derived keys ────────────────────────────────────────────


def test_derived_keys_are_distinct_and_deterministic(monkeypatch, fresh_secret):
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    jwt_key = secret_mod.jwt_signing_key()
    fernet_key = secret_mod.fernet_key()

    assert jwt_key != b"k" * 40
    assert base64.urlsafe_b64decode(fernet_key) != jwt_key
    secret_mod.reset_cache()
    assert secret_mod.jwt_signing_key() == jwt_key
    assert secret_mod.fernet_key() == fernet_key


def test_fernet_key_is_usable(monkeypatch, fresh_secret):
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    f = Fernet(secret_mod.fernet_key())
    assert f.decrypt(f.encrypt(b"sk-test")) == b"sk-test"


def test_changing_the_secret_changes_the_keys(monkeypatch, fresh_secret):
    monkeypatch.setattr(settings, "secret_key", "a" * 40)
    first = secret_mod.jwt_signing_key()
    secret_mod.reset_cache()
    monkeypatch.setattr(settings, "secret_key", "b" * 40)
    assert secret_mod.jwt_signing_key() != first


# ── JWT signing ─────────────────────────────────────────────


def test_tokens_are_not_signed_with_the_raw_secret(monkeypatch, fresh_secret):
    """Domain separation: the raw secret alone doesn't verify session tokens."""
    monkeypatch.setattr(settings, "secret_key", "k" * 40)
    token = create_access_token({"sub": "u1"})
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "k" * 40, algorithms=["HS256"])
    assert decode_access_token(token)["sub"] == "u1"


def test_unsigned_alg_none_token_is_rejected():
    forged = jwt.encode(
        {"sub": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        key=None,
        algorithm="none",
    )
    with pytest.raises(AuthenticationException):
        decode_access_token(forged)


def test_token_without_expiry_is_rejected():
    token = jwt.encode(
        {"sub": "u1"}, secret_mod.jwt_signing_key(), algorithm=settings.jwt_algorithm
    )
    with pytest.raises(AuthenticationException):
        decode_access_token(token)


def test_token_without_subject_is_rejected():
    token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(hours=1)},
        secret_mod.jwt_signing_key(),
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthenticationException):
        decode_access_token(token)


def test_tokens_carry_issued_at():
    payload = decode_access_token(create_access_token({"sub": "u1"}))
    assert "iat" in payload


# ── Settings validation ─────────────────────────────────────


def test_short_secret_key_rejected(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ValidationError, match="at least 32"):
        Settings()


def test_secret_key_may_be_left_unset(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    assert Settings().secret_key == ""


@pytest.mark.parametrize("alg", ["none", "RS256", "HS1"])
def test_only_hmac_sha2_algorithms_allowed(monkeypatch, alg):
    monkeypatch.setenv("JWT_ALGORITHM", alg)
    with pytest.raises(ValidationError):
        Settings()


def test_startup_generates_the_secret_file(fresh_secret, monkeypatch):
    from fastapi.testclient import TestClient

    from llmwatch.main import app

    with TestClient(app):
        pass
    assert fresh_secret.exists()
