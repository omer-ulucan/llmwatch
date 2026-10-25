"""
Module: jwt_handler.py
Purpose: Handles generating and verifying JWT tokens, plus password hashing.
WHY: Custom stateless token management avoids database hits for 99% of requests, enabling massive scale.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from llmwatch.config import settings
from llmwatch.exceptions import AuthenticationException
from llmwatch.security.secrets import jwt_signing_key

# WHY: bcrypt with 12 rounds is industry standard for secure hashing.
BCRYPT_ROUNDS = 12


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare plain password with its hash.

    WHY: bcrypt.checkpw raises ValueError when the hash is empty, malformed, or
    uses an unknown scheme.  Catching it here prevents a 500 from leaking through
    to the caller and treats a corrupt hash the same as a wrong password.
    """
    try:
        if not plain_password or not hashed_password:
            return False
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Hash the password securely using bcrypt directly.

    WHY: Using bcrypt directly avoids the passlib compatibility issue with
    bcrypt>=4.1 on Python 3.14 (passlib's _detect_wrap_bug sends a 255-byte
    secret that newer bcrypt rejects).
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a new JWT token.

    Args:
        data: Payload content to embed (usually sub = user_id plus workspace claims).
        expires_delta: Optional custom expiry time.

    Returns:
        str: Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=settings.jwt_expire_hours))
    payload = {**data, "iat": now, "exp": expire}
    return jwt.encode(payload, jwt_signing_key(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    WHY: Only the configured HMAC algorithm is accepted (no "none", no algorithm
    confusion), and exp/sub must be present.

    Args:
        token: the JWT literal string.

    Raises:
        AuthenticationException: if token is malformed, invalid, or expired.

    Returns:
        Dict: the decoded payload.
    """
    try:
        return jwt.decode(
            token,
            jwt_signing_key(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.MissingRequiredClaimError:
        raise AuthenticationException("Invalid token payload structure")
    except jwt.PyJWTError:
        raise AuthenticationException("Could not validate credentials")
