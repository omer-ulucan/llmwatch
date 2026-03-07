"""
Module: dependencies.py
Purpose: FastAPI dependencies for enforcing Authentication via JWT.
WHY: Using dependency injection separates routing from security validation, keeping controllers clean.
"""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any
from auth.jwt_handler import decode_access_token
from exceptions import AuthenticationException

# WHY: OAuth2PasswordBearer automatically looks for the Authorization: Bearer <token> header
# and integrates directly with FastAPI's OpenAPI swagger documentation standard.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Validates token and returns user context.
    
    Args:
        token (str): Injected from authorization header.
        
    Returns:
        Dict: JWT payload usually containing sub(user_id) and company_id.
        
    Raises:
        AuthenticationException: If validation fails.
    """
    if not token:
        raise AuthenticationException("Not authenticated")
    
    payload = decode_access_token(token)
    user_id: str = payload.get("sub")
    company_id: str = payload.get("company_id")
    
    if user_id is None or company_id is None:
        raise AuthenticationException("Invalid token payload structure")
        
    return {
        "user_id": user_id,
        "company_id": company_id
    }
