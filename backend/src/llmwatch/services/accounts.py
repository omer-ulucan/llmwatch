"""
Module: accounts.py
Purpose: Workspaces and users: registration, login and the demo account.
WHY: Keeps account rules (email normalisation, signup policy, timing-safe login) in
one place, shared by the HTTP routes and startup seeding.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.jwt_handler import get_password_hash, verify_password
from llmwatch.config import logger, settings
from llmwatch.db.models import User, Workspace
from llmwatch.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConflictException,
)

# WHY: Verifying against a real bcrypt hash when the email is unknown makes a failed
# login take the same time either way, so response timing doesn't reveal which
# emails have accounts.
_DUMMY_HASH = get_password_hash("llmwatch-timing-equaliser")


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def user_count(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(User))).scalar_one()
    )


async def register(
    session: AsyncSession, email: str, password: str, workspace_name: str
) -> tuple[Workspace, User]:
    """
    Creates a workspace and its owner.

    Raises:
        AuthorizationException: Signups are closed (ALLOW_SIGNUP=false) and this
            isn't the very first account.
        ConflictException: The email is already registered.
    """
    email = normalize_email(email)
    # WHY: The first account can always be created, otherwise an instance started
    # with ALLOW_SIGNUP=false could never be set up.
    if not settings.allow_signup and await user_count(session) > 0:
        raise AuthorizationException("Signups are disabled on this server")

    existing = await session.execute(select(User.id).where(User.email == email))
    if existing.first() is not None:
        raise ConflictException("Email already registered")

    workspace = Workspace(name=workspace_name.strip())
    session.add(workspace)
    await session.flush()
    user = User(
        workspace_id=workspace.id,
        email=email,
        password_hash=get_password_hash(password),
        role="owner",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent registration with the same email won the race.
        await session.rollback()
        raise ConflictException("Email already registered")
    return workspace, user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Returns the active user for these credentials, or raises."""
    result = await session.execute(
        select(User).where(User.email == normalize_email(email))
    )
    user = result.scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationException("Invalid credentials")
    if not verify_password(password, user.password_hash):
        raise AuthenticationException("Invalid credentials")
    if not user.is_active:
        raise AuthenticationException("Account disabled")
    return user


async def ensure_demo_account(session: AsyncSession) -> User:
    """
    Creates the demo workspace and user if missing (DEMO_MODE only).

    WHY: Demo mode used to bypass the database with hardcoded credentials and a
    fake tenant. Now it's an ordinary account seeded at startup, so the demo
    behaves exactly like a real install.
    """
    email = normalize_email(settings.demo_email)
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    workspace = Workspace(name="Demo workspace")
    session.add(workspace)
    await session.flush()
    user = User(
        workspace_id=workspace.id,
        email=email,
        password_hash=get_password_hash(settings.demo_password),
        role="owner",
    )
    session.add(user)
    await session.commit()
    logger.info(f"Demo account created: {email}")
    return user
