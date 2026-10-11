"""Before/after imagery crops for the villages with the most unrecorded burning (brief §9.3).

Crops are stored per season, `imagery/{season}/{village_id}/`, so a village's live-season crops
never replace its replay crops. Each season has its own `imagery/{season}/index.json`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pystac
import rasterio
from odc.geo.geobox import GeoBox
from PIL import Image
from pyproj import Transformer
from rasterio.windows import from_bounds

from afterpass import aggregate, sentinel
from afterpass.config import PUBLIC_DIR, season_window
from afterpass.pipeline import S2_LEAD, Replay

plt.switch_backend("Agg")

# Crops are rendered for this many villages, ranked by area not in official counts.
TOP_VILLAGES = 20
CROP_M = 1500
CROP_PX = 512
TRUE_COLOUR_RES_M = 10
# Reflectance mapped to full brightness in the SWIR composite (B12, B8A, B4 as red, green,
# blue). Fixed, so the before and after crops are directly comparable.
SWIR_STRETCH = (0.45, 0.45, 0.30)
RENDER_THREADS = 6
INK = "#0B0F14"


def season_dir(season: int) -> Path:
    """Where a season's crops live: one folder per village, plus index.json."""
    return PUBLIC_DIR / "imagery" / str(season)


@dataclass(frozen=True)
class Crop:
    """Where and when to crop for one village."""

    village_id: str
    name: str
    district: str
    slug: str
    crs: str
    bounds: tuple[float, float, float, float]
    pre: date
    post: date
    village_unrecorded_ha: float
    window_burned_ha: float
    window_unrecorded_ha: float


