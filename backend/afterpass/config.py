"""Settings, paths and GDAL environment. Secrets come from `.env` at the repo root."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
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
# Burning seasons: (first day, last day). The live season has no last day yet.
SEASONS: dict[int, tuple[date, date | None]] = {
    2025: (date(2025, 10, 1), date(2025, 11, 30)),
    2026: (date(2026, 10, 1), None),
}


def season_window(season: int) -> tuple[date, date]:
    """First and last day of a season; an open season ends today (UTC)."""
    first, last = SEASONS[season]
    return first, last or datetime.now(UTC).date()


# Fast, unsigned COG reads from AWS Open Data (brief §5.2). Every asset is read over HTTPS, so
# no region is set here: AWS_REGION belongs to AfterPass's own resources (Sydney), not to the
# open-data buckets (us-west-2).
GDAL_ENV: dict[str, str] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
    # GDAL waits forever on a dead connection unless told otherwise. Drop a request that
    # cannot connect in 20 s or that moves under 1 KB/s for 30 s; the reader then retries it.
    "GDAL_HTTP_CONNECTTIMEOUT": "20",
    "GDAL_HTTP_LOW_SPEED_LIMIT": "1000",
    "GDAL_HTTP_LOW_SPEED_TIME": "30",
    "GDAL_HTTP_TIMEOUT": "300",
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
    # Where AfterPass's own resources live. The account is locked to Sydney.
    aws_region: str = "ap-southeast-2"

    def require_firms_key(self) -> str:
        if self.firms_map_key is None or not self.firms_map_key.get_secret_value():
            raise RuntimeError("FIRMS_MAP_KEY is not set. Add it to .env at the repo root.")
        return self.firms_map_key.get_secret_value()


@lru_cache
def settings() -> Settings:
    return Settings()
