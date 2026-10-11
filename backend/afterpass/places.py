"""District boundaries from geoBoundaries (gbOpen, IND). Villages and localities come in Phase 2."""

from __future__ import annotations

from functools import lru_cache

import geopandas as gpd
import httpx
from shapely.geometry.base import BaseGeometry

from afterpass.cache import cache_path, download
from afterpass.config import REGION_BBOX

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/IND/{level}/"
# geoBoundaries ADM1 spellings -> the names we show.
STATE_NAMES = {"Punjab": "Punjab", "Haryāna": "Haryana", "Delhi": "Delhi"}


def _boundaries(level: str) -> gpd.GeoDataFrame:
    dest = cache_path("boundaries", f"geoBoundaries-IND-{level}.geojson")
    if not dest.exists():
        meta = httpx.get(GB_API.format(level=level), timeout=60).raise_for_status().json()
        download(meta["gjDownloadURL"], dest)
    return gpd.read_file(dest)


@lru_cache
def load_districts() -> gpd.GeoDataFrame:
    """Districts of Punjab, Haryana and Delhi with columns `district`, `state`, `geometry`.

    ADM2 has no state column, so each district takes the state its interior point falls in.
    """
    dest = cache_path("boundaries", "districts_pb_hr_dl.geojson")
    if dest.exists():
        return gpd.read_file(dest)
    w, s, e, n = REGION_BBOX
    adm2 = _boundaries("ADM2").cx[w:e, s:n].reset_index(drop=True)
    adm1 = _boundaries("ADM1")
    states = adm1[adm1["shapeName"].isin(STATE_NAMES)][["shapeName", "geometry"]]
    points = gpd.GeoDataFrame(
        {"district": adm2["shapeName"].to_numpy()},
        geometry=adm2.geometry.representative_point().to_numpy(),
        crs=adm2.crs,
    )
    joined = gpd.sjoin(points, states, predicate="within", how="inner")
    out = gpd.GeoDataFrame(
        {
            "district": joined["district"].to_numpy(),
            "state": joined["shapeName"].map(STATE_NAMES).to_numpy(),
        },
        geometry=adm2.geometry.loc[joined.index].to_numpy(),
        crs=adm2.crs,
    )
    out = out.sort_values(["state", "district"]).reset_index(drop=True)
    out.to_file(dest, driver="GeoJSON")
    return out


def district_geometry(name: str) -> BaseGeometry:
    """Polygon (EPSG:4326) for one district, matched case-insensitively."""
    districts = load_districts()
    match = districts[districts["district"].str.casefold() == name.casefold()]
    if len(match) != 1:
        raise ValueError(f"Expected exactly one district named {name!r}, found {len(match)}.")
    return match.geometry.iloc[0]
