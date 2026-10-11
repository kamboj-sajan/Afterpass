"""Observed Delhi PM2.5 from OpenAQ v3, compared with the Smoke Arrival Index (brief §8.6, §14.3).

Only reference monitors (CPCB and DPCC stations) inside Delhi are used. OpenAQ's daily values
are means of hourly values in local time (IST). The comparison is reported as it comes out:
PM2.5 has many sources, and the index models smoke from the replayed districts only.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from shapely.geometry import Point

from afterpass import places
from afterpass.cache import atomic_write_bytes, cache_path
from afterpass.config import season_window, settings

API = "https://api.openaq.org/v3"
SOURCE = "OpenAQ v3: CPCB and DPCC reference monitors inside Delhi"
PM25_PARAMETER_ID = 2
# The free tier allows 60 requests a minute; repeated overruns can get a key banned.
PAUSE_S = 1.2
RETRY_WAIT_S = 65.0
RETRIES = 3
# A station's day counts when at least this share of its hours were reported.
MIN_DAY_COVERAGE_PCT = 75.0
# A city mean needs at least this many stations reporting that day.
MIN_STATIONS = 5
CAVEATS = [
    "PM2.5 in Delhi comes from many sources (traffic, industry, dust, local burning, weather). "
    "Stubble smoke is one of them.",
    "The index models smoke from the replayed districts only, not all of Punjab and Haryana.",
    "Both series depend on the mixing height: a shallow layer raises the index by construction "
    "and also traps PM2.5 from every source, so part of the agreement is shared weather.",
    "The index is relative and has no units; a correlation says how the two move together, "
    "not how much PM2.5 the smoke adds.",
]

plt.switch_backend("Agg")


class OpenAQError(RuntimeError):
    pass


def _get(path: str, params: dict[str, str | int]) -> dict:
    key = settings().openaq_api_key
    if key is None or not key.get_secret_value():
        raise OpenAQError("OPENAQ_API_KEY is not set. Add it to .env at the repo root.")
    for attempt in range(RETRIES):
        try:
            resp = httpx.get(
                f"{API}/{path}",
                params=params,
                headers={"X-API-Key": key.get_secret_value()},
                timeout=120,
            )
        except httpx.HTTPError as exc:
            raise OpenAQError(f"OpenAQ request failed: {type(exc).__name__}") from None
        if resp.status_code == 429 and attempt < RETRIES - 1:
            time.sleep(RETRY_WAIT_S)
            continue
        if resp.status_code != 200:
            raise OpenAQError(f"OpenAQ returned HTTP {resp.status_code} for {path}")
        return resp.json()
    raise OpenAQError("OpenAQ kept answering HTTP 429.")


def _cached(name: str, path: str, params: dict[str, str | int]) -> tuple[dict, bool]:
    """A response from the cache, or downloaded and cached. Says whether it was downloaded."""
    dest = cache_path("openaq", name)
    if dest.exists():
        return json.loads(dest.read_text()), False
    payload = _get(path, params)
    atomic_write_bytes(dest, json.dumps(payload, separators=(",", ":")).encode())
    return payload, True


def stations(first: date, last: date) -> list[dict]:
    """Reference monitors inside Delhi that reported between `first` and `last`.

    Each has `id`, `name`, `lon`, `lat` and `sensors`: the ids of its PM2.5 sensors. A station
    can have several (a replaced instrument keeps its old id), so all are asked for data.
    """
    outline = places.delhi_geometry()
    w, s, e, n = outline.bounds
    payload, _ = _cached(
        f"locations_delhi_{first.isoformat()}_{last.isoformat()}.json",
        "locations",
        {
            "bbox": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}",
            "parameters_id": PM25_PARAMETER_ID,
            "limit": 1000,
        },
    )
    if payload["meta"]["found"] != len(payload["results"]):
        raise OpenAQError("More Delhi locations than one page holds; add paging.")
    out = []
    for row in payload["results"]:
        point = row["coordinates"]
        seen_first, seen_last = row.get("datetimeFirst"), row.get("datetimeLast")
        if not row["isMonitor"] or row["isMobile"] or not seen_first or not seen_last:
            continue
        if (
            seen_last["local"][:10] < first.isoformat()
            or seen_first["local"][:10] > last.isoformat()
        ):
            continue
        if not outline.contains(Point(point["longitude"], point["latitude"])):
            continue
        sensors = [x["id"] for x in row["sensors"] if x["parameter"]["id"] == PM25_PARAMETER_ID]
        if sensors:
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "lon": point["longitude"],
                    "lat": point["latitude"],
                    "sensors": sensors,
                }
            )
    return out


def parse_days(payload: dict) -> pd.DataFrame:
    """A sensor's daily means as `day` (IST date) and `pm25`, keeping well-covered, real days."""
    rows = [
        {"day": row["period"]["datetimeFrom"]["local"][:10], "pm25": float(row["value"])}
        for row in payload["results"]
        if row["value"] is not None
        and row["value"] > 0
        and row["coverage"]["percentComplete"] >= MIN_DAY_COVERAGE_PCT
    ]
    # An empty table would otherwise make the column untyped and spoil later means.
    return pd.DataFrame(rows, columns=["day", "pm25"]).astype({"pm25": float})


