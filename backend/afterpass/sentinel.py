"""Sentinel-2 L2A from Element 84 Earth Search (brief §5.2).

Each clear date is loaded once on the district's UTM grid at 20 m and cached as a compressed
GeoTIFF of raw digital numbers, so reruns read from disk and memory holds one date at a time.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import odc.stac
import pystac
import rasterio
from odc.geo.geobox import GeoBox
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.warp import reproject
from rasterio.windows import Window
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from afterpass.cache import cache_path

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
RESOLUTION = 20
MAX_TILE_CLOUD = 60
# The brief also lists `red`, but no index in the detection rule uses it and the download link
# is the slowest step, so it is left out of the stack. True colour comes from `visual`.
REFLECTANCE_BANDS = ("nir08", "swir16", "swir22")
BANDS = (*REFLECTANCE_BANDS, "scl", "cloud")
NODATA = 0
# A tile is skipped when it adds less than this much district area to tiles already chosen.
MIN_NEW_AREA_M2 = 50_000
# Internal tile size of the 20 m COGs. Reads are cut along these rows so that parallel requests
# never fetch the same block twice. A wrong value only costs speed, never correctness.
COG_BLOCK = 512
# One connection to us-west-2 from India carries roughly 200 KB/s, so speed comes from many
# parallel range requests.
READ_THREADS = 24
READ_ATTEMPTS = 6
CLIP_BUFFER_M = 500.0
# Scenes are published within days of acquisition; older windows are safe to cache.
SEARCH_SETTLE = timedelta(days=10)

# pystac's storage-extension migration warns on every Earth Search item; it does not affect reads.
warnings.filterwarnings("ignore", message="Could not parse bucket/account from href")


def utm_crs(geometry: BaseGeometry) -> str:
    """EPSG code of the UTM zone holding the geometry's centroid (northern hemisphere)."""
    zone = int((geometry.centroid.x + 180) // 6) + 1
    return f"EPSG:326{zone:02d}"


def to_crs(geometry: BaseGeometry, crs: str) -> BaseGeometry:
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    return shapely_transform(project, geometry)


def district_geobox(geometry: BaseGeometry, resolution: float = RESOLUTION) -> GeoBox:
    """Grid covering the district in its UTM zone, with pixel edges on multiples of the
    resolution. That matches the native Sentinel-2 grid, so 20 m bands are read unresampled."""
    crs = utm_crs(geometry)
    return GeoBox.from_bbox(to_crs(geometry, crs).bounds, crs=crs, resolution=resolution)


def solar_day(item: pystac.Item) -> date:
    assert item.datetime is not None
    lon = item.properties.get("proj:centroid", {}).get("lon", 0.0)
    return (item.datetime + timedelta(hours=lon / 15)).date()


def _find_items(geometry: BaseGeometry, start: date, end: date) -> list[pystac.Item]:
    """STAC search, cached once the window is old enough that no new scenes will appear."""
    key = f"{COLLECTION}|{geometry.envelope.wkt}|{start}|{end}|{MAX_TILE_CLOUD}"
    path = cache_path("stac", f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json")
    if path.exists():
        return list(pystac.ItemCollection.from_file(str(path)))
    client = Client.open(STAC_URL)
    found = client.search(
        collections=[COLLECTION],
        intersects=geometry.envelope,
        datetime=f"{start.isoformat()}/{end.isoformat()}T23:59:59Z",
        query={"eo:cloud_cover": {"lt": MAX_TILE_CLOUD}},
    )
    items = list(found.items())
    if end < datetime.now(UTC).date() - SEARCH_SETTLE:
        tmp = path.with_name(path.name + ".part")
        pystac.ItemCollection(items).save_object(str(tmp))
        tmp.replace(path)
    return items


def search(geometry: BaseGeometry, start: date, end: date) -> dict[date, list[pystac.Item]]:
    """Scenes covering the district with tile cloud cover under 60%, grouped by solar day."""
    by_day: dict[date, list[pystac.Item]] = defaultdict(list)
    for item in _find_items(geometry, start, end):
        by_day[solar_day(item)].append(item)
    pruned = {day: prune(by_day[day], geometry) for day in sorted(by_day)}
    return {day: items for day, items in pruned.items() if items}


def prune(items: list[pystac.Item], district: BaseGeometry) -> list[pystac.Item]:
    """Drop tiles that add no district coverage. MGRS tiles overlap by about 10 km, and the
    search also returns neighbours that only touch the district's bounding box."""
    footprints = {i.id: shape(i.geometry).buffer(0) for i in items if i.geometry}
    ranked = sorted(items, key=lambda i: -footprints[i.id].intersection(district).area)
    kept: list[pystac.Item] = []
    remaining = district
    crs = utm_crs(district)
    for item in ranked:
        gain = to_crs(remaining.intersection(footprints[item.id]), crs).area
        if gain >= MIN_NEW_AREA_M2:
            kept.append(item)
            remaining = remaining.difference(footprints[item.id])
    return sorted(kept, key=lambda i: i.id)


def _scale_offset(items: list[pystac.Item], band: str) -> tuple[float, float]:
    """Scale and offset from `raster:bands`, which must agree across one day's items."""
    pairs = set()
    for item in items:
        meta = item.assets[band].extra_fields["raster:bands"][0]
        pairs.add((float(meta["scale"]), float(meta["offset"])))
    if len(pairs) != 1:
        raise ValueError(f"Mixed scale/offset for {band} on one date: {sorted(pairs)}")
    return pairs.pop()


@dataclass(frozen=True)
class _Strip:
    """One block-row of a source tile and where it lands on the district grid."""

    window: Window
    rows: slice
    cols: slice


def _strips(item: pystac.Item, geobox: GeoBox, clip: BaseGeometry) -> list[_Strip] | None:
    """Block-row strips of the item's 20 m grid that overlap `clip` (in the grid's CRS).

    Returns None when the item is not on the district's CRS and pixel grid, in which case the
    caller falls back to a resampling read.
    """
    asset = item.assets[BANDS[0]].extra_fields
    res = float(geobox.resolution.x)
    a, _, left, _, e, top = asset["proj:transform"][:6]
    height, width = asset["proj:shape"]
    box_ = geobox.boundingbox
    same_grid = (
        item.properties.get("proj:code") == str(geobox.crs)
        and a == res
        and e == -res
        and (left - box_.left) % res == 0
        and (top - box_.top) % res == 0
    )
    if not same_grid:
        return None

    x0, x1 = max(left, box_.left), min(left + width * res, box_.right)
    y0, y1 = max(top - height * res, box_.bottom), min(top, box_.top)
    if x0 >= x1 or y0 >= y1:
        return []
    row_start, row_stop = round((top - y1) / res), round((top - y0) / res)
    strips = []
    for block_row in range(row_start - row_start % COG_BLOCK, row_stop, COG_BLOCK):
        r0, r1 = max(block_row, row_start), min(block_row + COG_BLOCK, row_stop)
        part = clip.intersection(box(x0, top - r1 * res, x1, top - r0 * res))
        if part.is_empty:
            continue
        c0 = max(round((x0 - left) / res), math.floor((part.bounds[0] - left) / res))
        c1 = min(round((x1 - left) / res), math.ceil((part.bounds[2] - left) / res))
        dst_row = round((box_.top - (top - r0 * res)) / res)
        dst_col = round((left + c0 * res - box_.left) / res)
        strips.append(
            _Strip(
                Window(c0, r0, c1 - c0, r1 - r0),
                slice(dst_row, dst_row + r1 - r0),
                slice(dst_col, dst_col + c1 - c0),
            )
        )
    return strips


def _read_window(href: str, window: Window) -> np.ndarray:
    """Read one window, retrying on network errors.

    A cut-off transfer can stay in GDAL's process-wide /vsicurl cache, where a plain retry
    would read the same truncated bytes again. Retries therefore add a query string, which S3
    ignores and GDAL treats as a different file.
    """
    for attempt in range(READ_ATTEMPTS):
        url = href if attempt == 0 else f"{href}?attempt={attempt}"
        try:
            with rasterio.open(url) as src:
                return src.read(1, window=window)
        except RasterioIOError:
            if attempt == READ_ATTEMPTS - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def _read_native(items: list[pystac.Item], geobox: GeoBox, clip: BaseGeometry) -> np.ndarray | None:
    """Mosaic the day's tiles onto the district grid with parallel block-aligned reads.

    Tiles are pasted in id order and a pixel is taken from the first tile whose SCL is not
    no-data, so every band of a pixel comes from the same tile.
    """
    plans = {item.id: _strips(item, geobox, clip) for item in items}
    if any(plan is None for plan in plans.values()):
        return None

    jobs = [
        (item.id, k, band, item.assets[band].href, strip.window)
        for item in items
        for k, strip in enumerate(plans[item.id] or [])
        for band in BANDS
    ]
    with ThreadPoolExecutor(READ_THREADS) as pool:
        arrays = list(pool.map(lambda job: _read_window(job[3], job[4]), jobs))
    pieces = {job[:3]: array for job, array in zip(jobs, arrays, strict=True)}

    out = np.zeros((len(BANDS), geobox.shape.y, geobox.shape.x), np.uint16)
    scl = BANDS.index("scl")
    for item in sorted(items, key=lambda i: i.id):
        for k, strip in enumerate(plans[item.id] or []):
            stack = np.stack([pieces[(item.id, k, band)] for band in BANDS]).astype(np.uint16)
            target = out[:, strip.rows, strip.cols]
            fill = (stack[scl] != NODATA) & (target[scl] == NODATA)
            target[:, fill] = stack[:, fill]
    return out


def _load_odc(
    items: list[pystac.Item], bands: tuple[str, ...], geobox: GeoBox, resampling: str
) -> np.ndarray:
    """Resampling read through odc-stac, for anything not on the native 20 m grid."""
    data = odc.stac.load(
        items,
        bands=list(bands),
        geobox=geobox,
        groupby="solar_day",
        resampling=resampling,
        chunks={"x": -1, "y": -1},
    )
    if data.sizes["time"] != 1:
        raise ValueError(f"Expected one solar day, got {data.sizes['time']}")
    loaded = data.isel(time=0).compute(scheduler="threads", num_workers=len(bands))
    return np.stack([loaded[band].to_numpy() for band in bands])


@dataclass(frozen=True)
class SceneData:
    """Reflectance (0-1 scale) and quality layers for one date."""

    day: date
    b8a: np.ndarray
    b11: np.ndarray
    b12: np.ndarray
    scl: np.ndarray
    cloud: np.ndarray
    nodata: np.ndarray


@dataclass(frozen=True)
class Scene:
    """One cached date on the district grid."""

    day: date
    acquired: datetime  # mean acquisition time of the day's items, UTC
    path: Path

    def read(self) -> SceneData:
        with rasterio.open(self.path) as src:
            dn = src.read()
            scales = json.loads(src.tags()["scale_offset"])
        bands = dict(zip(BANDS, dn, strict=True))
        nodata = bands["scl"] == NODATA
        for band in REFLECTANCE_BANDS:
            nodata |= bands[band] == NODATA
        reflectance = {}
        for band in REFLECTANCE_BANDS:
            scale, offset = scales[band]
            reflectance[band] = bands[band].astype(np.float32) * np.float32(scale) + np.float32(
                offset
            )
        return SceneData(
            day=self.day,
            b8a=reflectance["nir08"],
            b11=reflectance["swir16"],
            b12=reflectance["swir22"],
            scl=bands["scl"].astype(np.uint8),
            cloud=bands["cloud"].astype(np.uint8),
            nodata=nodata,
        )


def cache_scene(
    slug: str, day: date, items: list[pystac.Item], geobox: GeoBox, district: BaseGeometry
) -> Scene:
    """Load one date onto the district grid, or reuse the cached GeoTIFF.

    Pixels more than CLIP_BUFFER_M outside the district polygon are left as no-data.
    """
    path = cache_path("s2", slug, f"{day.isoformat()}.tif")
    if path.exists():
        with rasterio.open(path) as src:
            acquired = datetime.fromisoformat(src.tags()["acquired"])
        return Scene(day, acquired, path)

    scales = {band: _scale_offset(items, band) for band in REFLECTANCE_BANDS}
    clip = to_crs(district, str(geobox.crs)).buffer(CLIP_BUFFER_M)
    dn = _read_native(items, geobox, clip)
    if dn is None:
        dn = _load_odc(items, BANDS, geobox, "nearest").astype(np.uint16)
    stamps = [i.datetime.timestamp() for i in items if i.datetime]
    acquired = datetime.fromtimestamp(sum(stamps) / len(stamps), tz=UTC)

    tmp = path.with_name(path.name + ".part")
    profile = {
        "driver": "GTiff",
        "height": geobox.shape.y,
        "width": geobox.shape.x,
        "count": len(BANDS),
        "dtype": "uint16",
        "crs": str(geobox.crs),
        "transform": geobox.affine,
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 2,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(dn)
        dst.descriptions = BANDS
        dst.update_tags(
            acquired=acquired.isoformat(),
            scale_offset=json.dumps(scales),
            items=json.dumps([i.id for i in items]),
            collection=COLLECTION,
        )
    tmp.replace(path)
    return Scene(day, acquired, path)


def _read_visual_tile(href: str, geobox: GeoBox) -> np.ndarray:
    """One tile's `visual` asset warped onto `geobox`, read from the coarsest overview that
    still resolves the target pixel size (the asset is 10 m; overviews halve each level)."""
    factor = float(geobox.resolution.x) / 10.0
    level = int(math.log2(factor)) - 1 if factor >= 2 else None
    out = np.zeros((3, geobox.shape.y, geobox.shape.x), np.uint8)
    for attempt in range(READ_ATTEMPTS):
        try:
            options = {} if level is None else {"overview_level": level}
            with rasterio.open(href, **options) as src:
                reproject(
                    source=rasterio.band(src, [1, 2, 3]),
                    destination=out,
                    dst_transform=geobox.affine,
                    dst_crs=str(geobox.crs),
                    src_nodata=0,
                    dst_nodata=0,
                    resampling=Resampling.bilinear,
                )
            return out
        except RasterioIOError:
            if attempt == READ_ATTEMPTS - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def load_visual(
    slug: str, day: date, items: list[pystac.Item], geobox: GeoBox, tag: str
) -> np.ndarray:
    """8-bit true colour (H, W, 3) on `geobox`, cached as a GeoTIFF named by `tag`.

    Black (0, 0, 0) means no data on that date.
    """
    path = cache_path("s2_visual", slug, f"{day.isoformat()}_{tag}.tif")
    if not path.exists():
        extent = Transformer.from_crs(str(geobox.crs), "EPSG:4326", always_xy=True)
        bounds = box(*extent.transform_bounds(*geobox.boundingbox))
        covering = [i for i in items if i.geometry and shape(i.geometry).intersects(bounds)]
        hrefs = [item.assets["visual"].href for item in sorted(covering, key=lambda i: i.id)]
        if not hrefs:
            return np.zeros((geobox.shape.y, geobox.shape.x, 3), np.uint8)
        with ThreadPoolExecutor(len(hrefs)) as pool:
            tiles = list(pool.map(lambda href: _read_visual_tile(href, geobox), hrefs))
        rgb = tiles[0]
        for tile in tiles[1:]:
            empty = ~rgb.any(axis=0)
            rgb[:, empty] = tile[:, empty]
        tmp = path.with_name(path.name + ".part")
        profile = {
            "driver": "GTiff",
            "height": geobox.shape.y,
            "width": geobox.shape.x,
            "count": 3,
            "dtype": "uint8",
            "crs": str(geobox.crs),
            "transform": geobox.affine,
            "compress": "deflate",
        }
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(rgb)
        tmp.replace(path)
    with rasterio.open(path) as src:
        return np.moveaxis(src.read(), 0, -1)
