"""Quick-look PNG for visual QA: burn scars and FIRMS detections over true colour."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pystac
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from odc.geo.geobox import GeoBox
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from afterpass import sentinel

plt.switch_backend("Agg")

EMBER = "#FF6B1A"
CYAN = "#22D3EE"
INK = "#0B0F14"
OVERVIEW_RES_M = 40
INSET_RES_M = 10
INSET_SIZE_M = 3000
MAX_MOSAIC_DATES = 3


@dataclass(frozen=True)
class Inset:
    """A 3 km window with the pass before the burn and the pass that first showed it."""

    title: str
    bounds: tuple[float, float, float, float]
    pre: date
    post: date


def _extent(geobox: GeoBox) -> tuple[float, float, float, float]:
    b = geobox.boundingbox
    return (b.left, b.right, b.bottom, b.top)


def _brighten(rgb: np.ndarray) -> np.ndarray:
    """Mild stretch so hazy November scenes are readable in print."""
    return np.clip(rgb.astype(np.float32) * 1.35, 0, 255).astype(np.uint8)


def overview_mosaic(
    slug: str, days: dict[date, list[pystac.Item]], geobox: GeoBox, newest: date
) -> tuple[np.ndarray, list[date]]:
    """True colour for the whole district: the newest pass on or before `newest`, with gaps
    (the district sits on a swath edge) filled from the passes just before it."""
    rgb: np.ndarray | None = None
    used: list[date] = []
    for day in sorted((d for d in days if d <= newest), reverse=True):
        tile = sentinel.load_visual(slug, day, days[day], geobox, f"{OVERVIEW_RES_M}m")
        if rgb is None:
            rgb = tile.copy()
        else:
            empty = ~rgb.any(axis=-1)
            rgb[empty] = tile[empty]
        used.append(day)
        if rgb.any(axis=-1).mean() > 0.995 or len(used) == MAX_MOSAIC_DATES:
            break
    if rgb is None:
        raise ValueError(f"No Sentinel-2 pass on or before {newest}")
    return rgb, used


def pick_insets(scars: gpd.GeoDataFrame, recorded: np.ndarray, count: int = 4) -> list[Inset]:
    """Deterministic examples: the 3 km cell with the most recorded burned area, then the cells
    with the most unrecorded burned area."""
    if len(scars) == 0:
        return []
    centroids = scars.geometry.centroid
    cells = scars.assign(
        cx=(centroids.x // INSET_SIZE_M).astype(int),
        cy=(centroids.y // INSET_SIZE_M).astype(int),
        recorded_ha=np.where(recorded, scars["area_ha"], 0.0),
        unrecorded_ha=np.where(recorded, 0.0, scars["area_ha"]),
    )
    totals = cells.groupby(["cx", "cy"])[["recorded_ha", "unrecorded_ha"]].sum()
    chosen = [("Recorded by FIRMS", totals["recorded_ha"].idxmax())]
    for cell in totals["unrecorded_ha"].sort_values(ascending=False).index:
        if len(chosen) == count:
            break
        if all(max(abs(cell[0] - c[0]), abs(cell[1] - c[1])) > 1 for _, c in chosen):
            chosen.append(("Not in FIRMS", cell))
    insets = []
    for label, (cx, cy) in chosen:
        members = cells[(cells["cx"] == cx) & (cells["cy"] == cy)]
        # Show the date pair that accounts for most of the cell's burned area.
        pair = members.groupby(["window_start", "first_detected"])["area_ha"].sum().idxmax()
        x0, y0 = cx * INSET_SIZE_M, cy * INSET_SIZE_M
        insets.append(
            Inset(
                label,
                (x0, y0, x0 + INSET_SIZE_M, y0 + INSET_SIZE_M),
                date.fromisoformat(pair[0]),
                date.fromisoformat(pair[1]),
            )
        )
    return insets


def _in_dates(detections: gpd.GeoDataFrame, first: date, last: date) -> gpd.GeoDataFrame:
    days = detections["acq_date"]
    return detections[(days >= first.isoformat()) & (days <= last.isoformat())]


def render(
    path: Path,
    *,
    district: str,
    slug: str,
    geometry_utm: BaseGeometry,
    geobox: GeoBox,
    days: dict[date, list[pystac.Item]],
    scars: gpd.GeoDataFrame,
    recorded: np.ndarray,
    detections: gpd.GeoDataFrame,
    start: date,
    end: date,
) -> None:
    """Write the quick-look. `scars` and `detections` are in the grid's UTM CRS.

    The left panel shows the whole district. Each row on the right is one 3 km example: the
    pass before the burn, the pass that first showed it, and that pass again with the detected
    scars outlined and the FIRMS detections from the same days.
    """
    crs = str(geobox.crs)
    overview_box = GeoBox.from_bbox(geometry_utm.bounds, crs=crs, resolution=OVERVIEW_RES_M)
    rgb, used = overview_mosaic(slug, days, overview_box, end)
    insets = pick_insets(scars, recorded)
    in_window = _in_dates(detections, start, end)

    rows = max(len(insets), 1)
    fig = plt.figure(figsize=(21, 4.3 * rows), facecolor=INK)
    grid = fig.add_gridspec(
        rows, 5, width_ratios=[2.4, 2.4, 1.6, 1.6, 1.6], wspace=0.04, hspace=0.12
    )
    ax = fig.add_subplot(grid[:, :2])
    ax.imshow(_brighten(rgb), extent=_extent(overview_box), interpolation="bilinear")
    gpd.GeoSeries([geometry_utm]).boundary.plot(ax=ax, color="white", linewidth=0.8)
    if len(scars):
        scars.plot(ax=ax, color=EMBER, edgecolor="none")
    if len(in_window):
        ax.scatter(
            in_window.geometry.x,
            in_window.geometry.y,
            s=7,
            c=CYAN,
            edgecolors=INK,
            linewidths=0.3,
            zorder=5,
        )
    for number, inset in enumerate(insets, 1):
        x0, y0, x1, y1 = inset.bounds
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color="white", linewidth=1.2, zorder=6)
        ax.text(x1 + 400, y1, str(number), color="white", fontsize=12, fontweight="bold", va="top")
    burned = float(scars["area_ha"].sum()) if len(scars) else 0.0
    ax.set_title(
        f"{district}: burn scars first seen {start:%-d %b} to {end:%-d %b %Y}\n"
        f"{len(scars):,} scars, {burned:,.0f} ha  |  {len(in_window):,} FIRMS detections in "
        f"those dates  |  imagery {', '.join(f'{d:%-d %b}' for d in used)}",
        color="white",
        fontsize=12,
        loc="left",
    )
    ax.legend(
        handles=[
            Patch(facecolor=EMBER, label="Burn scar (Sentinel-2, 20 m)"),
            Line2D([], [], marker="o", linestyle="", color=CYAN, markersize=5, label="FIRMS fire"),
            Line2D([], [], color="white", linewidth=0.8, label="District boundary"),
        ],
        loc="lower left",
        facecolor=INK,
        edgecolor="none",
        labelcolor="white",
        fontsize=9,
    )
    ax.set_axis_off()

    one_day = timedelta(days=1)
    for row, inset in enumerate(insets):
        window = box(*inset.bounds)
        inset_box = GeoBox.from_bbox(inset.bounds, crs=crs, resolution=INSET_RES_M)
        tag = f"inset_{int(inset.bounds[0])}_{int(inset.bounds[1])}"
        local_scars = scars[scars.intersects(window)]
        local_fires = _in_dates(detections, inset.pre - one_day, inset.post + one_day)
        local_fires = local_fires[local_fires.within(window)]
        panels = (
            (inset.pre, f"{row + 1}. {inset.title}\nbefore, {inset.pre:%-d %b}", False),
            (inset.post, f"\nafter, {inset.post:%-d %b}", False),
            (inset.post, f"\nafter, scars outlined, {len(local_fires)} FIRMS fires", True),
        )
        for col, (day, title, overlay) in enumerate(panels):
            panel = fig.add_subplot(grid[row, 2 + col])
            if day in days:
                image = sentinel.load_visual(slug, day, days[day], inset_box, tag)
                panel.imshow(_brighten(image), extent=_extent(inset_box), interpolation="nearest")
            if overlay and len(local_scars):
                local_scars.boundary.plot(ax=panel, color=EMBER, linewidth=1.1)
            if overlay and len(local_fires):
                panel.scatter(
                    local_fires.geometry.x,
                    local_fires.geometry.y,
                    s=40,
                    facecolors="none",
                    edgecolors=CYAN,
                    linewidths=1.5,
                    zorder=5,
                )
            panel.set_xlim(inset.bounds[0], inset.bounds[2])
            panel.set_ylim(inset.bounds[1], inset.bounds[3])
            panel.set_title(title, color="white", fontsize=10, loc="left")
            panel.set_axis_off()

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=INK, bbox_inches="tight")
    plt.close(fig)
