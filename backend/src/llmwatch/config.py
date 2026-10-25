"""
Module: config.py
Purpose: Centralizes environment variables into a strongly typed Pydantic Settings object.
WHY: This ensures the application crashes immediately on startup if required configuration is missing,
rather than failing unexpectedly at runtime.
"""

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import List, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _package_version() -> str:
    # WHY: pyproject.toml is the single source of truth for the version.
    try:
        return version("llmwatch")
    except PackageNotFoundError:
        return "0.0.0+unknown"


MIN_SECRET_LENGTH = 32
# Placeholders shipped in .env.example and the docs: long enough, but public.
_PLACEHOLDER_SECRETS = {
    "replace_with_32_char_minimum_random_string",
    "your-secret-key-generated-with-openssl-rand-hex-32",
}


class Settings(BaseSettings):
    # AWS Settings
    # WHY: Credentials are optional so the app can use IAM instance roles on EC2.
    # When empty, boto3 falls back to the default credential chain
    # (env vars → instance metadata → ~/.aws/credentials).
    aws_region: str
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    dynamodb_table_logs: str
    dynamodb_table_users: str
    dynamodb_table_traces: str = "llmwatch_traces"
    dynamodb_table_api_keys: str = "llmwatch_api_keys"

    # Database
    # WHY: SQLite works with zero setup; set postgresql+asyncpg://... for Postgres
    # (install the "postgres" extra).
    database_url: str = "sqlite+aiosqlite:///./data/llmwatch.db"
    db_echo: bool = False
    # Apply pending Alembic migrations at startup.
    auto_migrate: bool = True

    # Auth Settings
    # WHY: One server secret; JWT signing and provider-key encryption keys are
    # derived from it (llmwatch.security.secrets). Leave it unset to have a random
    # secret generated once and stored in secret_key_file (back that file up:
    # losing it logs everyone out and makes stored provider API keys unreadable).
    secret_key: str = ""
    secret_key_file: str = "./data/secret_key"
    # Legacy name for secret_key, still honoured when secret_key is unset.
    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_expire_hours: int = 24

    # LLM Models Settings
    google_api_key: str
    qwen_base_url: str = ""
    qwen_api_key: str = ""

    # MLFlow Settings
    mlflow_tracking_uri: str

    # Signups: when false, only the very first account can be created (bootstrap).
    allow_signup: bool = True

    # Demo Mode — seeds a demo account with shared, public credentials.
    # WHY: Handy for local demos, but the credentials are public, so it is off by
    # default and refused when APP_ENV=production (see _refuse_demo_in_production).
    demo_mode: bool = False
    demo_email: str = "demo@llmwatch.dev"
    demo_password: str = "llmwatch-demo"

    # Rate limiting
    # WHY: Comma-separated CIDRs of reverse proxies whose X-Forwarded-For header is
    # trusted. Leave empty when the backend is reached directly; set it to the proxy
    # network when running behind nginx (otherwise every user shares one bucket).
    trusted_proxies: str = ""
    rate_limit_enabled: bool = True
    # memory:// is per process; use e.g. redis://host:6379 with several workers.
    rate_limit_storage_uri: str = "memory://"
    # Per API key / per user (slowapi syntax, e.g. "60/minute;1000/day")
    rate_limit_chat: str = "60/minute"
    rate_limit_agent: str = "10/minute"
    # Per client IP on the same routes, across all identities from that address
    rate_limit_per_ip: str = "300/minute"

    # Agent Python code execution
    # WHY: The python tool runs model-written code as a subprocess of the backend. It
    # is NOT a sandbox: it shares the container's filesystem and network. Keep it off
    # unless the deployment is isolated and you accept that risk.
    enable_code_execution: bool = False

    # Agent URL fetching
    # WHY: The fetch tool blocks private, loopback and link-local addresses. Hosts
    # listed here (comma-separated, exact or "*.example.com") may resolve to private
    # addresses, e.g. an intranet wiki the agent is meant to read.
    fetch_allowed_hosts: str = ""

    # Application Settings
    app_env: Literal["development", "production", "testing"] = "development"
    app_version: str = _package_version()
    cors_origins: str | List[str]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("secret_key", "jwt_secret_key")
    @classmethod
    def _require_strong_secret(cls, v: str, info) -> str:
        # WHY: Short HS256 secrets can be brute-forced offline from one captured
        # token, letting an attacker mint tokens for any tenant. Empty means "not
        # set" (a strong secret is then generated and persisted).
        name = info.field_name.upper()
        if not v:
            return v
        if len(v) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"{name} must be at least {MIN_SECRET_LENGTH} characters; "
                "generate one with: openssl rand -hex 32 (or leave it unset)"
            )
        if v in _PLACEHOLDER_SECRETS:
            raise ValueError(
                f"{name} is still a documented placeholder; "
                "generate one with: openssl rand -hex 32 (or leave it unset)"
            )
        return v

    @model_validator(mode="after")
    def _refuse_demo_in_production(self) -> "Settings":
        if self.demo_mode and self.app_env == "production":
            raise ValueError(
                "DEMO_MODE=true is not allowed when APP_ENV=production: demo "
                "credentials are public. Unset DEMO_MODE or use another APP_ENV."
            )
        return self

    def get_cors_origins(self) -> List[str]:
        """
        Parses CORS origins from string if needed.

        Returns:
            List[str]: List of allowed origins.
        """
        # WHY: Environment variables might be comma-separated strings
        if isinstance(self.cors_origins, str):
            return [
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            ]
        return self.cors_origins


settings = Settings()

# WHY: Logging is configured here so it's standardized across all modules. Only our
# own logger goes to DEBUG in development; libraries (aiosqlite, httpx, ...) stay at
# WARNING, otherwise every SQL round trip is logged.
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("llmwatch")
logger.setLevel(logging.DEBUG if settings.app_env == "development" else logging.INFO)
