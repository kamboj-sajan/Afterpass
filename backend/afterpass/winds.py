"""Winds and mixing height from Open-Meteo on a coarse regional grid (brief §5.4).

Live forecasts and the replay use the same request shape. The replay can read either the
Historical Forecast API (the same models as the live forecast) or, if a model there lacks 100 m
wind or boundary-layer height, the ERA5 Archive API. Directions are converted to u/v before any
interpolation, so a wind backing through north is never averaged into a southerly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import numpy as np

from afterpass.cache import cache_path

# 0.25 degree grid over 27.5-32.75 N, 73.5-78.0 E: 22 x 19 = 418 points.
GRID_STEP = 0.25
GRID_LATS = np.round(np.arange(27.5, 32.75 + 1e-9, GRID_STEP), 2)
GRID_LONS = np.round(np.arange(73.5, 78.0 + 1e-9, GRID_STEP), 2)
VARIABLES = ("wind_speed_100m", "wind_direction_100m", "boundary_layer_height")
CHUNK = 100  # coordinates per request
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
# The free tier allows 600 weighted calls a minute; a 100-point, multi-week request uses
# several hundred, so a rate-limited request waits out the minute and tries again.
RATE_LIMIT_WAIT_S = 65
RATE_LIMIT_TRIES = 6


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    models: str | None = None


SOURCES = {
    "forecast": Source("forecast", "https://api.open-meteo.com/v1/forecast"),
    "historical_forecast": Source(
        "historical_forecast", "https://historical-forecast-api.open-meteo.com/v1/forecast"
    ),
    "era5": Source("era5", "https://archive-api.open-meteo.com/v1/archive", "era5"),
}


class WindError(RuntimeError):
    pass


def wind_to_uv(speed: np.ndarray, direction_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Eastward and northward components (m/s) of a wind blowing FROM `direction_deg`."""
    theta = np.deg2rad(direction_deg)
    return -speed * np.sin(theta), -speed * np.cos(theta)


def grid_points() -> list[tuple[float, float]]:
    """(lat, lon) for every grid point, row by row from the south-west corner."""
    return [(float(lat), float(lon)) for lat in GRID_LATS for lon in GRID_LONS]


def _request(source: Source, points: list[tuple[float, float]], start: date, end: date) -> list:
    params: dict[str, str] = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in points),
        "hourly": ",".join(VARIABLES),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "timeformat": "unixtime",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if source.models:
        params["models"] = source.models
    for _ in range(RATE_LIMIT_TRIES):
        resp = httpx.get(source.url, params=params, timeout=180)
        if resp.status_code != 429:
            break
        time.sleep(RATE_LIMIT_WAIT_S)
    if resp.status_code != 200:
        # Open-Meteo explains a bad request (e.g. an unknown variable) in a JSON `reason`.
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            reason = ""
        raise WindError(f"Open-Meteo {source.name} returned HTTP {resp.status_code} {reason}")
    body = resp.json()
    # One location comes back as an object, several as a list in request order.
    return body if isinstance(body, list) else [body]


