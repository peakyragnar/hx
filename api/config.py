from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_env: str = Field("local", alias="APP_ENV")
    database_url: str = Field(
        "postgresql+psycopg://heretix:heretix@localhost:5433/heretix",
        alias="DATABASE_URL",
    )
    api_url: str = Field("http://127.0.0.1:8000", alias="API_URL")
    app_url: str = Field("http://127.0.0.1:3000", alias="APP_URL")
    rpl_model: str = Field("gpt-5", alias="RPL_MODEL")
    rpl_prompt_version: str = Field("rpl_g5_v2", alias="RPL_PROMPT_VERSION")
    rpl_k: int = Field(16, alias="RPL_K")
    rpl_r: int = Field(2, alias="RPL_R")
    rpl_b: int = Field(5000, alias="RPL_B")
    rpl_max_output_tokens: int = Field(1024, alias="RPL_MAX_OUTPUT_TOKENS")
    allow_mock: bool = Field(True, alias="RPL_ALLOW_MOCK")
    magic_link_ttl_minutes: int = Field(10, alias="MAGIC_LINK_TTL_MINUTES")
    session_ttl_days: int = Field(30, alias="SESSION_TTL_DAYS")
    session_cookie_name: str = Field("heretix_session", alias="SESSION_COOKIE_NAME")
    session_cookie_domain: Optional[str] = Field(None, alias="SESSION_COOKIE_DOMAIN")
    session_cookie_secure: bool = Field(False, alias="SESSION_COOKIE_SECURE")
    email_sender_address: str = Field("hello@heretix.local", alias="EMAIL_SENDER_ADDRESS")
    postmark_token: Optional[str] = Field(None, alias="POSTMARK_TOKEN")
    anon_cookie_name: str = Field("heretix_anon", alias="ANON_COOKIE_NAME")
    stripe_secret_key: Optional[str] = Field(None, alias="STRIPE_SECRET")
    stripe_webhook_secret: Optional[str] = Field(None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_starter: Optional[str] = Field(None, alias="STRIPE_PRICE_STARTER")
    stripe_price_core: Optional[str] = Field(None, alias="STRIPE_PRICE_CORE")
    stripe_price_pro: Optional[str] = Field(None, alias="STRIPE_PRICE_PRO")
    stripe_success_path: str = Field("/billing/success", alias="STRIPE_SUCCESS_PATH")
    stripe_cancel_path: str = Field("/billing/cancel", alias="STRIPE_CANCEL_PATH")
    stripe_portal_config: Optional[str] = Field(None, alias="STRIPE_PORTAL_CONFIG")
    stripe_portal_return_path: str = Field("/", alias="STRIPE_PORTAL_RETURN_PATH")
    prompts_dir: Optional[Path] = Field(None, alias="RPL_PROMPTS_DIR")

    class Config:
        env_file = ".env"
        case_sensitive = False

    def prompt_file(self) -> Path:
        """Return resolved prompt file path for the configured prompt version."""
        if self.prompts_dir is not None:
            root = Path(self.prompts_dir)
        else:
            from heretix import __file__ as heretix_file

            root = Path(heretix_file).resolve().parent / "prompts"
        path = root / f"{self.rpl_prompt_version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path

    def price_for_plan(self, plan: str) -> Optional[str]:
        mapping = {
            "starter": self.stripe_price_starter,
            "core": self.stripe_price_core,
            "pro": self.stripe_price_pro,
        }
        return mapping.get(plan)

    def stripe_success_url(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.stripe_success_path}"

    def stripe_cancel_url(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.stripe_cancel_path}"

    def stripe_portal_return_url(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.stripe_portal_return_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
