"""Write the public data-contract files (brief §9.2) to `data/public/`.

Every file carries `generated_at`, `source_versions` and `"demo": false`. Files the brief lists
as arrays are wrapped as `{..., "items": [...]}` so they can hold that metadata; GeoJSON files
carry it as top-level members next to `features`. Scars are split into one file per district
and ISO week (`scars/{district}/{week}.geojson`) instead of the brief's one file per district.
`imagery/index.json` lists the villages that have crops.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import geopandas as gpd
import pandas as pd

from afterpass import aggregate, burns, places, sentinel
from afterpass.config import PUBLIC_DIR, SEASONS, VALIDATION_DIR
from afterpass.pipeline import Replay

COORDINATE_DECIMALS = 5  # about 1 m
DISTRICT_SIMPLIFY_DEG = 0.001  # about 100 m
LIMITATIONS = [
    "Clouds and haze leave gaps in the imagery.",
    "Sentinel-2 revisits every 2-5 days, so scars tilled under before the next clear pass are "
    "missed. Detections are a lower bound.",
    "The time a field was lit is unknown; a scar is dated by the pass that first showed it.",
    "Fields under 0.5 ha are missed.",
    "FIRMS counts are fire pixels, not fields. Compare areas, not counts.",
]


def _write(path: Path, payload: dict, *, pretty: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) if pretty else json.dumps(payload, separators=(",", ":"))
    path.write_text(text + "\n")
    return path


def _firms_items(replay: Replay) -> list[dict]:
    table = replay.detections
    return [
        {
            "lon": round(float(row.longitude), 4),
            "lat": round(float(row.latitude), 4),
            "ist": row.acq_dt_ist.isoformat(timespec="minutes"),
            "sat": str(row.satellite),
            "conf": str(row.confidence),
            "frp": None if pd.isna(row.frp) else round(float(row.frp), 1),
            "district": replay.district.name,
        }
        for row in table.itertuples()
    ]


def _scars_by_week(replay: Replay) -> dict[str, dict]:
    """Scar polygons as one GeoJSON FeatureCollection per ISO week of first detection."""
    columns = ["scar_id", "first_detected", "window_start", "area_ha", "recorded", "village_id"]
    shapes = replay.scars[[*columns, "geometry"]].to_crs("EPSG:4326")
    shapes = shapes.set_geometry(shapes.geometry.set_precision(10**-COORDINATE_DECIMALS))
    weeks = shapes["first_detected"].map(aggregate.iso_week)
    return {
        week: json.loads(part.to_json(drop_id=True)) | {"week": week}
        for week, part in shapes.groupby(weeks, sort=True)
    }


def metadata(replays: list[Replay], overture_release: str) -> dict:
    """The provenance block every public file carries."""
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_versions": {
            "afterpass": version("afterpass"),
            "sentinel2": f"{sentinel.COLLECTION} via {sentinel.STAC_URL}",
            "firms": sorted({s for r in replays for s in r.detections["source"].unique()}),
            "worldcover": "ESA WorldCover 10 m 2021 v200",
            "boundaries": "geoBoundaries gbOpen IND ADM2",
            "overture": overture_release,
            "thresholds": json.loads(burns.THRESHOLDS_PATH.read_text()),
        },
        "demo": False,
    }


def latest_with(entry: dict, meta: dict) -> dict:
    """`latest.json` after publishing one season: every published season, newest on top.

    The top-level `season`, `run_id`, `data_through` and `districts` describe the newest
    season; `seasons` holds the same for each one, keyed by year.
    """
    path = PUBLIC_DIR / "latest.json"
    earlier = json.loads(path.read_text()) if path.exists() else {}
    seasons = dict(earlier.get("seasons", {}))
    if not seasons and "season" in earlier:
        # A file written before seasons were listed: keep what it described.
        keys = ("season", "run_id", "data_through", "districts", "generated_at")
        seasons[str(earlier["season"])] = {key: earlier[key] for key in keys} | {
            "mode": "live" if SEASONS[earlier["season"]][1] is None else "replay"
        }
    seasons[str(entry["season"])] = entry
    newest = seasons[max(seasons, key=int)]
    top = {key: newest[key] for key in ("season", "run_id", "data_through", "districts")}
    return {**top, "seasons": dict(sorted(seasons.items())), **meta}


IMAGERY_INDEX_KEYS = ("village_id", "name", "district", "pre_date", "post_date")


def write_imagery_index(meta: dict) -> Path:
    """List the villages that have before/after crops, so the app need not probe for them."""
    folder = PUBLIC_DIR / "imagery"
    records = [json.loads(path.read_text()) for path in sorted(folder.glob("*/meta.json"))]
    items = [{key: record[key] for key in IMAGERY_INDEX_KEYS} for record in records]
    return _write(folder / "index.json", {**meta, "items": items})


def publish_local(replays: list[Replay], season: int, overture_release: str) -> list[Path]:
    """Write every Phase 2 public file for the season. Returns the paths written."""
    meta = metadata(replays, overture_release)
    generated_at = datetime.fromisoformat(meta["generated_at"])
    season_dir = PUBLIC_DIR / "seasons" / str(season)
    written: list[Path] = []

    tables = {r.district.name: aggregate.with_areas(r.scars) for r in replays}
    everything = pd.concat(tables.values(), ignore_index=True)
    all_firms = pd.concat([r.detections for r in replays], ignore_index=True)
    states = places.load_districts().set_index("district")["state"]

    district_rows = []
    for replay in replays:
        table = tables[replay.district.name]
        district_rows.append(
            {
                "district": replay.district.name,
                "state": states[replay.district.name],
                "cropland_ha": replay.info["cropland_ha"],
                **aggregate.totals(table),
                "firms": aggregate.firms_counts(replay.detections),
                "by_day": aggregate.series(table, "first_detected"),
                "by_week": aggregate.series(table, "week"),
                "sentinel2": replay.info["sentinel2"],
                "missing_dates": replay.info["missing_dates"],
            }
        )

    data_through = max(row["date"] for r in replays for row in r.info["sentinel2"])
    entry = {
        "season": season,
        # A season with no last day is still running.
        "mode": "live" if SEASONS[season][1] is None else "replay",
        "run_id": f"{season}-{generated_at:%Y%m%dT%H%M%SZ}",
        "data_through": data_through,
        "districts": [r.district.name for r in replays],
        "generated_at": meta["generated_at"],
    }
    written.append(_write(PUBLIC_DIR / "latest.json", latest_with(entry, meta), pretty=True))
    written.append(
        _write(
            season_dir / "summary.json",
            {
                "season": season,
                "window": replays[0].info["window"],
                "totals": aggregate.totals(everything),
                "firms": aggregate.firms_counts(all_firms),
                "districts": district_rows,
                "limitations": LIMITATIONS,
                **meta,
            },
            pretty=True,
        )
    )

    outlines = gpd.GeoDataFrame(
        [
            {k: v for k, v in row.items() if k not in ("by_day", "by_week", "sentinel2", "firms")}
            | {"firms_count": row["firms"]["firms_count"]}
            for row in district_rows
        ],
        geometry=[r.district.geometry.simplify(DISTRICT_SIMPLIFY_DEG) for r in replays],
        crs="EPSG:4326",
    )
    outlines = outlines.set_geometry(outlines.geometry.set_precision(10**-COORDINATE_DECIMALS))
    written.append(
        _write(season_dir / "districts.geojson", json.loads(outlines.to_json(drop_id=True)) | meta)
    )

    # Rows keep their district so the app can filter by it. A cell on a district border
    # appears once per district; the app adds those rows together.
    cells = pd.concat(
        [
            aggregate.burns_by_h3_week(
                r.scars, aggregate.h3_cells(r.district.geometry, r.scars.crs)
            ).assign(district=r.district.name)
            for r in replays
        ],
        ignore_index=True,
    )
    cells = cells.sort_values(["district", "h3", "week"], ignore_index=True)
    cells[aggregate.AREA_COLUMNS] = cells[aggregate.AREA_COLUMNS].round(2)
    written.append(
        _write(season_dir / "burns_h3_r8.json", {**meta, "items": cells.to_dict("records")})
    )
    written.append(
        _write(
            season_dir / "firms_points.json",
            {**meta, "items": [item for r in replays for item in _firms_items(r)]},
        )
    )
    written.append(
        _write(season_dir / "villages.json", {**meta, "items": aggregate.villages(everything)})
    )
    # One file per district and week: a whole season in one file is too large for a browser.
    scars_dir = season_dir / "scars"
    if scars_dir.exists():
        shutil.rmtree(scars_dir)
    for replay in replays:
        for week, collection in _scars_by_week(replay).items():
            written.append(
                _write(scars_dir / replay.district.slug / f"{week}.geojson", collection | meta)
            )

    written.append(write_imagery_index(meta))

    written.extend(publish_validation(season, meta))
    return written


def publish_validation(season: int, meta: dict) -> list[Path]:
    """Copy `validation/{season}.json` (calibration, QA, PM2.5) to the public folder."""
    report = VALIDATION_DIR / f"{season}.json"
    if not report.exists():
        return []
    payload = json.loads(report.read_text()) | meta
    return [_write(PUBLIC_DIR / "validation" / f"{season}.json", payload, pretty=True)]


# --- Smoke (brief §8.5, §9.2) --------------------------------------------------------------

SMOKE_DIR = PUBLIC_DIR / "smoke"


def smoke_metadata(model: dict, overture_release: str, sources: str) -> dict:
    """The provenance block of every smoke file. `model` is smoke.params_record output."""
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_versions": {
            "afterpass": version("afterpass"),
            "winds": model["winds"],
            "winds_attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "burn_sources": sources,
            "overture": overture_release,
            "smoke_model": model,
        },
        "demo": False,
    }


def write_smoke_trips(run_id: str, start: float, trips: list[dict], meta: dict) -> Path:
    """smoke/{run_id}/trips.json: [{path, ts, w}] as `items`."""
    model = meta["source_versions"]["smoke_model"]
    return _write(
        SMOKE_DIR / run_id / "trips.json",
        {
            **meta,
            "run_id": run_id,
            "start": int(start),
            "hours": model["run_hours"],
            "tau_h": model["tau_h"],
            "items": trips,
        },
    )


def write_smoke_run(
    run_id: str,
    kind: str,
    hours: list[int],
    cells: list[str],
    sai: list[list[int]],
    localities: list[dict],
    normaliser: dict,
    meta: dict,
) -> list[Path]:
    """smoke/{run_id}/delhi_sai_h3r7.json and localities.json.

    `sai` is hours x cells of the normalised index (0-100).
    """
    by_cell = {cell: [row[i] for row in sai] for i, cell in enumerate(cells)}
    common = {**meta, "run_id": run_id, "kind": kind, "hours": hours, "normaliser": normaliser}
    return [
        _write(SMOKE_DIR / run_id / "delhi_sai_h3r7.json", {**common, "cells": by_cell}),
        _write(SMOKE_DIR / run_id / "localities.json", {**common, "items": localities}),
    ]


def clear_smoke_runs(keep: set[str], pattern: str) -> None:
    """Remove run folders matching `pattern` that are not in `keep` (e.g. an older replay)."""
    if not SMOKE_DIR.exists():
        return
    for folder in SMOKE_DIR.glob(pattern):
        if folder.is_dir() and folder.name not in keep:
            shutil.rmtree(folder)


def write_smoke_index(runs: list[dict], meta: dict) -> Path:
    """smoke/index.json: every published run, newest last. Runs of other kinds are kept."""
    path = SMOKE_DIR / "index.json"
    previous = json.loads(path.read_text())["runs"] if path.exists() else []
    replaced = {run["run_id"] for run in runs}
    kept = [
        run
        for run in previous
        if run["run_id"] not in replaced and (SMOKE_DIR / run["run_id"]).is_dir()
    ]
    merged = sorted(kept + runs, key=lambda run: run["start"])
    return _write(path, {**meta, "runs": merged}, pretty=True)
