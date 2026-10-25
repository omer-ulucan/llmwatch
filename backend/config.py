"""
Module: config.py
Purpose: Centralizes environment variables into a strongly typed Pydantic Settings object.
WHY: This ensures the application crashes immediately on startup if required configuration is missing,
rather than failing unexpectedly at runtime.
"""

import logging
from typing import List, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    # Auth Settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # LLM Models Settings
    google_api_key: str
    qwen_base_url: str = ""
    qwen_api_key: str = ""

    # MLFlow Settings
    mlflow_tracking_uri: str

    # Demo Mode — allows login with shared demo credentials.
    # WHY: Handy for local demos, but the credentials are public, so it is off by
    # default and refused when APP_ENV=production (see _refuse_demo_in_production).
    demo_mode: bool = False

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
    app_version: str = "0.1.0"
    cors_origins: str | List[str]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def _require_strong_jwt_secret(cls, v: str) -> str:
        # WHY: Short HS256 secrets can be brute-forced offline from one captured
        # token, letting an attacker mint tokens for any tenant.
        if len(v) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters; "
                "generate one with: openssl rand -hex 32"
            )
        if v in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "JWT_SECRET_KEY is still the .env.example placeholder; "
                "generate one with: openssl rand -hex 32"
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

# WHY: We configure logging here so it's standardized across all modules using config
logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("llmwatch")