def _fetch_chunk(source: Source, index: int, start: date, end: date) -> dict[str, np.ndarray]:
    dest = cache_path("winds", f"{source.name}_{start}_{end}_{index:02d}.npz")
    if dest.exists():
        with np.load(dest) as cached:
            return dict(cached)
    points = grid_points()[index * CHUNK : (index + 1) * CHUNK]
    locations = _request(source, points, start, end)
    if len(locations) != len(points):
        raise WindError(f"Asked for {len(points)} locations, got {len(locations)}")
    times = np.asarray(locations[0]["hourly"]["time"], dtype=np.int64)
    arrays = {"time": times}
    for name in VARIABLES:
        values = [loc["hourly"].get(name) for loc in locations]
        if any(v is None for v in values):
            raise WindError(f"Open-Meteo {source.name} has no {name}. Try --winds era5.")
        arrays[name] = np.asarray(values, dtype=np.float64)  # None -> nan
    tmp = dest.with_name(dest.stem + ".part.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.replace(dest)
    return arrays


def _fill_gaps(values: np.ndarray, name: str) -> np.ndarray:
    """Interpolate missing hours along time for each point (values: points x hours)."""
    out = values.copy()
    hours = np.arange(values.shape[1])
    for row in out:
        missing = np.isnan(row)
        if missing.all():
            raise WindError(f"{name} is missing for every hour at a grid point.")
        if missing.any():
            row[missing] = np.interp(hours[missing], hours[~missing], row[~missing])
    return out


@dataclass(frozen=True)
class WindField:
    """Hourly u, v (m/s) and boundary-layer height (m) on GRID_LATS x GRID_LONS.

    Arrays are shaped (hours, lats, lons); `times` are unix seconds (UTC).
    """

    times: np.ndarray
    lats: np.ndarray
    lons: np.ndarray
    u: np.ndarray
    v: np.ndarray
    pbl: np.ndarray
    source: str

    def contains(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return (
            (lon >= self.lons[0])
            & (lon <= self.lons[-1])
            & (lat >= self.lats[0])
            & (lat <= self.lats[-1])
        )

    def at(self, field: np.ndarray, t: float) -> np.ndarray:
        """One (lats, lons) grid of `field` at time t, linear between the hours around it."""
        if not self.times[0] <= t <= self.times[-1]:
            raise WindError(f"No winds for {datetime.fromtimestamp(t, UTC).isoformat()}")
        i = min(int(np.searchsorted(self.times, t, side="right")) - 1, len(self.times) - 2)
        f = (t - self.times[i]) / (self.times[i + 1] - self.times[i])
        return field[i] * (1 - f) + field[i + 1] * f

    def _corners(self, lon: np.ndarray, lat: np.ndarray):
        """Grid indices and bilinear weights; points outside the grid are clamped to its edge."""
        fx = np.clip((lon - self.lons[0]) / GRID_STEP, 0, len(self.lons) - 1 - 1e-9)
        fy = np.clip((lat - self.lats[0]) / GRID_STEP, 0, len(self.lats) - 1 - 1e-9)
        x0, y0 = fx.astype(np.int64), fy.astype(np.int64)
        dx, dy = fx - x0, fy - y0
        return x0, y0, dx, dy

    @staticmethod
    def _bilinear(grid: np.ndarray, corners) -> np.ndarray:
        x0, y0, dx, dy = corners
        top = grid[y0 + 1, x0] * (1 - dx) + grid[y0 + 1, x0 + 1] * dx
        bottom = grid[y0, x0] * (1 - dx) + grid[y0, x0 + 1] * dx
        return bottom + (top - bottom) * dy

    def velocity(self, lon: np.ndarray, lat: np.ndarray, t: float):
        """(u, v) in m/s: bilinear in space, linear in time."""
        corners = self._corners(lon, lat)
        return (
            self._bilinear(self.at(self.u, t), corners),
            self._bilinear(self.at(self.v, t), corners),
        )

    def mixing_height(self, lon: np.ndarray, lat: np.ndarray, t: float) -> np.ndarray:
        return self._bilinear(self.at(self.pbl, t), self._corners(lon, lat))


def load(start: date, end: date, source_name: str) -> WindField:
    """The wind field for UTC dates [start, end], fetched in chunks and cached."""
    source = SOURCES[source_name]
    n_chunks = -(-len(grid_points()) // CHUNK)
    chunks = [_fetch_chunk(source, i, start, end) for i in range(n_chunks)]
    times = chunks[0]["time"]
    if any(not np.array_equal(c["time"], times) for c in chunks):
        raise WindError("Open-Meteo chunks returned different hours.")
    shape = (len(times), len(GRID_LATS), len(GRID_LONS))
    stacked = {
        name: _fill_gaps(np.concatenate([c[name] for c in chunks]), name).T.reshape(shape)
        for name in VARIABLES
    }
    u, v = wind_to_uv(stacked["wind_speed_100m"], stacked["wind_direction_100m"])
    return WindField(
        times=times,
        lats=GRID_LATS,
        lons=GRID_LONS,
        u=u,
        v=v,
        pbl=stacked["boundary_layer_height"],
        source=f"Open-Meteo {source.name}" + (f" ({source.models})" if source.models else ""),
    )


def probe(source_name: str, day: date) -> dict[str, float]:
    """Share of non-missing hours per variable at two grid points, for the API check."""
    source = SOURCES[source_name]
    locations = _request(source, [(30.25, 75.75), (28.5, 77.0)], day, day)
    out = {}
    for name in VARIABLES:
        values = [x for loc in locations for x in (loc["hourly"].get(name) or [None])]
        out[name] = sum(x is not None for x in values) / len(values)
    return out
