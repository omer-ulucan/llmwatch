"""
Module: auth.py
Purpose: Exposes authentication API routes.
WHY: Encapsulating login/registration endpoints isolates public-facing handlers from protected routes.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from models.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RegisterResponse,
)
from auth.jwt_handler import get_password_hash, verify_password, create_access_token
from services.dynamo_service import get_dynamo_service
from exceptions import AuthenticationException, ValidationException
from config import settings
from rate_limit import limiter
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["Authentication"])

# WHY: Hardcoded demo user lets the app run without DynamoDB for local dev and demos.
# Set DEMO_MODE=false in production to disable.
_DEMO_USER = {
    "email": "admin@company.com",
    "password": "admin123",
    "user_id": "demo-user-001",
    "company_id": "demo-company-001",
}


@router.post("/register", response_model=RegisterResponse)
@limiter.limit("5/minute")
async def register(request: Request, data: RegisterRequest):
    """
    Registers a new company and admin user.
    """
    # ── Demo mode: accept any registration without DynamoDB ──
    if settings.demo_mode:
        return {
            "message": "User registered successfully",
            "company_id": f"demo-{uuid.uuid4().hex[:8]}",
        }

    company_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    hashed_pwd = get_password_hash(data.password)

    user_record = {
        "company_id": company_id,
        "email": data.email,
        "company_name": data.company_name,
        "user_id": user_id,
        "hashed_password": hashed_pwd,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }

    # WHY: save_user() uses a ConditionExpression for atomic email uniqueness,
    # preventing race conditions that the old check-then-write pattern allowed.
    get_dynamo_service().save_user(user_record)

    return {"message": "User registered successfully", "company_id": company_id}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest):
    """
    Authenticates a user and issues a JWT if successful.
    """
    # ── Demo mode: bypass DynamoDB entirely ────────────────
    if settings.demo_mode:
        if (
            data.email == _DEMO_USER["email"]
            and data.password == _DEMO_USER["password"]
        ):
            access_token = create_access_token(
                data={
                    "sub": _DEMO_USER["user_id"],
                    "company_id": _DEMO_USER["company_id"],
                }
            )
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": settings.jwt_expire_hours * 3600,
            }
        raise AuthenticationException("Invalid credentials")

    # ── Normal flow: look up user in DynamoDB ──────────────
    user = get_dynamo_service().get_user_by_email(data.email)
    if not user or not verify_password(data.password, user.get("hashed_password", "")):
        raise AuthenticationException("Invalid credentials")

    if not user.get("is_active", True):
        raise AuthenticationException("Account disabled")

    # WHY: Including company_id in the token prevents us from needing to hit the DB
    # on every subsequent request to figure out which tenant they belong to.
    access_token = create_access_token(
        data={"sub": user["user_id"], "company_id": user["company_id"]}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_hours * 3600,
    }
