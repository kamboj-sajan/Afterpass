"""Settings, paths and GDAL environment. Secrets come from `.env` at the repo root."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PUBLIC_DIR = DATA_DIR / "public"
REPORTS_DIR = REPO_ROOT / "reports"
VALIDATION_DIR = REPO_ROOT / "validation"

# Combined Punjab + Haryana + Delhi bbox (west, south, east, north).
REGION_BBOX: tuple[float, float, float, float] = (73.8, 27.6, 77.7, 32.6)
DEMO_DISTRICTS: tuple[str, ...] = ("Sangrur", "Bathinda", "Firozpur")
IST = "Asia/Kolkata"

# Fast, unsigned COG reads from AWS Open Data (brief §5.2).
GDAL_ENV: dict[str, str] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "AWS_NO_SIGN_REQUEST": "YES",
    "AWS_REGION": "us-west-2",
}
for _k, _v in GDAL_ENV.items():
    os.environ.setdefault(_k, _v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    firms_map_key: SecretStr | None = None
    openaq_api_key: SecretStr | None = None
    bedrock_model_id: str | None = None
    aws_region: str = "us-west-2"

    def require_firms_key(self) -> str:
        if self.firms_map_key is None or not self.firms_map_key.get_secret_value():
            raise RuntimeError("FIRMS_MAP_KEY is not set. Add it to .env at the repo root.")
        return self.firms_map_key.get_secret_value()


@lru_cache
def settings() -> Settings:
    return Settings()
