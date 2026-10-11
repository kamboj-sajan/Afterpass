"""Run the smoke model for a replay season or a live forecast, and publish it (brief §8)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from afterpass import firms, pipeline, places, smoke, winds
from afterpass import publish as publisher
from afterpass.cache import cache_path
from afterpass.config import REGION_BBOX, season_window


@dataclass(frozen=True)
class Outcome:
    runs: list[dict]
    particles: int
    ha_each: float
    normaliser: dict
    wind_source: str


def _localities(
    points: gpd.GeoDataFrame, receptors: smoke.Receptors, sai: np.ndarray
) -> list[dict]:
    """One record per Delhi locality with its cell's hourly SAI (`sai`: hours x cells)."""
    records = []
    for row in points.itertuples():
        cell = h3.latlng_to_cell(row.geometry.y, row.geometry.x, smoke.H3_RESOLUTION)
        index = receptors.position.get(cell)
        if index is None:
            continue
        record = {
            "id": row.locality_id,
            "name": row.name,
            "district": row.district,
            "lon": round(row.geometry.x, 5),
            "lat": round(row.geometry.y, 5),
            "h3": cell,
            "sai": sai[:, index].tolist(),
        }
        if row.name_hi:
            record["name_hi"] = row.name_hi
        records.append(record)
    return records


def _summary_row(run_id: str, kind: str, start: float, sai: np.ndarray, trips: dict) -> dict:
    """The index entry for one run. `sai` is its hours x cells of the normalised index."""
    delhi_mean = sai.mean(axis=1)
    peak = int(np.argmax(delhi_mean))
    worst = int(sai.max()) if sai.size else 0
    return {
        "run_id": run_id,
        "kind": kind,
        "start": int(start),
        "start_ist": datetime.fromtimestamp(start, smoke.IST_TZ).isoformat(timespec="minutes"),
        "hours": int(sai.shape[0]),
        "peak_sai": worst,
        "peak_level": smoke.level(worst),
        "delhi_mean_peak": round(float(delhi_mean[peak]), 1),
        "delhi_mean_peak_hour": int(start + peak * smoke.HOUR_S),
        "trips": trips.get("count", 0),
        "trips_mb": trips.get("mb", 0.0),
    }


