"""Aggregate scars and FIRMS detections into the metrics the app shows (brief §7, §9.1)."""

from __future__ import annotations

from datetime import date

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry

H3_RESOLUTION = 8
# H3 only returns cells whose centre is inside the polygon, so the district is padded by more
# than one cell width (about 0.9 km at resolution 8) before asking for its cells.
CELL_PADDING_DEG = 0.02
AREA_COLUMNS = ["burned_ha", "recorded_ha", "unrecorded_ha"]


def iso_week(day: str) -> str:
    """ISO week label such as 2025-W44 for a YYYY-MM-DD date."""
    year, week, _ = date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02d}"


def with_areas(scars: gpd.GeoDataFrame) -> pd.DataFrame:
    """Scar attributes with the area split into recorded and unrecorded hectares."""
    table = pd.DataFrame(scars.drop(columns="geometry"))
    table["burned_ha"] = table["area_ha"]
    table["recorded_ha"] = table["area_ha"].where(table["recorded"], 0.0)
    table["unrecorded_ha"] = table["area_ha"].where(~table["recorded"], 0.0)
    table["week"] = table["first_detected"].map(iso_week)
    return table


def totals(table: pd.DataFrame) -> dict:
    """Burned, recorded and unrecorded hectares, the unrecorded share and the scar count."""
    burned = float(table["burned_ha"].sum())
    unrecorded = float(table["unrecorded_ha"].sum())
    return {
        "burned_ha": round(burned, 1),
        "recorded_ha": round(float(table["recorded_ha"].sum()), 1),
        "unrecorded_ha": round(unrecorded, 1),
        "unrecorded_share": round(unrecorded / burned, 3) if burned else None,
        "scar_count": int(len(table)),
    }


def series(table: pd.DataFrame, by: str) -> list[dict]:
    """Totals per value of `by` (a day or week column), in order."""
    return [{by: key, **totals(group)} for key, group in table.groupby(by, sort=True)]


def h3_cells(geometry: BaseGeometry, crs: str) -> gpd.GeoDataFrame:
    """Resolution-8 cells covering a district (EPSG:4326 polygon), as polygons in `crs`."""
    padded = geometry.buffer(CELL_PADDING_DEG)
    ids = sorted(h3.geo_to_cells(mapping(padded), H3_RESOLUTION))
    polygons = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]) for cell in ids]
    return gpd.GeoDataFrame({"h3": ids}, geometry=polygons, crs="EPSG:4326").to_crs(crs)


def burns_by_h3_week(scars: gpd.GeoDataFrame, cells: gpd.GeoDataFrame) -> pd.DataFrame:
    """Burned hectares per H3 cell and ISO week. A scar spanning cells is split by area."""
    columns = ["h3", "week", *AREA_COLUMNS]
    if len(scars) == 0:
        return pd.DataFrame(columns=columns)
    shapes = scars[["first_detected", "recorded", "geometry"]]
    pieces = gpd.overlay(shapes, cells, how="intersection", keep_geom_type=True)
    pieces["burned_ha"] = pieces.geometry.area / 10_000
    pieces["recorded_ha"] = pieces["burned_ha"].where(pieces["recorded"], 0.0)
    pieces["unrecorded_ha"] = pieces["burned_ha"].where(~pieces["recorded"], 0.0)
    pieces["week"] = pieces["first_detected"].map(iso_week)
    out = pieces.groupby(["h3", "week"], sort=True)[AREA_COLUMNS].sum().reset_index()
    return out[columns]


def villages(table: pd.DataFrame) -> list[dict]:
    """One record per village with season totals and a weekly series, largest gap first."""
    records = []
    for (district, village_id), group in table.groupby(["district", "village_id"], sort=True):
        summary = totals(group)
        records.append(
            {
                "id": village_id,
                "name": group["village"].iloc[0],
                "district": district,
                "lon": float(group["village_lon"].iloc[0]),
                "lat": float(group["village_lat"].iloc[0]),
                "burned_ha": summary["burned_ha"],
                "unrecorded_ha": summary["unrecorded_ha"],
                "share": summary["unrecorded_share"],
                "weekly": [
                    {k: row[k] for k in ("week", "burned_ha", "unrecorded_ha")}
                    for row in series(group, "week")
                ],
            }
        )
    return sorted(records, key=lambda r: (-r["unrecorded_ha"], r["id"]))


def firms_counts(detections: pd.DataFrame) -> dict:
    """FIRMS detection counts in total, by satellite, by day and by IST hour."""
    hours = detections["acq_dt_ist"].dt.hour.value_counts()
    return {
        "firms_count": int(len(detections)),
        "by_satellite": {
            str(k): int(v) for k, v in detections["source"].value_counts().sort_index().items()
        },
        "by_day": {
            str(k): int(v) for k, v in detections["acq_date"].value_counts().sort_index().items()
        },
        "by_ist_hour": [int(hours.get(hour, 0)) for hour in range(24)],
    }
