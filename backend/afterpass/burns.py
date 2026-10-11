"""Burn-scar detection from Sentinel-2 at 20 m (brief §6).

The functions here are pure array maths. Dates are streamed one at a time and only per-pixel
state is kept between them, so memory stays at about one scene.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from affine import Affine
from rasterio import features
from scipy import ndimage
from shapely.geometry import shape

from afterpass.sentinel import Scene

INVALID_SCL = (0, 1, 6, 8, 9, 10, 11)
CLOUD_SCL = (8, 9, 10)
SHADOW_SCL = 3
CLOUD_PROB_MAX = 30
SHADOW_NEAR_CLOUD_M = 1000.0
LOOKBACK_DAYS = 20
MIN_AREA_HA = 0.5
SIMPLIFY_M = 10.0
EIGHT_CONNECTED = np.ones((3, 3), bool)
THRESHOLDS_PATH = Path(__file__).with_name("thresholds.json")


@dataclass(frozen=True)
class Thresholds:
    """Starting guesses from the brief; calibrate.py writes the calibrated set."""

    t_nbr: float = 0.0
    t_mirbi: float = 1.6
    t_nir: float = 0.20
    t_dnbr: float = 0.10

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Thresholds:
        return cls(**json.loads(path.read_text()))


def valid_mask(
    scl: np.ndarray, cloud_prob: np.ndarray, nodata: np.ndarray, pixel_m: float = 20.0
) -> np.ndarray:
    """Usable pixels (brief §6.2), before the cropland restriction.

    SCL 2 (dark area) stays valid because fresh char is often labelled that way. SCL 3 (cloud
    shadow) is only invalid within about 1 km of cloud; isolated "shadows" over farmland are
    often burn scars.
    """
    valid = ~nodata & (cloud_prob < CLOUD_PROB_MAX) & ~np.isin(scl, INVALID_SCL)
    shadow = scl == SHADOW_SCL
    cloud = np.isin(scl, CLOUD_SCL)
    if shadow.any() and cloud.any():
        distance_m = ndimage.distance_transform_edt(~cloud, sampling=pixel_m)
        valid &= ~(shadow & (distance_m <= SHADOW_NEAR_CLOUD_M))
    return valid


def indices(b8a: np.ndarray, b11: np.ndarray, b12: np.ndarray) -> tuple[np.ndarray, ...]:
    """NBR, NBR2 and MIRBI from 0-1 reflectance (brief §6.3). Zero denominators give NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        nbr = np.where(b8a + b12 != 0, (b8a - b12) / (b8a + b12), np.nan)
        nbr2 = np.where(b11 + b12 != 0, (b11 - b12) / (b11 + b12), np.nan)
    mirbi = 10.0 * b12 - 9.8 * b11 + 2.0
    return nbr.astype(np.float32), nbr2.astype(np.float32), mirbi.astype(np.float32)


def char_signature(
    nbr: np.ndarray, mirbi: np.ndarray, b8a: np.ndarray, th: Thresholds
) -> np.ndarray:
    """Dark, char-like pixels: low NBR, high MIRBI, low near-infrared."""
    return (nbr < th.t_nbr) & (mirbi > th.t_mirbi) & (b8a < th.t_nir)


class PixelState:
    """What is remembered per pixel between dates. Days are proleptic ordinals; 0 means none."""

    def __init__(self, shape: tuple[int, int]) -> None:
        self.last_nbr = np.full(shape, np.nan, np.float32)
        self.last_day = np.zeros(shape, np.int32)
        self.first_detected = np.zeros(shape, np.int32)

    def nbr_drop(self, day: date, valid: np.ndarray, nbr: np.ndarray) -> np.ndarray:
        """NBR at the last valid observation minus NBR now. NaN where there is no valid
        observation in the previous LOOKBACK_DAYS."""
        age = day.toordinal() - self.last_day
        usable = valid & (self.last_day > 0) & (age <= LOOKBACK_DAYS)
        return np.where(usable, self.last_nbr - nbr, np.nan).astype(np.float32)

    def observe(self, day: date, valid: np.ndarray, nbr: np.ndarray) -> None:
        """Record today's valid pixels as the latest observation."""
        self.last_nbr[valid] = nbr[valid]
        self.last_day[valid] = day.toordinal()


