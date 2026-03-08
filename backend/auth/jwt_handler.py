"""
Module: jwt_handler.py
Purpose: Handles generating and verifying JWT tokens, plus password hashing.
WHY: Custom stateless token management avoids database hits for 99% of requests, enabling massive scale.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from jose import JWTError, jwt
import bcrypt
from config import settings
from exceptions import AuthenticationException

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
        data: Payload content to embed (usually sub = user_id, company_id = company_id).
        expires_delta: Optional custom expiry time.

    Returns:
        str: Encoded JWT string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # WHY: 24h as per requirement
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: the JWT literal string.

    Raises:
        AuthenticationException: if token is malformed, invalid, or expired.

    Returns:
        Dict: the decoded payload.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        raise AuthenticationException("Could not validate credentials")
