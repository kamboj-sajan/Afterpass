"""Per-district pipeline steps shared by the CLI commands."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pystac
from odc.geo.geobox import GeoBox
from rasterio import features
from rasterio.errors import RasterioIOError
from shapely.geometry.base import BaseGeometry

from afterpass import burns, calibrate, firms, match, places, sentinel, worldcover
from afterpass.config import CACHE_DIR, IST, season_window

# Sentinel-2 is needed before the window (the NBR reference) and after it (calibration samples).
S2_LEAD = timedelta(days=burns.LOOKBACK_DAYS)
S2_TAIL = calibrate.POSITIVE_MAX_AGE
# FIRMS is needed a week before the window so early positives have a pass to be sampled on.
FIRMS_LEAD = timedelta(days=7)
FIRMS_TAIL = timedelta(days=1)
# Detections just outside the boundary can still match scars near the edge (MODIS: 1 km).
FIRMS_BUFFER_M = 1000.0
LOAD_ROUNDS = 3


@dataclass(frozen=True)
class District:
    name: str
    slug: str
    geometry: BaseGeometry  # EPSG:4326
    geometry_utm: BaseGeometry
    geobox: GeoBox

    @property
    def crs(self) -> str:
        return str(self.geobox.crs)


def load_district(name: str) -> District:
    geometry = places.district_geometry(name)
    geobox = sentinel.district_geobox(geometry)
    return District(
        name=name,
        slug=name.lower().replace(" ", "_"),
        geometry=geometry,
        geometry_utm=sentinel.to_crs(geometry, str(geobox.crs)),
        geobox=geobox,
    )


def detection_mask(district: District) -> np.ndarray:
    """Cropland pixels inside the district polygon."""
    inside = features.geometry_mask(
        [district.geometry_utm],
        out_shape=(district.geobox.shape.y, district.geobox.shape.x),
        transform=district.geobox.affine,
        invert=True,
    )
    return inside & worldcover.cropland_mask(district.slug, district.geometry, district.geobox)


@dataclass(frozen=True)
class SceneSet:
    """Every Sentinel-2 date cached for a district, plus any that could not be downloaded."""

    days: dict[date, list[pystac.Item]]
    scenes: list[sentinel.Scene]
    missing: list[date]


def load_scenes(
    district: District,
    start: date,
    end: date,
    log: Callable[[str], None] = lambda _: None,
    tail: timedelta = S2_TAIL,
) -> SceneSet:
    """Search and cache every Sentinel-2 date needed to detect burns in [start, end].

    A date whose download fails is retried after the others. Dates still missing after
    LOAD_ROUNDS are returned in `missing` rather than raising, so one bad file does not lose
    an hour of downloads; callers must report them.
    """
    days = sentinel.search(district.geometry, start - S2_LEAD, end + tail)
    cached: dict[date, sentinel.Scene] = {}
    pending = list(days)
    for _ in range(LOAD_ROUNDS):
        failed = []
        for day in pending:
            try:
                cached[day] = sentinel.cache_scene(
                    district.slug, day, days[day], district.geobox, district.geometry
                )
            except RasterioIOError as exc:
                failed.append(day)
                log(f"{district.name}: Sentinel-2 {day} failed ({exc}); will retry")
                continue
            log(f"{district.name}: Sentinel-2 {day} ready ({len(cached)}/{len(days)})")
        pending = failed
        if not pending:
            break
    return SceneSet(days, [cached[day] for day in sorted(cached)], pending)


def load_detections(district: District, start: date, end: date) -> gpd.GeoDataFrame:
    """FIRMS detections in and just around the district, as points in its UTM CRS."""
    table = firms.fetch(start - FIRMS_LEAD, end + FIRMS_TAIL)
    return firms.clip(table, district.geometry, district.crs, buffer_m=FIRMS_BUFFER_M)


def in_district(detections: gpd.GeoDataFrame, district: District) -> gpd.GeoDataFrame:
    return detections[detections.within(district.geometry_utm)].reset_index(drop=True)


def replay_dir(season: int) -> Path:
    path = CACHE_DIR / "replay" / str(season)
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Replay:
    """One district's season: scars in its UTM CRS, FIRMS points inside it, run details."""

    district: District
    scars: gpd.GeoDataFrame
    detections: gpd.GeoDataFrame
    info: dict


