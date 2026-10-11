"""Smoke transport: a relative outlook of where burning's smoke goes (brief §8).

This is not a chemistry model. A particle's weight is hectares of burned field, decayed with
age, and the Smoke Arrival Index (SAI) is a relative 0-100 number. Nothing here is, or may be
shown as, a concentration.

Assumptions, all stated in the published files:
- Fires are lit 15:00-19:00 IST (iFOREST: over 90% of large Punjab farm fires in 2024-2025
  started after 3 PM), uniformly within that window.
- Sentinel-2 passes at about 11:00 IST, so a scar first seen on day t burned on an afternoon
  from its window start p (the last clear view without it) to t - 1. Its area is spread
  evenly over those days (brief §8.1).
- Smoke rides the 100 m wind, spreads by a random walk with diffusivity K and fades as
  exp(-age / tau). SAI divides by the mixing height: the same smoke under a shallow night-time
  boundary layer counts for more.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry

from afterpass.config import IST
from afterpass.winds import WindField

EARTH_RADIUS_M = 6_371_000.0
DEG_PER_M = 180.0 / (math.pi * EARTH_RADIUS_M)
H3_RESOLUTION = 7
HOUR_S = 3600
IST_TZ = ZoneInfo(IST)
# Plain-language levels for the normalised index: (name, lowest value).
LEVELS = (("low", 0), ("moderate", 25), ("high", 50), ("very_high", 75))
DELHI_PADDING_DEG = 0.03


@dataclass(frozen=True)
class SmokeParams:
    """Tunable model settings (brief §8.3). Saved into every published smoke file."""

    dt_s: int = 600
    diffusivity_m2s: float = 1000.0
    tau_h: float = 36.0
    burn_hours_ist: tuple[float, float] = (15.0, 19.0)
    # The busiest day releases this many particles; others release in proportion.
    max_particles_per_day: int = 60_000
    # A particle is dropped once its weight falls below this share of the start (~7 days).
    min_weight: float = 0.01
    pbl_floor_m: float = 100.0
    run_hours: int = 48
    # The brief allows up to 20k trails; 15k at a vertex every 2 h keeps a run near 4 MB.
    trips_cap: int = 15_000
    trail_vertex_h: int = 2
    # Trails are only drawn for a particle's first two days; it still counts towards SAI after.
    trip_max_age_h: float = 48.0
    # A run's trails start this long before the run, so smoke already over Delhi at the first
    # hour arrives with its trail. Matches the trail length the app draws.
    trail_lead_h: int = 6
    seed: int = 2025

    @property
    def sigma_m(self) -> float:
        """Random-walk step: sqrt(2 K dt)."""
        return math.sqrt(2 * self.diffusivity_m2s * self.dt_s)

    @property
    def max_age_s(self) -> float:
        return -self.tau_h * HOUR_S * math.log(self.min_weight)


def ist_timestamp(day: date, hour: float = 0.0) -> float:
    """Unix seconds for an IST calendar day and fractional hour."""
    return datetime.combine(day, time(0), IST_TZ).timestamp() + hour * HOUR_S


# --- Sources -------------------------------------------------------------------------------


def burn_days(window_start: str, first_detected: str) -> list[date]:
    """IST days on whose afternoon a scar may have burned: p to t - 1 (see module notes)."""
    p, t = date.fromisoformat(window_start), date.fromisoformat(first_detected)
    last = t - timedelta(days=1)
    if last < p:  # no gap between the two views; the afternoon before is the only option
        return [last]
    return [p + timedelta(days=i) for i in range((last - p).days + 1)]


def sources_replay(scars: gpd.GeoDataFrame) -> pd.DataFrame:
    """Burned hectares per H3 resolution-7 cell and IST burn day: columns cell, day, ha."""
    if len(scars) == 0:
        return pd.DataFrame({"cell": [], "day": [], "ha": []})
    centroids = scars.geometry.centroid.to_crs("EPSG:4326")
    rows = []
    for point, start, seen, area in zip(
        centroids,
        scars["window_start"],
        scars["first_detected"],
        scars["area_ha"],
        strict=True,
    ):
        cell = h3.latlng_to_cell(point.y, point.x, H3_RESOLUTION)
        days = burn_days(start, seen)
        rows.extend((cell, day, area / len(days)) for day in days)
    table = pd.DataFrame(rows, columns=["cell", "day", "ha"])
    return table.groupby(["cell", "day"], as_index=False, sort=True)["ha"].sum()


def sources_live(
    recent: pd.DataFrame,
    days: list[date],
    firms_today: pd.DataFrame,
    today: date,
    ha_per_frp: float,
) -> pd.DataFrame:
    """Forecast sources by persistence (brief §8.1).

    Each forecast day burns, per cell, the mean daily area of `recent` (the last 3 days of
    sources_replay output), and today also gets FIRMS fire radiative power converted to
    hectares with the replay's ratio of burned area to FRP.
    """
    rate = recent.groupby("cell")["ha"].sum() / 3.0
    rows = [(cell, day, ha) for day in days for cell, ha in rate.items() if ha > 0]
    if len(firms_today) and today in days:
        cells = [
            h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            for lat, lon in zip(firms_today["latitude"], firms_today["longitude"], strict=True)
        ]
        frp = firms_today["frp"].fillna(0).to_numpy()
        rows.extend(
            (cell, today, power * ha_per_frp) for cell, power in zip(cells, frp, strict=True)
        )
    table = pd.DataFrame(rows, columns=["cell", "day", "ha"])
    return table.groupby(["cell", "day"], as_index=False, sort=True)["ha"].sum()


@dataclass(frozen=True)
class Particles:
    """Particles sorted by release time. Every particle carries `ha_each` hectares."""

    lon: np.ndarray
    lat: np.ndarray
    released: np.ndarray  # unix seconds
    ha_each: float

    def __len__(self) -> int:
        return len(self.released)


def release(sources: pd.DataFrame, params: SmokeParams, rng: np.random.Generator) -> Particles:
    """Particles in proportion to burned area, at random times in the IST burn window.

    Counts are rounded stochastically (floor, plus one with probability of the remainder), so
    the expected hectares released equal the sources exactly.
    """
    totals = sources.groupby("day")["ha"].sum()
    if len(totals) == 0 or totals.max() <= 0:
        empty = np.empty(0)
        return Particles(empty, empty, empty, 0.0)
    ha_each = float(totals.max()) / params.max_particles_per_day
    expected = sources["ha"].to_numpy() / ha_each
    counts = np.floor(expected).astype(np.int64)
    counts += rng.random(len(counts)) < expected - counts
    centres = np.array([h3.cell_to_latlng(c) for c in sources["cell"]]).reshape(-1, 2)
    starts = np.array([ist_timestamp(d, params.burn_hours_ist[0]) for d in sources["day"]])
    lat0 = np.repeat(centres[:, 0], counts)
    lon0 = np.repeat(centres[:, 1], counts)
    start = np.repeat(starts, counts)
    n = len(start)
    # Spread over the cell: uniform in a disc of the cell's edge length.
    edge = h3.average_hexagon_edge_length(H3_RESOLUTION, unit="m")
    radius = edge * np.sqrt(rng.random(n))
    angle = rng.random(n) * 2 * np.pi
    lat = lat0 + radius * np.sin(angle) * DEG_PER_M
    lon = lon0 + radius * np.cos(angle) * DEG_PER_M / np.cos(np.deg2rad(lat0))
    window_s = (params.burn_hours_ist[1] - params.burn_hours_ist[0]) * HOUR_S
    released = start + rng.random(n) * window_s
    order = np.argsort(released, kind="stable")
    return Particles(lon[order], lat[order], released[order], ha_each)


# --- Advection -----------------------------------------------------------------------------


def _displace(lon, lat, u, v, dt):
    lat_new = lat + v * dt * DEG_PER_M
    lon_new = lon + u * dt * DEG_PER_M / np.cos(np.deg2rad(lat))
    return lon_new, lat_new


def step(
    lon: np.ndarray,
    lat: np.ndarray,
    t: float,
    wind: WindField,
    dt: float,
    sigma_m: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance particles from t to t + dt: RK2 (Heun) on the wind, then a random-walk jitter."""
    u1, v1 = wind.velocity(lon, lat, t)
    lon_p, lat_p = _displace(lon, lat, u1, v1, dt)
    u2, v2 = wind.velocity(lon_p, lat_p, t + dt)
    lon_new, lat_new = _displace(lon, lat, (u1 + u2) / 2, (v1 + v2) / 2, dt)
    if sigma_m > 0:
        jitter = rng.normal(0.0, sigma_m, (2, len(lon)))
        lon_new, lat_new = _displace(lon_new, lat_new, jitter[0], jitter[1], 1.0)
    return lon_new, lat_new


