"""Visual QA: a labelling sheet for detected scars and random cropland, and the precision it
gives (brief §14.2)."""

from __future__ import annotations

import base64
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pystac
import rasterio
from odc.geo.geobox import GeoBox
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry

from afterpass import sentinel
from afterpass.pipeline import Replay

QA_SCARS = 100
QA_POINTS = 100
SEED = 2025
CHIP_M = 600
CHIP_RES_M = 10
CHIP_SCALE = 4
POINT_BOX_M = 60.0
CHIP_THREADS = 12
EMBER = (255, 107, 26)
Z_95 = 1.959964


@dataclass(frozen=True)
class QAItem:
    """One thing to label: a detected scar, or a random cropland point with a date pair."""

    id: str
    kind: str  # "scar" or "point"
    district: str
    slug: str
    crs: str
    lon: float
    lat: float
    pre: str
    post: str
    detected: bool  # for points: whether the rule flagged this spot on the "after" pass
    outline: list[list[float]]  # ring in the district's UTM CRS


def wilson(successes: int, total: int, z: float = Z_95) -> tuple[float, float] | None:
    """Wilson score interval for a proportion; None when there is nothing to count."""
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - half), min(1.0, centre + half)


def _lonlat(crs: str, x: float, y: float) -> tuple[float, float]:
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return round(lon, 5), round(lat, 5)


def _largest_ring(geometry: BaseGeometry) -> list[list[float]]:
    polygon = max(getattr(geometry, "geoms", [geometry]), key=lambda g: g.area)
    return [[round(x, 1), round(y, 1)] for x, y in polygon.exterior.coords]


def sample_scars(replays: list[Replay], rng: np.random.Generator, count: int) -> list[QAItem]:
    """Scars drawn uniformly at random from every district's detections."""
    pool = [(r, i) for r in replays for i in range(len(r.scars))]
    chosen = rng.choice(len(pool), size=min(count, len(pool)), replace=False)
    items = []
    for index in sorted(chosen):
        replay, row = pool[index]
        scar = replay.scars.iloc[row]
        centre = scar.geometry.representative_point()
        lon, lat = _lonlat(replay.district.crs, centre.x, centre.y)
        items.append(
            QAItem(
                id=scar["scar_id"],
                kind="scar",
                district=replay.district.name,
                slug=replay.district.slug,
                crs=replay.district.crs,
                lon=lon,
                lat=lat,
                pre=scar["window_start"],
                post=scar["first_detected"],
                detected=True,
                outline=_largest_ring(scar.geometry),
            )
        )
    return items


def sample_points(
    replays: list[Replay],
    masks: dict[str, np.ndarray],
    scenes: dict[str, list[sentinel.Scene]],
    rng: np.random.Generator,
    count: int,
) -> list[QAItem]:
    """Random cropland pixels, each with a random pass in the season and the valid pass
    before it. Districts are drawn in proportion to their cropland."""
    cropland = {r.district.slug: np.flatnonzero(masks[r.district.slug]) for r in replays}
    weights = np.array([len(cropland[r.district.slug]) for r in replays], float)
    items: list[QAItem] = []
    while len(items) < count:
        replay = replays[rng.choice(len(replays), p=weights / weights.sum())]
        slug, place = replay.district.slug, replay.district
        pixel = int(cropland[slug][rng.integers(len(cropland[slug]))])
        row, col = divmod(pixel, masks[slug].shape[1])
        x, y = place.geobox.affine * (col + 0.5, row + 0.5)
        first, last = replay.info["window"]
        in_season = [s for s in scenes[slug] if first <= s.day.isoformat() <= last]
        post = in_season[rng.integers(len(in_season))]
        earlier = [s for s in scenes[slug] if s.day < post.day]
        if not _has_data(post, row, col):
            continue
        pre = next((s for s in reversed(earlier) if _has_data(s, row, col)), None)
        if pre is None:
            continue
        here = Point(x, y)
        same_day = replay.scars[replay.scars["first_detected"] == post.day.isoformat()]
        detected = bool(same_day.intersects(here).any())
        lon, lat = _lonlat(place.crs, x, y)
        half = POINT_BOX_M / 2
        items.append(
            QAItem(
                id=f"{slug}-point-{len(items):03d}",
                kind="point",
                district=place.name,
                slug=slug,
                crs=place.crs,
                lon=lon,
                lat=lat,
                pre=pre.day.isoformat(),
                post=post.day.isoformat(),
                detected=detected,
                outline=_largest_ring(box(x - half, y - half, x + half, y + half)),
            )
        )
    return items


