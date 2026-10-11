"""District boundaries (geoBoundaries gbOpen, IND) and villages (Overture Maps divisions)."""

from __future__ import annotations

import re
from functools import lru_cache

import duckdb
import geopandas as gpd
import httpx
import pandas as pd
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


OVERTURE_CATALOG = "https://stac.overturemaps.org/catalog.json"
OVERTURE_DIVISIONS = "s3://overturemaps-us-west-2/release/{release}/theme=divisions/type=division/*"
LOCALITY_SUBTYPES = ("locality", "neighborhood", "macrohood")
VILLAGE_RADIUS_M = 3000.0


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_localities() -> tuple[gpd.GeoDataFrame, str]:
    """Villages and urban localities in the region from Overture Maps divisions.

    Returns points (EPSG:4326) with `locality_id` and `name`, and the Overture release they
    came from. The newest cached release is reused; delete the cache file to refresh.
    """
    cached = sorted(cache_path("overture", "x").parent.glob("localities_*.csv"))
    if cached:
        dest = cached[-1]
    else:
        release = httpx.get(OVERTURE_CATALOG, timeout=60).raise_for_status().json()["latest"]
        dest = cache_path("overture", f"localities_{release}.csv")
        w, s, e, n = REGION_BBOX
        subtypes = ", ".join(f"'{t}'" for t in LOCALITY_SUBTYPES)
        tmp = dest.with_name(dest.name + ".part")
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
        con.execute("SET s3_region = 'us-west-2';")
        con.execute(
            f"""
            COPY (
                SELECT id, names.primary AS name, subtype, region,
                       ST_X(geometry) AS lon, ST_Y(geometry) AS lat
                FROM read_parquet('{OVERTURE_DIVISIONS.format(release=release)}',
                                  hive_partitioning = 1)
                WHERE country = 'IN' AND subtype IN ({subtypes})
                  AND names.primary IS NOT NULL
                  AND bbox.xmin BETWEEN {w} AND {e} AND bbox.ymin BETWEEN {s} AND {n}
                ORDER BY id
            ) TO '{tmp}' (FORMAT CSV, HEADER)
            """
        )
        tmp.replace(dest)
    # Names are text; without this, a village called "Nan" or "NA" is read as a missing value.
    table = pd.read_csv(dest, keep_default_na=False)
    table = table[table["name"].str.strip() != ""]
    points = gpd.GeoDataFrame(
        {
            "locality_id": table["id"].str[:8] + "-" + table["name"].map(_slug),
            "name": table["name"],
        },
        geometry=gpd.points_from_xy(table["lon"], table["lat"]),
        crs="EPSG:4326",
    )
    return points, dest.stem.removeprefix("localities_")


def assign_villages(scars: gpd.GeoDataFrame, localities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add `village_id`, `village` and `village_lon/lat` to scars (brief §9.1).

    Each scar takes the locality nearest its centroid. Beyond VILLAGE_RADIUS_M the scar is
    labelled "near <locality>" and kept apart from scars that are inside the radius. Scars
    must be in a projected CRS (metres); localities are reprojected to it.
    """
    centroids = gpd.GeoDataFrame(
        {"row": range(len(scars))}, geometry=scars.geometry.centroid.to_numpy(), crs=scars.crs
    )
    places_ = localities.to_crs(scars.crs)
    lonlat = localities.to_crs("EPSG:4326").geometry
    places_ = places_.assign(lon=lonlat.x.to_numpy(), lat=lonlat.y.to_numpy())
    nearest = gpd.sjoin_nearest(centroids, places_, how="left", distance_col="distance_m")
    nearest = nearest.drop_duplicates("row").sort_values("row")
    near_only = nearest["distance_m"].to_numpy() > VILLAGE_RADIUS_M
    ids, names = nearest["locality_id"].to_numpy(), nearest["name"].to_numpy()
    out = scars.copy()
    out["village_id"] = [f"near-{i}" if far else i for i, far in zip(ids, near_only, strict=True)]
    out["village"] = [f"near {n}" if far else n for n, far in zip(names, near_only, strict=True)]
    out["village_lon"] = nearest["lon"].to_numpy().round(5)
    out["village_lat"] = nearest["lat"].to_numpy().round(5)
    return out


def delhi_geometry() -> BaseGeometry:
    """NCT of Delhi (EPSG:4326): the union of its districts."""
    districts = load_districts()
    return districts[districts["state"] == "Delhi"].geometry.union_all()


def load_delhi_localities() -> tuple[gpd.GeoDataFrame, str]:
    """Delhi localities and neighbourhoods from Overture, with Hindi names where present.

    Kept apart from `load_localities` so adding the Hindi column does not change the village
    assignment of earlier runs. Returns points (EPSG:4326) with `locality_id`, `name`,
    `name_hi` (empty when Overture has none) and `district`, plus the Overture release.
    """
    cached = sorted(cache_path("overture", "x").parent.glob("delhi_localities_*.csv"))
    delhi = delhi_geometry()
    if cached:
        dest = cached[-1]
    else:
        release = httpx.get(OVERTURE_CATALOG, timeout=60).raise_for_status().json()["latest"]
        dest = cache_path("overture", f"delhi_localities_{release}.csv")
        w, s, e, n = delhi.buffer(0.02).bounds
        subtypes = ", ".join(f"'{t}'" for t in LOCALITY_SUBTYPES)
        tmp = dest.with_name(dest.name + ".part")
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
        con.execute("SET s3_region = 'us-west-2';")
        con.execute(
            f"""
            COPY (
                SELECT id, names.primary AS name, names.common['hi'] AS name_hi, subtype,
                       ST_X(geometry) AS lon, ST_Y(geometry) AS lat
                FROM read_parquet('{OVERTURE_DIVISIONS.format(release=release)}',
                                  hive_partitioning = 1)
                WHERE country = 'IN' AND subtype IN ({subtypes})
                  AND names.primary IS NOT NULL
                  AND bbox.xmin BETWEEN {w} AND {e} AND bbox.ymin BETWEEN {s} AND {n}
                ORDER BY id
            ) TO '{tmp}' (FORMAT CSV, HEADER)
            """
        )
        tmp.replace(dest)
    table = pd.read_csv(dest, keep_default_na=False)
    table = table[table["name"].str.strip() != ""]
    points = gpd.GeoDataFrame(
        {
            "locality_id": table["id"].str[:8] + "-" + table["name"].map(_slug),
            "name": table["name"],
            "name_hi": table["name_hi"].str.strip(),
        },
        geometry=gpd.points_from_xy(table["lon"], table["lat"]),
        crs="EPSG:4326",
    )
    districts = load_districts()
    zones = districts[districts["state"] == "Delhi"][["district", "geometry"]]
    points = gpd.sjoin(points, zones, predicate="within", how="inner").drop(columns="index_right")
    points = points.sort_values("locality_id").drop_duplicates("locality_id")
    return points.reset_index(drop=True), dest.stem.removeprefix("delhi_localities_")
