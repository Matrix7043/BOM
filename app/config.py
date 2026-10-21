"""Runtime configuration, read from environment variables (or a .env file).

Every setting has a safe default so the app starts with zero configuration;
override any of them with an env var of the same name in upper case.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_file: str | None = None  # optional rotating file in addition to stdout

    data_dir: Path = Path("data")          # bundled read-only datasets
    storage_dir: Path = Path("storage")    # uploads + model artifacts (mount a volume here)

    significance_alpha: float = 0.05
    transform: Literal["sqrt", "log1p"] = "sqrt"

    max_upload_mb: float = 5.0
    max_channels: int = 20
    min_rows: int = 15

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        return self.storage_dir / "artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
