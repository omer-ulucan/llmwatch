"""
Module: config.py
Purpose: Centralizes environment variables into a strongly typed Pydantic Settings object.
WHY: This ensures the application crashes immediately on startup if required configuration is missing,
rather than failing unexpectedly at runtime.
"""
from typing import List, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

class Settings(BaseSettings):
    # AWS Settings
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    dynamodb_table_logs: str
    dynamodb_table_users: str

    # Auth Settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # LLM Models Settings
    google_api_key: str
    qwen_base_url: str
    qwen_api_key: str

    # MLFlow Settings
    mlflow_tracking_uri: str
    
    # Application Settings
    app_env: Literal["development", "production", "testing"] = "development"
    app_version: str = "0.1.0"
    cors_origins: str | List[str]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_cors_origins(self) -> List[str]:
        """
        Parses CORS origins from string if needed.
        
        Returns:
            List[str]: List of allowed origins.
        """
        # WHY: Environment variables might be comma-separated strings
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return self.cors_origins

settings = Settings()

# WHY: We configure logging here so it's standardized across all modules using config
logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("llmwatch")