def pick_crops(replays: list[Replay], top: int) -> list[Crop]:
    """The `top` villages by unrecorded area. Each crop is the 1.5 km grid square holding most
    of the village's unrecorded burned area, shown for the date pair that explains most of it."""
    ranked = []
    for replay in replays:
        table = aggregate.with_areas(replay.scars)
        for record in aggregate.villages(table):
            ranked.append((record, replay))
    ranked.sort(key=lambda pair: (-pair[0]["unrecorded_ha"], pair[0]["id"]))

    crops = []
    for record, replay in ranked[:top]:
        scars = replay.scars[replay.scars["village_id"] == record["id"]]
        centroids = scars.geometry.centroid
        cells = scars.assign(
            cx=(centroids.x // CROP_M).astype(int),
            cy=(centroids.y // CROP_M).astype(int),
            unrecorded_ha=scars["area_ha"].where(~scars["recorded"], 0.0),
        )
        cx, cy = cells.groupby(["cx", "cy"])["unrecorded_ha"].sum().idxmax()
        members = cells[(cells["cx"] == cx) & (cells["cy"] == cy)]
        pre, post = members.groupby(["window_start", "first_detected"])["area_ha"].sum().idxmax()
        crops.append(
            Crop(
                village_id=record["id"],
                name=record["name"],
                district=record["district"],
                slug=replay.district.slug,
                crs=replay.district.crs,
                bounds=(cx * CROP_M, cy * CROP_M, (cx + 1) * CROP_M, (cy + 1) * CROP_M),
                pre=date.fromisoformat(pre),
                post=date.fromisoformat(post),
                village_unrecorded_ha=record["unrecorded_ha"],
                window_burned_ha=round(float(members["area_ha"].sum()), 1),
                window_unrecorded_ha=round(float(members["unrecorded_ha"].sum()), 1),
            )
        )
    return crops


def _resize(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(rgb).resize((CROP_PX, CROP_PX), Image.Resampling.BICUBIC)


def true_colour(crop: Crop, day: date, items: list[pystac.Item]) -> Image.Image:
    geobox = GeoBox.from_bbox(crop.bounds, crs=crop.crs, resolution=TRUE_COLOUR_RES_M)
    tag = f"crop_{int(crop.bounds[0])}_{int(crop.bounds[1])}"
    return _resize(sentinel.load_visual(crop.slug, day, items, geobox, tag))


def swir_colour(
    crop: Crop, day: date, items: list[pystac.Item], scene: sentinel.Scene
) -> Image.Image:
    """SWIR false colour: B12 and B8A from the cached 20 m stack, B4 read at 10 m."""
    with rasterio.open(scene.path) as src:
        window = from_bounds(*crop.bounds, transform=src.transform).round_offsets().round_lengths()
        nir = src.read(sentinel.BANDS.index("nir08") + 1, window=window)
        swir = src.read(sentinel.BANDS.index("swir22") + 1, window=window)
    geobox = GeoBox.from_bbox(crop.bounds, crs=crop.crs, resolution=TRUE_COLOUR_RES_M)
    tag = f"crop_{int(crop.bounds[0])}_{int(crop.bounds[1])}"
    red = sentinel.load_asset(crop.slug, day, items, geobox, tag, asset="red")[..., 0]
    layers = (
        np.kron(sentinel.reflectance(items, "swir22", swir), np.ones((2, 2), np.float32)),
        np.kron(sentinel.reflectance(items, "nir08", nir), np.ones((2, 2), np.float32)),
        sentinel.reflectance(items, "red", red),
    )
    nodata = np.kron(swir == sentinel.NODATA, np.ones((2, 2), bool)) | (red == sentinel.NODATA)
    rgb = np.stack(
        [np.clip(layer / top, 0, 1) for layer, top in zip(layers, SWIR_STRETCH, strict=True)],
        axis=-1,
    )
    rgb[nodata] = 0
    return _resize((rgb * 255).astype(np.uint8))


def render(
    crop: Crop,
    days: dict[date, list[pystac.Item]],
    scenes: dict[date, sentinel.Scene],
    meta: dict,
    season: int,
) -> dict:
    """Write the four WebP crops and meta.json for one village. Returns the metadata."""
    folder = season_dir(season) / crop.village_id
    folder.mkdir(parents=True, exist_ok=True)
    for label, day in (("pre", crop.pre), ("post", crop.post)):
        true_colour(crop, day, days[day]).save(folder / f"{label}_tc.webp", "WEBP", quality=85)
        swir_colour(crop, day, days[day], scenes[day]).save(
            folder / f"{label}_swir.webp", "WEBP", quality=85
        )
    to_lonlat = Transformer.from_crs(crop.crs, "EPSG:4326", always_xy=True)
    west, south, east, north = to_lonlat.transform_bounds(*crop.bounds)
    record = {
        "season": season,
        "village_id": crop.village_id,
        "name": crop.name,
        "district": crop.district,
        "pre_date": crop.pre.isoformat(),
        "post_date": crop.post.isoformat(),
        "bounds": [round(v, 5) for v in (west, south, east, north)],
        "size_m": CROP_M,
        "village_unrecorded_ha": crop.village_unrecorded_ha,
        "window_burned_ha": crop.window_burned_ha,
        "window_unrecorded_ha": crop.window_unrecorded_ha,
        "files": {
            "pre_tc": "pre_tc.webp",
            "post_tc": "post_tc.webp",
            "pre_swir": "pre_swir.webp",
            "post_swir": "post_swir.webp",
        },
        **meta,
    }
    (folder / "meta.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def render_all(
    crops: list[Crop],
    days: dict[str, dict[date, list[pystac.Item]]],
    scenes: dict[str, dict[date, sentinel.Scene]],
    meta: dict,
    season: int,
) -> list[dict]:
    """Render every crop, a few at a time (the reads are network-bound)."""
    with ThreadPoolExecutor(RENDER_THREADS) as pool:
        return list(
            pool.map(lambda c: render(c, days[c.slug], scenes[c.slug], meta, season), crops)
        )


def needed_scenes(crops: list[Crop]) -> dict[str, set[date]]:
    """The Sentinel-2 dates each district's crops are drawn from: their before and after."""
    needed: dict[str, set[date]] = {}
    for crop in crops:
        needed.setdefault(crop.slug, set()).update((crop.pre, crop.post))
    return needed


def render_season(
    season: int,
    replays: list[Replay],
    top: int,
    meta: dict,
    log: Callable[[str], None] = lambda _: None,
) -> list[dict]:
    """Crops for the season's `top` villages, written to imagery/{season}/.

    Only the scenes the crops are drawn from are loaded. Each comes from the local scene cache
    when it is there (the pipeline pulls those files first) and is downloaded otherwise.
    Villages that dropped out of the top list lose their folders, so no crop shows stale
    numbers.
    """
    crops = pick_crops(replays, top)
    first, last = season_window(season)
    days: dict[str, dict[date, list[pystac.Item]]] = {}
    scenes: dict[str, dict[date, sentinel.Scene]] = {}
    for replay in replays:
        place = replay.district
        wanted = needed_scenes(crops).get(place.slug, set())
        if not wanted:
            continue
        # The same search as the replay's, so its cached STAC results are reused.
        found = sentinel.search(place.geometry, first - S2_LEAD, last)
        days[place.slug] = found
        scenes[place.slug] = {
            day: sentinel.cache_scene(place.slug, day, found[day], place.geobox, place.geometry)
            for day in sorted(wanted)
        }
        log(f"{place.name}: {len(wanted)} Sentinel-2 dates for its crops")
    records = render_all(crops, days, scenes, meta, season)
    keep = {record["village_id"] for record in records}
    folder = season_dir(season)
    if folder.exists():
        for child in folder.iterdir():
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child)
    return records


def contact_sheet(records: list[dict], path: Path) -> None:
    """One PNG with a row per village: true colour before/after, then SWIR before/after."""
    columns = (
        ("pre_tc", "before"),
        ("post_tc", "after"),
        ("pre_swir", "before, SWIR"),
        ("post_swir", "after, SWIR"),
    )
    fig, axes = plt.subplots(
        len(records), 4, figsize=(14, 3.7 * len(records)), facecolor=INK, squeeze=False
    )
    for row, record in zip(axes, records, strict=True):
        folder = season_dir(record["season"]) / record["village_id"]
        for ax, (key, label) in zip(row, columns, strict=True):
            ax.imshow(Image.open(folder / record["files"][key]))
            day = record["pre_date"] if key.startswith("pre") else record["post_date"]
            ax.set_title(f"{label}, {date.fromisoformat(day):%-d %b}", color="white", fontsize=9)
            ax.set_axis_off()
        row[0].text(
            0,
            1.16,
            f"{record['name']}, {record['district']}: {record['village_unrecorded_ha']:,.0f} ha "
            f"not in FIRMS this season ({record['window_unrecorded_ha']:,.0f} ha in this "
            f"{record['size_m'] / 1000:g} km square)",
            transform=row[0].transAxes,
            color="white",
            fontsize=11,
            fontweight="bold",
        )
    fig.subplots_adjust(hspace=0.32, wspace=0.03)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, facecolor=INK, bbox_inches="tight")
    plt.close(fig)
