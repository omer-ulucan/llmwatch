"""
Module: auth.py
Purpose: Exposes authentication API routes.
WHY: Encapsulating login/registration endpoints isolates public-facing handlers from protected routes.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.auth.jwt_handler import create_access_token
from llmwatch.config import settings
from llmwatch.db.engine import get_session
from llmwatch.db.models import User, Workspace
from llmwatch.exceptions import AuthenticationException
from llmwatch.models.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from llmwatch.rate_limit import limiter
from llmwatch.services import accounts

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_for(user: User) -> Dict[str, Any]:
    # WHY: The workspace and role are in the token for clients' convenience only;
    # the server reloads the user on every request and trusts the database.
    access_token = create_access_token(
        data={"sub": user.id, "workspace_id": user.workspace_id, "role": user.role}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_hours * 3600,
    }


@router.post("/register", response_model=RegisterResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Registers a new workspace and its owner.
    """
    workspace, _user = await accounts.register(
        session, data.email, data.password, data.resolved_workspace_name
    )
    return {
        "message": "User registered successfully",
        "workspace_id": workspace.id,
        "company_id": workspace.id,
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticates a user via JSON body and issues a JWT if successful.
    WHY: This is the primary endpoint used by the frontend SPA.
    """
    user = await accounts.authenticate(session, data.email, data.password)
    return _token_for(user)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """
    OAuth2-compatible token endpoint that accepts form-encoded credentials.
    WHY: Swagger UI's "Authorize" button sends application/x-www-form-urlencoded
    with 'username' and 'password' fields per the OAuth2 spec. This endpoint
    bridges that expectation so developers can test authenticated routes
    directly from the /docs page. The 'username' field is treated as the email.
    """
    user = await accounts.authenticate(session, form_data.username, form_data.password)
    return _token_for(user)


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the authenticated user and their workspace.
    WHY: Lets the UI show who is signed in instead of a hardcoded placeholder.
    """
    workspace = await session.get(Workspace, current_user["workspace_id"])
    if workspace is None:
        raise AuthenticationException("Workspace no longer exists")
    return {
        "user": {
            "id": current_user["user_id"],
            "email": current_user["email"],
            "role": current_user["role"],
        },
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "created_at": workspace.created_at,
        },
        "auth_method": current_user["auth_method"],
    }
