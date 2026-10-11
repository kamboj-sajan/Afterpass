"""NASA FIRMS active-fire detections (brief §5.1).

Raw CSVs are cached per (source, start date, day range) for the whole region bbox, so every
district reuses the same downloads. The MAP_KEY is part of the request URL, so errors raised
here never include the URL.
"""

from __future__ import annotations

import io
import time
from datetime import UTC, date, datetime, timedelta

import geopandas as gpd
import httpx
import pandas as pd
from shapely.geometry.base import BaseGeometry

from afterpass.cache import atomic_write_bytes, cache_path
from afterpass.config import IST, REGION_BBOX, settings

API = "https://firms.modaps.eosdis.nasa.gov/api"
SENSORS = ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS")
MAX_DAYS = 5
KEEP = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "frp",
    "daynight",
]
# NRT files for the last few days are still being filled in, so those chunks are not cached.
NRT_SETTLE_DAYS = 2
TRIES = 4
RETRY_WAIT_S = 5.0


class FirmsError(RuntimeError):
    pass


def _get(path: str) -> str:
    """GET a FIRMS API path that follows the key. Errors never echo the URL (it holds the key)."""
    key = settings().require_firms_key()
    for attempt in range(TRIES):
        try:
            resp = httpx.get(f"{API}/{path.format(key=key)}", timeout=120)
        except httpx.HTTPError as exc:
            # A dropped connection is common; a few spaced retries usually get through.
            if attempt == TRIES - 1:
                raise FirmsError(f"FIRMS request failed: {type(exc).__name__}") from None
            time.sleep(RETRY_WAIT_S * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise FirmsError(f"FIRMS returned HTTP {resp.status_code}")
        return resp.text
    raise FirmsError("FIRMS request failed.")


def data_availability() -> dict[str, tuple[date, date]]:
    """{source: (min_date, max_date)}. Cached for the current UTC day."""
    today = datetime.now(UTC).date()
    dest = cache_path("firms", f"data_availability_{today.isoformat()}.csv")
    if not dest.exists():
        text = _get("data_availability/csv/{key}/ALL")
        if not text.startswith("data_id"):
            raise FirmsError(f"Unexpected data_availability response: {text[:80]!r}")
        atomic_write_bytes(dest, text.encode())
    df = pd.read_csv(dest)
    return {
        r.data_id: (date.fromisoformat(r.min_date), date.fromisoformat(r.max_date))
        for r in df.itertuples()
    }


def plan_requests(
    start: date, end: date, availability: dict[str, tuple[date, date]]
) -> list[tuple[str, date, int]]:
    """(source, chunk_start, day_range) requests covering [start, end] for every sensor.

    Standard-processing (SP) data is used where it exists and near-real-time (NRT) for the days
    after it, so no day is fetched twice for one sensor.
    """
    requests: list[tuple[str, date, int]] = []
    for sensor in SENSORS:
        cursor = start
        for suffix in ("SP", "NRT"):
            source = f"{sensor}_{suffix}"
            if source not in availability or cursor > end:
                continue
            lo, hi = availability[source]
            first, last = max(cursor, lo), min(end, hi)
            day = first
            while day <= last:
                n = min(MAX_DAYS, (last - day).days + 1)
                requests.append((source, day, n))
                day += timedelta(days=n)
            if last >= first:
                cursor = last + timedelta(days=1)
    return requests


def _fetch_chunk(source: str, start: date, days: int) -> str:
    bbox = ",".join(str(v) for v in REGION_BBOX)
    dest = cache_path("firms", "area", f"{source}_{start.isoformat()}_{days}.csv")
    if dest.exists():
        return dest.read_text()
    text = _get(f"area/csv/{{key}}/{source}/{bbox}/{days}/{start.isoformat()}")
    if not text.startswith("latitude"):
        raise FirmsError(f"Unexpected FIRMS response for {source} {start}: {text[:80]!r}")
    settled = datetime.now(UTC).date() - timedelta(days=NRT_SETTLE_DAYS)
    if start + timedelta(days=days - 1) < settled:
        atomic_write_bytes(dest, text.encode())
    return text


def parse(text: str, source: str) -> pd.DataFrame:
    """Parse one FIRMS CSV, keeping the brief's columns plus UTC and IST datetimes."""
    df = pd.read_csv(io.StringIO(text), dtype={"acq_time": str, "confidence": str})
    df = df.reindex(columns=KEEP)
    df["acq_time"] = df["acq_time"].str.zfill(4)
    df["acq_dt_utc"] = pd.to_datetime(
        df["acq_date"] + " " + df["acq_time"], format="%Y-%m-%d %H%M", utc=True
    )
    df["acq_dt_ist"] = df["acq_dt_utc"].dt.tz_convert(IST)
    df["source"] = source
    df["sensor"] = "MODIS" if source.startswith("MODIS") else "VIIRS"
    return df


def fetch(start: date, end: date) -> pd.DataFrame:
    """All detections in the region bbox with acq_date in [start, end] (UTC dates)."""
    frames = [
        parse(_fetch_chunk(source, day, n), source)
        for source, day, n in plan_requests(start, end, data_availability())
    ]
    frames = [f for f in frames if len(f)]
    if not frames:
        return parse(",".join(KEEP) + "\n", "none")
    return pd.concat(frames, ignore_index=True).sort_values("acq_dt_utc", ignore_index=True)


def clip(
    df: pd.DataFrame, geometry: BaseGeometry, crs: str, buffer_m: float = 0.0
) -> gpd.GeoDataFrame:
    """Detections within `buffer_m` of `geometry` (EPSG:4326), returned as points in `crs`."""
    points = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs="EPSG:4326"
    ).to_crs(crs)
    area = gpd.GeoSeries([geometry], crs="EPSG:4326").to_crs(crs).iloc[0].buffer(buffer_m)
    return points[points.within(area)].reset_index(drop=True)


def is_confident_viirs(df: pd.DataFrame) -> pd.Series:
    """High- or nominal-confidence VIIRS detections (the calibration positives, brief §6.5)."""
    return (df["sensor"] == "VIIRS") & df["confidence"].str.lower().isin(["h", "n"])
