
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Gemini API
    gemini_api_key: str = ""

    # Primary models
    gemini_routing_model: str = "gemini-3.5-flash-lite"
    gemini_response_model: str = "gemini-3.5-flash-lite"

    # Fallback models
    gemini_routing_fallback_model: str = "gemini-3.1-flash-lite"
    gemini_response_fallback_model: str = "gemini-3.1-flash-lite"

    # Embeddings
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embed_dim: int = 768

    # Router
    gemini_router_min_confidence: float = 0.72

    # Database: required environment configuration
    database_url: str
    database_host_override: str = ""
    application_database_name: str = "supportflow_recovery"

    # Security
    admin_token: str = "change-this-before-deployment"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # ==========================================
    # Email notifications (disabled by default)
    # ==========================================
    email_delivery_enabled: bool = False
    email_delivery_mode: str = "test"
    email_test_allowed_recipients: str = ""
    verification_email_encryption_key: str = ""
    verification_email_base_url: str = ""

    # SMTP connection settings
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_username: str = ""
    email_smtp_password: str = ""
    email_smtp_starttls: bool = True
    email_smtp_timeout_seconds: int = 15

    # Sender and admin recipient
    email_from_address: str = ""
    admin_notification_email: str = ""

    # Delivery worker
    email_worker_batch_size: int = 10
    email_worker_poll_seconds: int = 30
    email_max_attempts: int = 5

    # Disabled until admin security review is complete.
    admin_jwt_routes_enabled: bool = False

    cors_origins: str = "http://localhost:5173"

    @model_validator(mode="after")
    def apply_container_database_host(self):
        """Replace only the DB host for containers; keep credentials private."""
        override = self.database_host_override.strip()
        if not override:
            return self
        if any(char in override for char in "/:@?#"):
            raise ValueError("Invalid database host override")
        url = make_url(self.database_url)
        if url.drivername != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        self.database_url = url.set(host=override).render_as_string(
            hide_password=False
        )
        return self

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
