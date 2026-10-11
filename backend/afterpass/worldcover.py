"""ESA WorldCover 2021 cropland mask on a district grid (brief §5.3)."""

from __future__ import annotations

import math

import numpy as np
import rasterio
from odc.geo.geobox import GeoBox
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage
from shapely.geometry.base import BaseGeometry

from afterpass.cache import cache_path

# The bucket lives in eu-central-1; the regional HTTPS endpoint avoids a redirect per request.
TILE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
TILE_DEG = 3
CROPLAND = 40


def tile_names(bounds: tuple[float, float, float, float]) -> list[str]:
    """Names of the 3-degree tiles (labelled by south-west corner) touching lon/lat bounds."""
    west, south, east, north = bounds
    names = []
    for lat in range(_floor_tile(south), _floor_tile(north) + 1, TILE_DEG):
        for lon in range(_floor_tile(west), _floor_tile(east) + 1, TILE_DEG):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            names.append(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
    return names


def _floor_tile(value: float) -> int:
    return math.floor(value / TILE_DEG) * TILE_DEG


def cropland_mask(slug: str, geometry: BaseGeometry, geobox: GeoBox) -> np.ndarray:
    """True where WorldCover is cropland (class 40), dilated by one pixel, on `geobox`."""
    path = cache_path("worldcover", f"{slug}_cropland.tif")
    if path.exists():
        with rasterio.open(path) as src:
            return src.read(1).astype(bool)

    shape = (geobox.shape.y, geobox.shape.x)
    classes = np.zeros(shape, np.uint8)
    for tile in tile_names(geometry.bounds):
        part = np.zeros(shape, np.uint8)
        with rasterio.open(TILE_URL.format(tile=tile)) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=part,
                dst_transform=geobox.affine,
                dst_crs=str(geobox.crs),
                dst_nodata=0,
                resampling=Resampling.nearest,
            )
        classes = np.where(part > 0, part, classes)

    cropland = ndimage.binary_dilation(classes == CROPLAND, structure=np.ones((3, 3), bool))
    tmp = path.with_name(path.name + ".part")
    profile = {
        "driver": "GTiff",
        "height": shape[0],
        "width": shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": str(geobox.crs),
        "transform": geobox.affine,
        "compress": "deflate",
    }
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(cropland.astype(np.uint8), 1)
    tmp.replace(path)
    return cropland