def fetch_daily(season: int, log: Callable[[str], None] = lambda _: None) -> pd.DataFrame:
    """Daily PM2.5 per station for a finished season: `station`, `name`, `day`, `pm25`."""
    first, last = season_window(season)
    frames = []
    found = stations(first, last)
    for number, station in enumerate(found, 1):
        parts = []
        for sensor in station["sensors"]:
            payload, downloaded = _cached(
                f"days_{sensor}_{first.isoformat()}_{last.isoformat()}.json",
                f"sensors/{sensor}/days",
                {"date_from": first.isoformat(), "date_to": last.isoformat(), "limit": 100},
            )
            parts.append(parse_days(payload))
            if downloaded:
                time.sleep(PAUSE_S)
        days = pd.concat(parts, ignore_index=True)
        # Two sensors at one station on the same day are averaged.
        days = days.groupby("day", as_index=False)["pm25"].mean()
        days = days[(days["day"] >= first.isoformat()) & (days["day"] <= last.isoformat())]
        frames.append(days.assign(station=station["id"], name=station["name"]))
        log(f"OpenAQ: {station['name']}: {len(days)} days ({number}/{len(found)})")
    columns = ["station", "name", "day", "pm25"]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]


def city_mean(daily: pd.DataFrame, min_stations: int = MIN_STATIONS) -> pd.DataFrame:
    """Mean PM2.5 across stations per day (`pm25`, `stations`), for days with enough stations."""
    grouped = daily.groupby("day")["pm25"].agg(pm25="mean", stations="count")
    return grouped[grouped["stations"] >= min_stations]


def compare(sai: pd.Series, pm25: pd.Series) -> dict:
    """Pearson and Spearman correlation of two daily series over the days both have."""
    both = pd.concat({"sai": sai, "pm25": pm25}, axis=1).astype(float).dropna()
    if len(both) < 3 or both["sai"].nunique() < 2 or both["pm25"].nunique() < 2:
        return {"days": int(len(both)), "pearson": None, "spearman": None}
    pearson = stats.pearsonr(both["sai"], both["pm25"])
    spearman = stats.spearmanr(both["sai"], both["pm25"])
    return {
        "days": int(len(both)),
        "pearson": {"r": round(float(pearson.statistic), 3), "p": float(f"{pearson.pvalue:.3g}")},
        "spearman": {
            "rho": round(float(spearman.statistic), 3),
            "p": float(f"{spearman.pvalue:.3g}"),
        },
    }


def report(season: int, sai: pd.Series, daily: pd.DataFrame, districts: list[str]) -> dict:
    """The `pm25` block of `validation/{season}.json`. `sai` is indexed by ISO date."""
    city = city_mean(daily)
    result = compare(sai, city["pm25"])
    days = sorted(set(sai.index) | set(city.index))
    return {
        "source": SOURCE,
        "smoke_sources": districts,
        "stations": int(daily["station"].nunique()),
        "station_days": int(len(daily)),
        "min_day_coverage_pct": MIN_DAY_COVERAGE_PCT,
        "min_stations_per_day": MIN_STATIONS,
        **result,
        "series": [
            {
                "date": day,
                "sai": None if day not in sai.index else round(float(sai[day]), 2),
                "pm25": None if day not in city.index else round(float(city["pm25"][day]), 1),
                "stations": 0 if day not in city.index else int(city["stations"][day]),
            }
            for day in days
        ],
        "caveats": CAVEATS,
    }


def plot(block: dict, season: int, path: Path) -> None:
    """Dual-axis chart of the daily Delhi-mean index and observed PM2.5."""
    ink, ember, cyan, grid = "#0B0F14", "#FF6B1A", "#22D3EE", "#2A3344"
    days = pd.to_datetime([row["date"] for row in block["series"]])
    sai = np.array([np.nan if row["sai"] is None else row["sai"] for row in block["series"]])
    pm25 = np.array([np.nan if row["pm25"] is None else row["pm25"] for row in block["series"]])

    fig, left = plt.subplots(figsize=(14, 5.2), facecolor=ink)
    left.set_facecolor(ink)
    left.fill_between(days, np.nan_to_num(sai), color=ember, alpha=0.55, linewidth=0)
    left.plot(days, sai, color=ember, linewidth=1.4)
    left.set_ylabel("Delhi-mean Smoke Arrival Index (0-100, relative)", color=ember)
    left.set_ylim(0, max(10.0, float(np.nanmax(sai)) * 1.15))
    right = left.twinx()
    right.plot(days, pm25, color=cyan, linewidth=1.6, marker="o", markersize=3)
    right.set_ylabel("Observed PM2.5, mean of Delhi monitors (µg/m³)", color=cyan)
    right.set_ylim(0, float(np.nanmax(pm25)) * 1.15)
    for axis, colour in ((left, ember), (right, cyan)):
        axis.tick_params(colors="white")
        axis.tick_params(axis="y", colors=colour)
        for spine in axis.spines.values():
            spine.set_color(grid)
    pearson, spearman = block["pearson"], block["spearman"]
    scores = (
        "too few days to correlate"
        if pearson is None
        else f"Pearson r = {pearson['r']:.2f}, Spearman rho = {spearman['rho']:.2f}"
    )
    left.set_title(
        f"Smoke Arrival Index vs observed PM2.5, Delhi, {season} season: {scores}, "
        f"{block['days']} days, {block['stations']} monitors\n"
        f"Index models smoke from {', '.join(block['smoke_sources'])} only. "
        "PM2.5: CPCB and DPCC monitors via OpenAQ.",
        color="white",
        fontsize=11,
        loc="left",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=ink, bbox_inches="tight")
    plt.close(fig)
