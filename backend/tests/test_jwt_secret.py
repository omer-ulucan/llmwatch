"""
Regression tests: the JWT signing secret must be long enough to resist brute force.

WHY: HS256 tokens can be cracked offline from a single captured token when the
secret is short or guessable, which lets an attacker mint tokens for any tenant.
"""

import pytest
from pydantic import ValidationError

# Imported at module load, under conftest's valid env: importing config later,
# after monkeypatching a bad env, would fail in the module-level settings object.
from llmwatch.config import Settings


# Empty means "unset": a secret is then generated (see test_secret_key.py).
@pytest.mark.parametrize("secret", ["short", "x" * 31])
def test_short_jwt_secret_rejected(monkeypatch, secret):
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    with pytest.raises(ValidationError, match="at least 32"):
        Settings()


@pytest.mark.parametrize(
    "placeholder",
    [
        "replace_with_32_char_minimum_random_string",
        "your-secret-key-generated-with-openssl-rand-hex-32",
    ],
)
def test_documented_placeholders_rejected(monkeypatch, placeholder):
    monkeypatch.setenv("JWT_SECRET_KEY", placeholder)
    with pytest.raises(ValidationError, match="placeholder"):
        Settings()


def test_32_char_secret_accepted(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "k" * 32)
    assert Settings().jwt_secret_key == "k" * 32
