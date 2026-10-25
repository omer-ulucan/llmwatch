"""
Module: main.py
Purpose: Main application entrypoint configuring routers, middleware, and exception handlers.
WHY: Serving as the orchestrator, it centralizes app configuration to ensure consistent behavior.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from llmwatch.config import logger, settings
from llmwatch.db import migrate
from llmwatch.db.engine import dispose_engine, get_sessionmaker, is_memory_sqlite
from llmwatch.exceptions import LLMWatchException
from llmwatch.middleware.security import setup_security_middleware
from llmwatch.providers.service import sync_env_providers_all
from llmwatch.rate_limit import limiter, rate_limit_exceeded_handler
from llmwatch.routers import (
    agent,
    analytics,
    api_keys,
    auth,
    chat,
    providers,
    workspaces,
)
from llmwatch.security.secrets import server_secret
from llmwatch.services.accounts import ensure_demo_account

# WHY: We apply slowapi rate limiters at the application layer to block abuse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    app.state.start_time = time.time()
    if settings.demo_mode:
        logger.warning(
            "DEMO_MODE is enabled: anyone can log in with the public demo "
            "credentials. Never expose this instance to the internet."
        )
    # Fail fast on a bad secret, and create the generated one before serving.
    server_secret()
    await run_startup_migrations()
    if settings.demo_mode:
        async with get_sessionmaker()() as session:
            await ensure_demo_account(session)
    # WHY: Only when we manage the schema; with AUTO_MIGRATE=false the operator
    # does, and startup leaves the database alone (new workspaces still get the
    # env providers when they register).
    if settings.auto_migrate and not is_memory_sqlite(settings.database_url):
        async with get_sessionmaker()() as session:
            await sync_env_providers_all(session)
    logger.info(
        f"LLMWatch {settings.app_version} startup complete in environment: {settings.app_env}"
    )
    yield
    await dispose_engine()


async def run_startup_migrations() -> None:
    """Brings the database schema up to date before serving requests."""
    if not settings.auto_migrate:
        return
    if is_memory_sqlite(settings.database_url):
        # WHY: Alembic would migrate its own connection's private memory database,
        # not the one the app uses. Tests create in-memory schemas directly.
        logger.info("In-memory database: skipping migrations")
        return
    # WHY: Alembic is synchronous and runs its own event loop; keep it off ours.
    await asyncio.to_thread(migrate.upgrade, settings.database_url)
    logger.info("Database schema is up to date")


app = FastAPI(
    title="LLMWatch API",
    version=settings.app_version,
    description="Backend services for the LLMWatch observability and orchestration platform.",
    lifespan=lifespan,
)

# Apply limits globally
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Setup fundamental HTTP security guards
setup_security_middleware(app)


# Map dynamic custom exceptions into standard HTTP error responses format
@app.exception_handler(LLMWatchException)
async def custom_exception_handler(request: Request, exc: LLMWatchException):
    # WHY: We never expose full traceback traces, only our sanitized specific codes
    status_code = 400 if exc.code == "VALIDATION_ERROR" else 500
    if exc.code == "AUTHENTICATION_FAILED":
        status_code = 401
    elif exc.code == "AUTHORIZATION_FAILED":
        status_code = 403
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = 404
    elif exc.code == "CONFLICT":
        status_code = 409

    return JSONResponse(
        status_code=status_code, content={"error": exc.message, "code": exc.code}
    )


# WHY: Universal error catcher to prevent uncaught exceptions crashing the Uvicorn worker
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred.",
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


# Include sub-routers logically mapping the domains
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(agent.router)
app.include_router(api_keys.router)
app.include_router(workspaces.router)
app.include_router(providers.router)


@app.get("/health", tags=["Health"])
@limiter.limit("10/minute")  # Strict limits on public unauthed routes
async def health_check(request: Request):
    """
    Load balancer checking endpoint.
    """
    return {
        "status": "up",
        "version": settings.app_version,
        "timestamp": time.time(),
        "uptime_seconds": time.time() - getattr(app.state, "start_time", time.time()),
    }