def fresh_burn(
    state: PixelState,
    day: date,
    valid: np.ndarray,
    nbr: np.ndarray,
    mirbi: np.ndarray,
    b8a: np.ndarray,
    th: Thresholds,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the "freshly burned at t" rule (brief §6.4) and advance the state.

    Returns the fresh-burn mask and, for those pixels, the ordinal of the previous valid
    observation (the start of the window in which the burn happened).
    """
    drop = state.nbr_drop(day, valid, nbr)
    fresh = (
        valid
        & char_signature(nbr, mirbi, b8a, th)
        & (drop > th.t_dnbr)
        & (state.first_detected == 0)
    )
    window_start = np.where(fresh, state.last_day, 0).astype(np.int32)
    state.first_detected[fresh] = day.toordinal()
    state.observe(day, valid, nbr)
    return fresh, window_start


def clean_components(fresh: np.ndarray, pixel_m: float = 20.0) -> tuple[np.ndarray, int]:
    """3x3 opening, 8-connected labelling, then drop components under MIN_AREA_HA.

    Returns a label image (0 = background) and the number of scars kept.
    """
    opened = ndimage.binary_opening(fresh, structure=EIGHT_CONNECTED)
    labels, count = ndimage.label(opened, structure=EIGHT_CONNECTED)
    if count == 0:
        return labels, 0
    min_pixels = int(np.ceil(MIN_AREA_HA * 10_000 / pixel_m**2))
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    keep = sizes >= min_pixels
    keep[0] = False
    relabel = np.zeros(count + 1, np.int32)
    relabel[keep] = np.arange(1, int(keep.sum()) + 1)
    return relabel[labels], int(keep.sum())


def _majority_window_start(labels: np.ndarray, count: int, window_start: np.ndarray) -> np.ndarray:
    """Most common window-start ordinal per label; ties go to the earliest date."""
    best = np.zeros(count + 1, np.int32)
    best_votes = np.zeros(count + 1, np.int64)
    inside = labels > 0
    for ordinal in np.unique(window_start[inside]):
        votes = np.bincount(labels[inside & (window_start == ordinal)], minlength=count + 1)
        better = votes > best_votes
        best[better] = ordinal
        best_votes[better] = votes[better]
    return best


def vectorise(
    fresh: np.ndarray,
    window_start: np.ndarray,
    day: date,
    transform: Affine,
    crs: str,
    district: str,
) -> gpd.GeoDataFrame:
    """Turn one date's fresh-burn mask into scar polygons with attributes (brief §6.6)."""
    labels, count = clean_components(fresh, pixel_m=abs(transform.a))
    columns = ["district", "first_detected", "window_start", "area_ha", "geometry"]
    if count == 0:
        return gpd.GeoDataFrame({c: [] for c in columns}, geometry="geometry", crs=crs)
    starts = _majority_window_start(labels, count, window_start)
    polygons: dict[int, list] = {}
    for geom, value in features.shapes(
        labels.astype(np.int32), mask=labels > 0, connectivity=8, transform=transform
    ):
        polygons.setdefault(int(value), []).append(shape(geom))
    rows = []
    for label, parts in sorted(polygons.items()):
        geom = gpd.GeoSeries(parts).union_all().simplify(SIMPLIFY_M, preserve_topology=True)
        rows.append(
            {
                "district": district,
                "first_detected": day.isoformat(),
                "window_start": date.fromordinal(int(starts[label])).isoformat(),
                "area_ha": round(geom.area / 10_000, 3),
                "geometry": geom,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


@dataclass(frozen=True)
class Observation:
    """One date's cropland-valid mask and the layers the rule needs."""

    scene: Scene
    valid: np.ndarray
    nbr: np.ndarray
    mirbi: np.ndarray
    b8a: np.ndarray


def observations(scenes: Iterable[Scene], mask: np.ndarray) -> Iterator[Observation]:
    """Stream scenes in date order. `mask` is cropland inside the district."""
    for scene in sorted(scenes, key=lambda s: s.day):
        data = scene.read()
        valid = valid_mask(data.scl, data.cloud, data.nodata) & mask
        nbr, _, mirbi = indices(data.b8a, data.b11, data.b12)
        yield Observation(scene, valid, nbr, mirbi, data.b8a)


def detect(
    scenes: Iterable[Scene],
    mask: np.ndarray,
    th: Thresholds,
    transform: Affine,
    crs: str,
    district: str,
) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """Run the rule over every date. Returns scars (in `crs`) and per-date statistics."""
    state = PixelState(mask.shape)
    frames, stats = [], []
    cropland_px = int(mask.sum())
    for obs in observations(scenes, mask):
        fresh, window_start = fresh_burn(
            state, obs.scene.day, obs.valid, obs.nbr, obs.mirbi, obs.b8a, th
        )
        scars = vectorise(fresh, window_start, obs.scene.day, transform, crs, district)
        frames.append(scars)
        stats.append(
            {
                "date": obs.scene.day.isoformat(),
                "valid_pct": round(100 * float(obs.valid.sum()) / cropland_px, 1),
                "scars": len(scars),
                "burned_ha": round(float(scars["area_ha"].sum()), 1),
            }
        )
    non_empty = [f for f in frames if len(f)]
    scars = gpd.GeoDataFrame(
        pd.concat(non_empty, ignore_index=True) if non_empty else frames[0],
        geometry="geometry",
        crs=crs,
    )
    return scars, stats
