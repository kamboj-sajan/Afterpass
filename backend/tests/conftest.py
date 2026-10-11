import json
from datetime import UTC, date, datetime, time

import numpy as np
import pytest
import rasterio
from affine import Affine

from afterpass.sentinel import BANDS, Scene

TRANSFORM = Affine(20, 0, 500_000, 0, -20, 3_400_000)
CRS = "EPSG:32643"
SCALE, OFFSET = 0.0001, -0.1


@pytest.fixture
def make_scene(tmp_path):
    """Write a cached-scene GeoTIFF from 0-1 reflectance arrays, as sentinel.cache_scene does."""

    def _make(day: date, b8a, b11, b12, scl=None, cloud=None, hour_utc: int = 5) -> Scene:
        shape = np.shape(b8a)
        scl = np.full(shape, 5) if scl is None else scl
        cloud = np.zeros(shape) if cloud is None else cloud
        dn = [np.round((np.asarray(band) - OFFSET) / SCALE) for band in (b8a, b11, b12)]
        stack = np.stack([*dn, scl, cloud]).astype(np.uint16)
        acquired = datetime.combine(day, time(hour_utc, 40), tzinfo=UTC)
        path = tmp_path / f"{day.isoformat()}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=shape[0],
            width=shape[1],
            count=len(BANDS),
            dtype="uint16",
            crs=CRS,
            transform=TRANSFORM,
        ) as dst:
            dst.write(stack)
            dst.update_tags(
                acquired=acquired.isoformat(),
                scale_offset=json.dumps({b: [SCALE, OFFSET] for b in BANDS[:3]}),
            )
        return Scene(day, acquired, path)

    return _make


@pytest.fixture
def make_wind():
    """A WindField on the real grid with the same u, v and mixing height everywhere."""
    from afterpass import winds

    def _make(u, v, pbl=500.0, hours=3, start=0) -> winds.WindField:
        shape = (hours, len(winds.GRID_LATS), len(winds.GRID_LONS))
        return winds.WindField(
            times=int(start) + np.arange(hours, dtype=np.int64) * 3600,
            lats=winds.GRID_LATS,
            lons=winds.GRID_LONS,
            u=np.array(np.broadcast_to(u, shape), dtype=float),
            v=np.array(np.broadcast_to(v, shape), dtype=float),
            pbl=np.array(np.broadcast_to(pbl, shape), dtype=float),
            source="test",
        )

    return _make
