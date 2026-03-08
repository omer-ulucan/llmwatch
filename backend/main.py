"""
Module: main.py
Purpose: Main application entrypoint configuring routers, middleware, and exception handlers.
WHY: Serving as the orchestrator, it centralizes app configuration to ensure consistent behavior.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import time

from config import settings, logger
from exceptions import LLMWatchException
from middleware.security import setup_security_middleware
from rate_limit import limiter
from routers import auth, chat, analytics, agent


# WHY: We apply slowapi rate limiters at the application layer to block abuse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    app.state.start_time = time.time()
    logger.info(
        f"LLMWatch {settings.app_version} startup complete in environment: {settings.app_env}"
    )
    yield


app = FastAPI(
    title="LLMWatch API",
    version=settings.app_version,
    description="Backend services for the LLMWatch observability and orchestration platform.",
    lifespan=lifespan,
)

# Apply limits globally
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