def _has_data(scene: sentinel.Scene, row: int, col: int) -> bool:
    with rasterio.open(scene.path) as src:
        scl = src.read(sentinel.BANDS.index("scl") + 1, window=((row, row + 1), (col, col + 1)))
    return bool(scl[0, 0] != sentinel.NODATA)


def _chip_bounds(item: QAItem) -> tuple[float, float, float, float]:
    xs = [p[0] for p in item.outline]
    ys = [p[1] for p in item.outline]
    cx = round((min(xs) + max(xs)) / 2 / CHIP_RES_M) * CHIP_RES_M
    cy = round((min(ys) + max(ys)) / 2 / CHIP_RES_M) * CHIP_RES_M
    half = CHIP_M / 2
    return (cx - half, cy - half, cx + half, cy + half)


def chip(item: QAItem, day: str, items: list[pystac.Item]) -> str:
    """True-colour chip around the item with its outline drawn, as a base64 WebP data URI."""
    bounds = _chip_bounds(item)
    geobox = GeoBox.from_bbox(bounds, crs=item.crs, resolution=CHIP_RES_M)
    tag = f"qa_{int(bounds[0])}_{int(bounds[1])}"
    rgb = sentinel.load_visual(item.slug, date.fromisoformat(day), items, geobox, tag)
    size = rgb.shape[0] * CHIP_SCALE
    image = Image.fromarray(rgb).resize((size, size), Image.Resampling.BICUBIC)
    scale = CHIP_SCALE / CHIP_RES_M
    ring = [((x - bounds[0]) * scale, (bounds[3] - y) * scale) for x, y in item.outline]
    ImageDraw.Draw(image).line(ring, fill=EMBER, width=2)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=82)
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()


def build_sheet(
    items: list[QAItem],
    days: dict[str, dict[date, list[pystac.Item]]],
    season: int,
    html_path: Path,
    items_path: Path,
) -> None:
    """Write the self-contained labelling page and the list of items it shows."""

    def render(item: QAItem) -> dict:
        tiles = days[item.slug]
        return {
            "id": item.id,
            "district": item.district,
            "pre_date": item.pre,
            "post_date": item.post,
            "pre": chip(item, item.pre, tiles[date.fromisoformat(item.pre)]),
            "post": chip(item, item.post, tiles[date.fromisoformat(item.post)]),
        }

    with ThreadPoolExecutor(CHIP_THREADS) as pool:
        cards = list(pool.map(render, items))
    template = Path(__file__).with_name("qa_sheet.html").read_text()
    page = template.replace("__SEASON__", str(season)).replace("__ITEMS__", json.dumps(cards))
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page)
    items_path.parent.mkdir(parents=True, exist_ok=True)
    listing = [{k: v for k, v in asdict(i).items() if k != "outline"} for i in items]
    items_path.write_text(json.dumps({"season": season, "items": listing}, indent=2) + "\n")


def score(items: list[dict], labels: dict[str, str]) -> dict:
    """Precision on detected scars, and how many burned-looking random points were detected.

    Labels are "b" (burned), "n" (not burned) or "u" (unsure). Unsure and unlabelled items are
    left out of both proportions and counted separately.
    """

    def proportion(successes: int, total: int) -> dict:
        interval = wilson(successes, total)
        return {
            "value": round(successes / total, 3) if total else None,
            "wilson_95": None if interval is None else [round(v, 3) for v in interval],
            "n": total,
        }

    scars = [i for i in items if i["kind"] == "scar"]
    points = [i for i in items if i["kind"] == "point"]
    scar_labels = [labels.get(i["id"]) for i in scars]
    burned_points = [i for i in points if labels.get(i["id"]) == "b"]
    return {
        "precision": proportion(
            scar_labels.count("b"), scar_labels.count("b") + scar_labels.count("n")
        ),
        "scars": {
            "sampled": len(scars),
            "burned": scar_labels.count("b"),
            "not_burned": scar_labels.count("n"),
            "unsure": scar_labels.count("u"),
            "unlabelled": scar_labels.count(None),
        },
        "detected_share_of_burned_points": proportion(
            sum(1 for i in burned_points if i["detected"]), len(burned_points)
        ),
        "points": {
            "sampled": len(points),
            "burned": len(burned_points),
            "not_burned": sum(1 for i in points if labels.get(i["id"]) == "n"),
            "unsure": sum(1 for i in points if labels.get(i["id"]) == "u"),
            "unlabelled": sum(1 for i in points if labels.get(i["id"]) is None),
        },
    }
