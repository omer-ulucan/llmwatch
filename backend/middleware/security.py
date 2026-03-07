"""
Module: security.py
Purpose: Applies standard security headers and mechanisms to outbound responses.
WHY: HTTP headers present the first line of defense blocking malicious client-side execution (XSS, Clickjacking).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from config import settings

def setup_security_middleware(app: FastAPI) -> None:
    """
    Bootstraps all security constraints globally.
    
    Args:
        app (FastAPI): The main application instance.
    """
    # WHY: Strict CORS ensures only the React SPA can hit the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """
        Intercepts requests to append Helmet-style strict security headers.
        """
        response = await call_next(request)
        
        # WHY: Defense-in-depth headers recommended by OWASP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        return response
