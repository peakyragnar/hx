from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_env: str = Field("local", alias="APP_ENV")
    database_url: str = Field(
        "postgresql+psycopg://heretix:heretix@localhost:5433/heretix",
        alias="DATABASE_URL",
    )
    rpl_model: str = Field("gpt-5", alias="RPL_MODEL")
    rpl_prompt_version: str = Field("rpl_g5_v2", alias="RPL_PROMPT_VERSION")
    rpl_k: int = Field(16, alias="RPL_K")
    rpl_r: int = Field(2, alias="RPL_R")
    rpl_b: int = Field(5000, alias="RPL_B")
    rpl_max_output_tokens: int = Field(1024, alias="RPL_MAX_OUTPUT_TOKENS")
    allow_mock: bool = Field(True, alias="RPL_ALLOW_MOCK")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