def _simulate_and_publish(
    *,
    sources: pd.DataFrame,
    runs: dict[float, str],
    kind: str,
    sim_start: float,
    wind: winds.WindField,
    params: smoke.SmokeParams,
    meta: dict,
    p95: float | None,
    log: Callable[[str], None],
) -> tuple[Outcome, smoke.SaiSeries]:
    """Shared by replay and live: release, simulate, normalise, write every run's files.

    `p95` fixes the normaliser (live runs use the replay season's); None computes it here.
    """
    rng = np.random.default_rng(params.seed)
    particles = smoke.release(sources, params, rng)
    log(f"smoke: {len(particles):,} particles, {particles.ha_each:.3f} ha each")
    receptors = smoke.delhi_receptors(places.delhi_geometry())
    points, _ = places.load_delhi_localities()
    span = params.run_hours * smoke.HOUR_S
    sim_end = max(runs) + span
    trips_info: dict[str, dict] = {}

    def on_run(run_start: float, trips: list[dict]) -> None:
        run_id = runs[run_start]
        path = publisher.write_smoke_trips(run_id, run_start, trips, meta)
        trips_info[run_id] = {"count": len(trips), "mb": round(path.stat().st_size / 1e6, 2)}

    series = smoke.simulate(
        particles, wind, receptors, sim_start, sim_end, params, sorted(runs), on_run, log
    )
    if p95 is None:
        p95 = smoke.normaliser(series.raw)
    normaliser = {
        "p95_raw": p95,
        "basis": "95th percentile of non-zero Delhi cell-hours in the 2025 replay season",
    }
    index = smoke.normalise(series.raw, p95)
    rows = []
    for run_start, run_id in sorted(runs.items()):
        first = int((run_start - sim_start) // smoke.HOUR_S)
        sai = index[first : first + params.run_hours]
        hours = [int(run_start + h * smoke.HOUR_S) for h in range(params.run_hours)]
        publisher.write_smoke_run(
            run_id,
            kind,
            hours,
            receptors.cells,
            sai.tolist(),
            _localities(points, receptors, sai),
            normaliser,
            meta,
        )
        rows.append(_summary_row(run_id, kind, run_start, sai, trips_info.get(run_id, {})))
    publisher.write_smoke_index(rows, meta)
    outcome = Outcome(rows, len(particles), particles.ha_each, normaliser, wind.source)
    return outcome, series


def _wind_for(sim_start: float, sim_end: float, source: str) -> winds.WindField:
    """Winds covering [sim_start, sim_end] plus an hour either side, by UTC date."""
    first = datetime.fromtimestamp(sim_start - smoke.HOUR_S, UTC).date()
    last = datetime.fromtimestamp(sim_end + smoke.HOUR_S, UTC).date()
    return winds.load(first, last, source)


def replay(
    season: int,
    districts: list[str],
    wind_source: str,
    params: smoke.SmokeParams,
    log: Callable[[str], None] = lambda _: None,
) -> Outcome:
    """One continuous run over the season, published as a 48-hour run per IST day."""
    replays = [pipeline.load_replay(name, season) for name in districts]
    sources = pd.concat([smoke.sources_replay(r.scars) for r in replays], ignore_index=True)
    sources = sources.groupby(["cell", "day"], as_index=False, sort=True)["ha"].sum()
    first, last = season_window(season)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    runs = {smoke.ist_timestamp(day): day.isoformat() for day in days}
    sim_start = smoke.ist_timestamp(min(min(sources["day"]), first))
    wind = _wind_for(sim_start, max(runs) + params.run_hours * smoke.HOUR_S, wind_source)
    _, release = places.load_delhi_localities()
    meta = publisher.smoke_metadata(
        smoke.params_record(params, wind.source),
        release,
        f"AfterPass {season} replay burn scars: {', '.join(districts)}",
    )
    publisher.clear_smoke_runs(set(runs.values()), f"{season}-??-??")
    outcome, series = _simulate_and_publish(
        sources=sources,
        runs=runs,
        kind="replay",
        sim_start=sim_start,
        wind=wind,
        params=params,
        meta=meta,
        p95=None,
        log=log,
    )
    # Kept for the PM2.5 comparison and as the normaliser for live runs.
    np.savez_compressed(
        cache_path("smoke", f"sai_{season}.npz"),
        hours=series.hours,
        raw=series.raw,
        p95=outcome.normaliser["p95_raw"],
    )
    return outcome


def replay_normaliser(season: int = 2025) -> float:
    path = cache_path("smoke", f"sai_{season}.npz")
    if not path.exists():
        raise FileNotFoundError(f"No {season} smoke replay. Run `afterpass smoke` first.")
    with np.load(path) as cached:
        return float(cached["p95"])


def burned_ha_per_frp(season: int, districts: list[str]) -> float:
    """Season burned area over the FRP of the FIRMS detections in the same districts."""
    replays = [pipeline.load_replay(name, season) for name in districts]
    burned = sum(float(r.scars["area_ha"].sum()) for r in replays)
    frp = sum(float(r.detections["frp"].fillna(0).sum()) for r in replays)
    return burned / frp if frp else 0.0


def live(
    season: int,
    districts: list[str],
    params: smoke.SmokeParams,
    now: datetime | None = None,
    log: Callable[[str], None] = lambda _: None,
) -> Outcome:
    """A 48-hour forecast from now (brief §8.1).

    The two days before today burn as detected, so smoke already in the air is included.
    Today and the forecast days burn at the mean daily rate of the last 3 days (persistence),
    and today also adds FIRMS detections converted from FRP to hectares with the 2025
    replay's ratio. Normalised against the 2025 replay season so live and replay agree.
    """
    now = now or datetime.now(UTC)
    today = now.astimezone(smoke.IST_TZ).date()
    replays = [pipeline.load_replay(name, season) for name in districts]
    detected = pd.concat([smoke.sources_replay(r.scars) for r in replays], ignore_index=True)
    recent = detected[detected["day"].between(today - timedelta(days=3), today - timedelta(1))]
    forecast_days = [today + timedelta(days=i) for i in range(3)]
    utc_today = now.astimezone(UTC).date()
    region = firms.fetch(utc_today, utc_today)
    w, s, e, n = REGION_BBOX
    region = region[region["longitude"].between(w, e) & region["latitude"].between(s, n)]
    in_districts = firms.clip(
        region,
        places.load_districts().set_index("district").loc[districts].union_all(),
        "EPSG:4326",
    )
    firms_today = in_districts[in_districts["acq_dt_ist"].dt.date == today]
    future = smoke.sources_live(
        recent, forecast_days, firms_today, today, burned_ha_per_frp(2025, districts)
    )
    past = detected[detected["day"].between(today - timedelta(days=2), today - timedelta(1))]
    sources = pd.concat([past, future], ignore_index=True)
    sources = sources.groupby(["cell", "day"], as_index=False, sort=True)["ha"].sum()

    sim_start = smoke.ist_timestamp(today - timedelta(days=2))
    run_start = sim_start + (now.timestamp() - sim_start) // smoke.HOUR_S * smoke.HOUR_S
    run_id = datetime.fromtimestamp(run_start, smoke.IST_TZ).strftime("%Y-%m-%dT%H%M")
    wind = _wind_for(sim_start, run_start + params.run_hours * smoke.HOUR_S, "forecast")
    _, release = places.load_delhi_localities()
    meta = publisher.smoke_metadata(
        smoke.params_record(params, wind.source),
        release,
        f"AfterPass {season} burn scars for the last 2 days, then persistence of the last 3 "
        "days plus today's FIRMS FRP: forecast assumes burning continues at that rate",
    )
    outcome, _ = _simulate_and_publish(
        sources=sources,
        runs={run_start: run_id},
        kind="live",
        sim_start=sim_start,
        wind=wind,
        params=params,
        meta=meta,
        p95=replay_normaliser(),
        log=log,
    )
    return outcome


def daily_delhi_sai(season: int) -> pd.Series:
    """Daily (IST) mean over Delhi cells of the normalised SAI, for the PM2.5 comparison."""
    path = cache_path("smoke", f"sai_{season}.npz")
    with np.load(path) as cached:
        index = smoke.normalise(cached["raw"], float(cached["p95"]))
        hours = cached["hours"]
    days = [datetime.fromtimestamp(h, smoke.IST_TZ).date() for h in hours]
    series = pd.Series(index.mean(axis=1), index=days)
    first, last = season_window(season)
    series = series.groupby(level=0).mean()
    return series[(series.index >= first) & (series.index <= last)]
