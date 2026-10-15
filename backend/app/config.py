"""Application settings loaded from environment variables (never from source control)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"  # development | test | production
    database_url: str = "sqlite:///./data/maa.db"
    jwt_secret: str = INSECURE_DEFAULT_SECRET
    jwt_exp_minutes: int = 60 * 8
    cors_origins: str = ""  # comma separated; empty = same-origin only

    # AI / speech providers
    llm_provider: str = "heuristic"  # heuristic | gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"  # configurable; verify availability for your key
    stt_provider: str = "none"  # none | gemini | fake (tests only)

    # Messaging providers (disabled until configured and authorized)
    email_provider: str = "disabled"  # disabled | mock | gmail
    whatsapp_provider: str = "disabled"  # disabled | mock | cloud
    calendar_provider: str = "disabled"  # disabled | mock
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_template_name: str = ""  # approved template; required for business-initiated messages
    whatsapp_template_lang: str = "en"

    # Safety / reliability
    approval_ttl_hours: int = 24
    sends_per_hour: int = 30
    job_max_attempts: int = 3
    job_stale_seconds: int = 300
    job_backoff_seconds: int = 30
    upload_dir: str = "./data/uploads"
    run_worker: bool = True
    worker_interval_seconds: float = 2.0
    max_upload_bytes: int = 20 * 1024 * 1024
    login_attempts_per_minute: int = 10
    allow_signup: bool = True

    log_json: bool = True
    serve_frontend: bool = True
    frontend_dir: str = Field(default="")

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_for_runtime(self) -> None:
        if self.is_production and self.jwt_secret == INSECURE_DEFAULT_SECRET:
            raise RuntimeError("JWT_SECRET must be set to a strong random value in production")
        if self.is_production and len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
