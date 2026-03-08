"""
Tests for JWT token generation, decoding, and password hashing.
"""

import pytest
from datetime import timedelta
from unittest.mock import patch
from jose import jwt as jose_jwt

from auth.jwt_handler import (
    create_access_token,
    decode_access_token,
    verify_password,
    get_password_hash,
)
from exceptions import AuthenticationException


# ── Password hashing ─────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_and_verify(self):
        raw = "my_secure_password"
        hashed = get_password_hash(raw)
        assert hashed != raw
        assert verify_password(raw, hashed)

    def test_wrong_password_fails(self):
        hashed = get_password_hash("correct")
        assert not verify_password("wrong", hashed)

    def test_hashes_are_unique(self):
        h1 = get_password_hash("same")
        h2 = get_password_hash("same")
        # bcrypt salts should make them different
        assert h1 != h2

    def test_hash_produces_bcrypt_format(self):
        """get_password_hash should produce a standard bcrypt hash string."""
        hashed = get_password_hash("secret")
        assert hashed.startswith("$2b$12$")  # bcrypt prefix with 12 rounds

    def test_verify_delegates_to_bcrypt(self):
        """verify_password should call bcrypt.checkpw under the hood."""
        with patch("auth.jwt_handler.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True
            result = verify_password("plain", "$2b$12$somehash")
            mock_bcrypt.checkpw.assert_called_once_with(b"plain", b"$2b$12$somehash")
            assert result is True

    def test_hash_delegates_to_bcrypt(self):
        """get_password_hash should call bcrypt.gensalt and bcrypt.hashpw."""
        with patch("auth.jwt_handler.bcrypt") as mock_bcrypt:
            mock_bcrypt.gensalt.return_value = b"$2b$12$fakesalt"
            mock_bcrypt.hashpw.return_value = b"$2b$12$fakehashed"
            result = get_password_hash("secret")
            mock_bcrypt.gensalt.assert_called_once_with(rounds=12)
            mock_bcrypt.hashpw.assert_called_once_with(b"secret", b"$2b$12$fakesalt")
            assert result == "$2b$12$fakehashed"


# ── Token creation / decoding ────────────────────────────────────────────


class TestTokenCreation:
    def test_roundtrip(self, jwt_secret, jwt_algorithm):
        payload = {"sub": "user-1", "company_id": "comp-1"}
        token = create_access_token(data=payload)
        decoded = decode_access_token(token)

        assert decoded["sub"] == "user-1"
        assert decoded["company_id"] == "comp-1"
        assert "exp" in decoded

    def test_custom_expiry(self, jwt_secret, jwt_algorithm):
        token = create_access_token(
            data={"sub": "u"}, expires_delta=timedelta(minutes=5)
        )
        decoded = decode_access_token(token)
        assert decoded["sub"] == "u"

    def test_expired_token_raises(self, jwt_secret, jwt_algorithm):
        token = create_access_token(
            data={"sub": "u"}, expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(AuthenticationException):
            decode_access_token(token)

    def test_tampered_token_raises(self, jwt_secret, jwt_algorithm):
        token = create_access_token(data={"sub": "u"})
        tampered = token[:-4] + "XXXX"
        with pytest.raises(AuthenticationException):
            decode_access_token(tampered)

    def test_garbage_token_raises(self):
        with pytest.raises(AuthenticationException):
            decode_access_token("not.a.jwt")