def decayed(ha_each: float, age_s: np.ndarray, tau_h: float) -> np.ndarray:
    return ha_each * np.exp(-age_s / (tau_h * HOUR_S))


# --- Receptors -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Receptors:
    """H3 resolution-7 cells over Delhi."""

    cells: list[str]
    lon: np.ndarray  # cell centres
    lat: np.ndarray
    bounds: tuple[float, float, float, float]  # west, south, east, north of all cells
    position: dict[str, int]  # cell -> index

    def index(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Receptor index of each point, or -1. Only points in the bounding box hit H3."""
        west, south, east, north = self.bounds
        out = np.full(len(lon), -1, np.int64)
        near = np.flatnonzero((lon >= west) & (lon <= east) & (lat >= south) & (lat <= north))
        for k in near:
            out[k] = self.position.get(h3.latlng_to_cell(lat[k], lon[k], H3_RESOLUTION), -1)
        return out


def delhi_receptors(geometry: BaseGeometry) -> Receptors:
    """Resolution-7 cells that overlap `geometry` (NCT Delhi, EPSG:4326)."""
    padded = geometry.buffer(DELHI_PADDING_DEG)
    candidates = sorted(h3.geo_to_cells(mapping(padded), H3_RESOLUTION))
    shapes = {c: Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in candidates}
    cells = [c for c in candidates if shapes[c].intersects(geometry)]
    centres = np.array([h3.cell_to_latlng(c) for c in cells])
    bounds = gpd.GeoSeries([shapes[c] for c in cells]).total_bounds
    west, south, east, north = (float(b) for b in bounds)
    position = {cell: i for i, cell in enumerate(cells)}
    return Receptors(cells, centres[:, 1], centres[:, 0], (west, south, east, north), position)


# --- Simulation ----------------------------------------------------------------------------


@dataclass
class _Track:
    """Positions of the particles drawn as trails, kept only as long as a run needs them."""

    times: list[np.ndarray] = field(default_factory=list)
    ids: list[np.ndarray] = field(default_factory=list)
    lons: list[np.ndarray] = field(default_factory=list)
    lats: list[np.ndarray] = field(default_factory=list)

    def add(self, t: float, ids: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> None:
        if len(ids):
            self.times.append(np.full(len(ids), int(t), np.int64))
            self.ids.append(ids.astype(np.int64))
            self.lons.append(lon.astype(np.float32))
            self.lats.append(lat.astype(np.float32))

    def window(self, start: float, end: float):
        if not self.times:
            return (np.empty(0, np.int64),) * 2 + (np.empty(0, np.float32),) * 2
        t, i = np.concatenate(self.times), np.concatenate(self.ids)
        keep = (t >= start) & (t <= end)
        return t[keep], i[keep], np.concatenate(self.lons)[keep], np.concatenate(self.lats)[keep]

    def drop_before(self, start: float) -> None:
        kept = [k for k, t in enumerate(self.times) if t[0] >= start]
        for name in ("times", "ids", "lons", "lats"):
            setattr(self, name, [getattr(self, name)[k] for k in kept])


def build_trips(
    times: np.ndarray,
    ids: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    cap: int,
    ha_each: float,
    released: np.ndarray,
    rng: np.random.Generator,
) -> list[dict]:
    """Trails as [{path, ts, w, age0}], at most `cap`, coordinates to 4 decimals (brief §8.5).

    `w` is the hectares of burned field each drawn trail stands for, so the subsample still
    says how much burning it represents. `age0` is the smoke's age in seconds at the first
    vertex (trails that started before the run window are already old), for colouring by age.
    """
    if len(ids) == 0:
        return []
    order = np.lexsort((times, ids))
    times, ids, lons, lats = times[order], ids[order], lons[order], lats[order]
    # The same particle can be recorded twice at one instant (released on the hour).
    fresh = np.ones(len(ids), bool)
    fresh[1:] = (ids[1:] != ids[:-1]) | (times[1:] != times[:-1])
    times, ids, lons, lats = times[fresh], ids[fresh], lons[fresh], lats[fresh]
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], len(ids)]
    long_enough = np.flatnonzero(ends - starts >= 2)
    chosen = long_enough
    if len(chosen) > cap:
        chosen = np.sort(rng.choice(long_enough, cap, replace=False))
    weight = ha_each * len(long_enough) / max(len(chosen), 1)
    trips = []
    for k in chosen:
        a, b = starts[k], ends[k]
        trips.append(
            {
                "path": np.round(np.column_stack([lons[a:b], lats[a:b]]).astype(float), 4).tolist(),
                "ts": times[a:b].tolist(),
                "w": round(weight, 3),
                "age0": int(times[a] - released[ids[a]]),
            }
        )
    return trips


@dataclass(frozen=True)
class SaiSeries:
    """Raw SAI per receptor per hour: the hour's mean of sum(weight) / max(PBL, floor)."""

    hours: np.ndarray  # unix seconds of each hour's start
    raw: np.ndarray  # (hours, receptors)


def trail_stride(particles: Particles, run_starts: list[float], params: SmokeParams) -> int:
    """Follow every k-th particle as a trail, so no run needs many more than trips_cap.

    Particles are in release order, so every k-th one samples all sources and days evenly.
    """
    if len(particles) == 0 or not run_starts:
        return 1
    released = particles.released
    age = params.trip_max_age_h * HOUR_S
    span = params.run_hours * HOUR_S
    lead = params.trail_lead_h * HOUR_S
    busiest = max(
        np.searchsorted(released, s + span, "right")
        - np.searchsorted(released, s - lead - age, "left")
        for s in run_starts
    )
    return max(1, int(busiest) // params.trips_cap)


def simulate(
    particles: Particles,
    wind: WindField,
    receptors: Receptors,
    start: float,
    end: float,
    params: SmokeParams,
    run_starts: list[float],
    on_run: Callable[[float, list[dict]], None],
    log: Callable[[str], None] = lambda _: None,
) -> SaiSeries:
    """Run every particle from `start` to `end` (unix seconds, a whole number of hours apart).

    Hours count from `start`, which is IST midnight for a replay: on the half hour in UTC.

    Calls `on_run(run_start, trips)` as soon as each run's window has been simulated, so trails
    never pile up in memory. Returns the hourly SAI at every receptor.
    """
    rng = np.random.default_rng(params.seed)
    dt = params.dt_s
    if (end - start) % HOUR_S or HOUR_S % dt:
        raise ValueError("end - start must be whole hours, and dt must divide an hour")
    n_hours = int((end - start) // HOUR_S)
    sums = np.zeros((n_hours, len(receptors.cells)))
    counts = np.zeros(n_hours)
    stride = trail_stride(particles, run_starts, params)
    tracked_all = np.arange(len(particles)) % stride == 0
    pending = sorted(run_starts)
    span = params.run_hours * HOUR_S
    lead = params.trail_lead_h * HOUR_S
    track = _Track()

    ids = np.empty(0, np.int64)
    lon = np.empty(0)
    lat = np.empty(0)
    tracked = np.empty(0, bool)
    next_id = 0
    t = float(start)
    steps = int((end - start) // dt)
    for k in range(steps + 1):
        # Release everything due by now, at its release point.
        due = int(np.searchsorted(particles.released, t, side="right"))
        if due > next_id:
            new = np.arange(next_id, due)
            ids = np.concatenate([ids, new])
            lon = np.concatenate([lon, particles.lon[new]])
            lat = np.concatenate([lat, particles.lat[new]])
            tracked = np.concatenate([tracked, tracked_all[new]])
            track.add(
                t,
                new[tracked_all[new]],
                particles.lon[new][tracked_all[new]],
                particles.lat[new][tracked_all[new]],
            )
            next_id = due
        if (t - start) % (params.trail_vertex_h * HOUR_S) == 0:
            track.add(t, ids[tracked], lon[tracked], lat[tracked])

        hour = int((t - start) // HOUR_S)
        if hour < n_hours and len(ids):
            where = receptors.index(lon, lat)
            near = where >= 0
            if near.any():
                age = t - particles.released[ids[near]]
                weight = decayed(particles.ha_each, age, params.tau_h)
                total = np.bincount(where[near], weights=weight, minlength=len(receptors.cells))
                pbl = wind.mixing_height(receptors.lon, receptors.lat, t)
                sums[hour] += total / np.maximum(pbl, params.pbl_floor_m)
        if hour < n_hours:
            counts[hour] += 1

        while pending and t >= pending[0] + span:
            run_start = pending.pop(0)
            trips = build_trips(
                *track.window(run_start - lead, run_start + span),
                params.trips_cap,
                particles.ha_each * stride,
                particles.released,
                rng,
            )
            on_run(run_start, trips)
            track.drop_before((pending[0] if pending else t) - lead)
        if k == steps:
            break

        if len(ids):
            lon, lat = step(lon, lat, t, wind, dt, params.sigma_m, rng)
            age = t + dt - particles.released[ids]
            gone = ~wind.contains(lon, lat) | (age > params.max_age_s)
            retire = tracked & (gone | (age > params.trip_max_age_h * HOUR_S))
            track.add(t + dt, ids[retire], lon[retire], lat[retire])
            tracked &= ~retire
            if gone.any():
                keep = ~gone
                ids, lon, lat, tracked = ids[keep], lon[keep], lat[keep], tracked[keep]
        t += dt
        if k % (24 * HOUR_S // dt) == 0:
            day = datetime.fromtimestamp(t, IST_TZ).date()
            log(f"smoke: {day}  {len(ids):,} particles in the air")
    return SaiSeries(start + np.arange(n_hours) * HOUR_S, sums / np.maximum(counts, 1)[:, None])


# --- Index ---------------------------------------------------------------------------------


def normaliser(raw: np.ndarray) -> float:
    """The season's 95th percentile of non-zero cell-hours: SAI 100 (brief §8.4)."""
    positive = raw[raw > 0]
    return float(np.percentile(positive, 95)) if positive.size else 0.0


def normalise(raw: np.ndarray, p95: float) -> np.ndarray:
    if p95 <= 0:
        return np.zeros(raw.shape, np.int64)
    return np.clip(np.round(raw / p95 * 100), 0, 100).astype(np.int64)


def level(sai: float) -> str:
    name = LEVELS[0][0]
    for candidate, lowest in LEVELS:
        if sai >= lowest:
            name = candidate
    return name


def params_record(params: SmokeParams, wind_source: str) -> dict:
    """What the published files say about how they were made."""
    return {
        **asdict(params),
        "sigma_m": round(params.sigma_m, 1),
        "winds": wind_source,
        "levels": {name: lowest for name, lowest in LEVELS},
        "emission_timing": "15:00-19:00 IST on each burn day (iFOREST timing finding)",
        "note": "Relative index from a simplified transport model; not PM2.5.",
    }
