"""Per-district pipeline steps shared by the CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import geopandas as gpd
import numpy as np
import pystac
from odc.geo.geobox import GeoBox
from rasterio import features
from shapely.geometry.base import BaseGeometry

from afterpass import burns, calibrate, firms, places, sentinel, worldcover

# Sentinel-2 is needed before the window (the NBR reference) and after it (calibration samples).
S2_LEAD = timedelta(days=burns.LOOKBACK_DAYS)
S2_TAIL = calibrate.POSITIVE_MAX_AGE
# FIRMS is needed a week before the window so early positives have a pass to be sampled on.
FIRMS_LEAD = timedelta(days=7)
FIRMS_TAIL = timedelta(days=1)
# Detections just outside the boundary can still match scars near the edge (MODIS: 1 km).
FIRMS_BUFFER_M = 1000.0


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


def load_scenes(
    district: District,
    start: date,
    end: date,
    log: Callable[[str], None] = lambda _: None,
) -> tuple[dict[date, list[pystac.Item]], list[sentinel.Scene]]:
    """Search and cache every Sentinel-2 date needed to detect burns in [start, end]."""
    days = sentinel.search(district.geometry, start - S2_LEAD, end + S2_TAIL)
    scenes = []
    for day, items in days.items():
        scenes.append(
            sentinel.cache_scene(district.slug, day, items, district.geobox, district.geometry)
        )
        log(f"Sentinel-2 {day} ready ({len(scenes)}/{len(days)})")
    return days, scenes


def load_detections(district: District, start: date, end: date) -> gpd.GeoDataFrame:
    """FIRMS detections in and just around the district, as points in its UTM CRS."""
    table = firms.fetch(start - FIRMS_LEAD, end + FIRMS_TAIL)
    return firms.clip(table, district.geometry, district.crs, buffer_m=FIRMS_BUFFER_M)


def in_district(detections: gpd.GeoDataFrame, district: District) -> gpd.GeoDataFrame:
    return detections[detections.within(district.geometry_utm)].reset_index(drop=True)
