"""
Module: jwt_handler.py
Purpose: Handles generating and verifying JWT tokens, plus password hashing.
WHY: Custom stateless token management avoids database hits for 99% of requests, enabling massive scale.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from config import settings
from exceptions import AuthenticationException

# WHY: bcrypt with 12 rounds is industry standard for secure hashing.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare plain password with its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash the password securely."""
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
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
        expire = datetime.utcnow() + expires_delta
    else:
        # WHY: 24h as per requirement
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
        
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
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
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise AuthenticationException("Could not validate credentials")