def replay_district(
    name: str,
    season: int,
    localities: gpd.GeoDataFrame,
    log: Callable[[str], None] = lambda _: None,
) -> Replay:
    """Detect, match and locate every scar first seen in the season, then cache the result."""
    first, last = season_window(season)
    place = load_district(name)
    loaded = load_scenes(place, first, last, log=log, tail=timedelta(0))
    # A scar's window can open LOOKBACK_DAYS before the season, and matching allows a day more.
    nearby = firms.clip(
        firms.fetch(first - S2_LEAD - FIRMS_TAIL, last + FIRMS_TAIL),
        place.geometry,
        place.crs,
        buffer_m=FIRMS_BUFFER_M,
    )
    mask = detection_mask(place)
    thresholds = burns.Thresholds.load(burns.THRESHOLDS_PATH)
    scars, stats = burns.detect(
        loaded.scenes, mask, thresholds, place.geobox.affine, place.crs, place.name
    )
    days = scars["first_detected"]
    scars = scars[(days >= first.isoformat()) & (days <= last.isoformat())].reset_index(drop=True)
    scars["recorded"] = match.recorded(scars, nearby)
    scars = places.assign_villages(scars, localities)
    scars.insert(0, "scar_id", [f"{place.slug}-{i:06d}" for i in range(len(scars))])

    inside = in_district(nearby, place)
    dates = inside["acq_date"]
    inside = inside[(dates >= first.isoformat()) & (dates <= last.isoformat())]
    inside = inside.reset_index(drop=True)
    info = {
        "district": place.name,
        "season": season,
        "window": [first.isoformat(), last.isoformat()],
        "cropland_ha": round(float(mask.sum()) * place.geobox.resolution.x**2 / 10_000, 0),
        "sentinel2": stats,
        "missing_dates": [day.isoformat() for day in loaded.missing],
    }
    folder = replay_dir(season)
    scars.to_file(folder / f"{place.slug}_scars.fgb", driver="FlatGeobuf")
    columns = ["longitude", "latitude", "acq_date", "acq_dt_ist", "satellite", "source"]
    columns += ["confidence", "frp", "geometry"]
    inside[columns].to_file(folder / f"{place.slug}_firms.fgb", driver="FlatGeobuf")
    (folder / f"{place.slug}.json").write_text(json.dumps(info, indent=2) + "\n")
    # Read back what was written, so a fresh replay and a later `publish` see the same thing.
    return load_replay(name, season)


def load_replay(name: str, season: int) -> Replay:
    """Read back what replay_district cached."""
    place = load_district(name)
    folder = replay_dir(season)
    info_path = folder / f"{place.slug}.json"
    if not info_path.exists():
        raise FileNotFoundError(f"No replay for {name} {season}. Run `afterpass replay` first.")
    detections = gpd.read_file(folder / f"{place.slug}_firms.fgb")
    detections["acq_dt_ist"] = pd.to_datetime(detections["acq_dt_ist"], utc=True).dt.tz_convert(IST)
    scars = gpd.read_file(folder / f"{place.slug}_scars.fgb")
    # Some drivers hand date-like text back as timestamps; the pipeline keeps ISO strings.
    for frame, columns in (
        (scars, ("first_detected", "window_start")),
        (detections, ("acq_date",)),
    ):
        for column in columns:
            frame[column] = pd.to_datetime(frame[column]).dt.strftime("%Y-%m-%d")
    # FlatGeobuf stores features in spatial-index order; restore a stable one.
    scars = scars.sort_values("scar_id", ignore_index=True)
    order = ["acq_dt_ist", "longitude", "latitude", "source"]
    detections = detections.sort_values(order, ignore_index=True)
    return Replay(place, scars, detections, json.loads(info_path.read_text()))
