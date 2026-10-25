"""
Module: secrets.py
Purpose: Resolves the server secret and derives purpose-specific keys from it.
WHY: Self-hosters shouldn't need to invent secrets for `docker compose up`, yet the
secret must be strong and survive restarts. Resolution order:
  1. SECRET_KEY
  2. JWT_SECRET_KEY (legacy name)
  3. the contents of SECRET_KEY_FILE, generated on first start if missing
Keys for different purposes are derived with HKDF and distinct labels, so a key
used for one job (JWT signing) can't be replayed for another (Fernet encryption).
"""

import base64
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from llmwatch.config import MIN_SECRET_LENGTH, logger, settings

_JWT_INFO = b"llmwatch/jwt-signing/v1"
_FERNET_INFO = b"llmwatch/provider-key-encryption/v1"


def _read_secret_file(path: Path) -> str:
    value = path.read_text().strip()
    if len(value) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"The secret in {path} must be at least {MIN_SECRET_LENGTH} characters"
        )
    return value


def _load_or_create_secret_file(path: Path) -> str:
    if path.exists():
        return _read_secret_file(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    try:
        # WHY: O_EXCL so concurrent workers can't overwrite each other's secret;
        # 0600 so only the server's user can read it.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_secret_file(path)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    logger.warning(
        f"No SECRET_KEY set: generated one and stored it in {path}. Back this file "
        "up; losing it logs everyone out and makes stored provider keys unreadable."
    )
    return value


@lru_cache(maxsize=1)
def server_secret() -> str:
    """The server secret (see module docstring for the resolution order)."""
    if settings.secret_key:
        return settings.secret_key
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    return _load_or_create_secret_file(Path(settings.secret_key_file).expanduser())


def _derive(info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(
        server_secret().encode()
    )


@lru_cache(maxsize=1)
def jwt_signing_key() -> bytes:
    return _derive(_JWT_INFO)


@lru_cache(maxsize=1)
def fernet_key() -> bytes:
    return base64.urlsafe_b64encode(_derive(_FERNET_INFO))


def reset_cache() -> None:
    """Forget resolved secrets (tests, or after changing settings at runtime)."""
    server_secret.cache_clear()
    jwt_signing_key.cache_clear()
    fernet_key.cache_clear()
