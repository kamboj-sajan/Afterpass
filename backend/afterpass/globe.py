"""Country outlines for the hero globe, from Natural Earth's India point-of-view dataset.

The India point of view draws India's boundaries as India does (brief §5.5). The 10 m file is
13 MB; the globe draws land as dots, so a heavily simplified copy is enough.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import geopandas as gpd

from afterpass.cache import cache_path, download
from afterpass.config import REPO_ROOT

SOURCE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_10m_admin_0_countries_ind.geojson"
)
OUTPUT = REPO_ROOT / "frontend" / "public" / "globe" / "countries_ind.json"
SIMPLIFY_DEG = 0.25
# Islands smaller than this (square degrees) would not hold a single dot.
MIN_AREA_DEG2 = 0.3
COORDINATE_DECIMALS = 2


def build(output: Path = OUTPUT) -> tuple[Path, int]:
    """Download (once), simplify and write the globe's country outlines. Returns path and count."""
    source = download(SOURCE, cache_path("naturalearth", "ne_10m_admin_0_countries_ind.geojson"))
    countries = gpd.read_file(source)[["NAME", "ADM0_A3", "geometry"]]
    countries = countries.rename(columns={"NAME": "name", "ADM0_A3": "code"})
    parts = countries.explode(index_parts=False, ignore_index=True)
    with warnings.catch_warnings():
        # Areas in square degrees are only used to drop specks; no projection is needed.
        warnings.simplefilter("ignore", UserWarning)
        parts = parts[parts.geometry.area >= MIN_AREA_DEG2]
    parts = parts.set_geometry(parts.geometry.simplify(SIMPLIFY_DEG, preserve_topology=True))
    parts = parts.set_geometry(parts.geometry.set_precision(10**-COORDINATE_DECIMALS))
    parts = parts[~parts.geometry.is_empty]
    merged = parts.dissolve(by=["code", "name"], as_index=False)
    payload = json.loads(merged.to_json(drop_id=True))
    payload["source"] = (
        "Natural Earth, 1:10m Admin 0 countries, India point of view (public domain)"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return output, len(merged)
