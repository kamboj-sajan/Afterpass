"""The replay path end to end on synthetic scars and winds, checking the published files."""

import json
from datetime import date

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, box

from afterpass import outlook, places, smoke
from afterpass import publish as publisher
from afterpass.pipeline import Replay

DELHI = box(76.84, 28.41, 77.35, 28.88)


@pytest.fixture
def world(tmp_path, monkeypatch, make_wind):
    """Scars west of Delhi, a steady westerly, and every output under tmp_path."""
    monkeypatch.setattr(publisher, "SMOKE_DIR", tmp_path / "smoke")
    monkeypatch.setattr(outlook, "cache_path", lambda *p: tmp_path.joinpath(*p))
    monkeypatch.setattr(
        outlook, "season_window", lambda season: (date(2025, 11, 1), date(2025, 11, 2))
    )
    scars = gpd.GeoDataFrame(
        {
            "window_start": ["2025-10-31", "2025-11-01"],
            "first_detected": ["2025-11-02", "2025-11-02"],
            "area_ha": [40.0, 20.0],
        },
        geometry=[box(76.5, 28.6, 76.51, 28.61), box(76.6, 28.7, 76.61, 28.71)],
        crs="EPSG:4326",
    ).to_crs("EPSG:32643")

    class District:
        name = "Test"

    monkeypatch.setattr(
        outlook.pipeline,
        "load_replay",
        lambda name, season: Replay(District(), scars, scars.iloc[:0], {}),
    )
    monkeypatch.setattr(places, "delhi_geometry", lambda: DELHI)
    localities = gpd.GeoDataFrame(
        {
            "locality_id": ["a-dwarka", "b-far"],
            "name": ["Dwarka", "Far"],
            "name_hi": ["द्वारका", ""],
            "district": ["South West", "North"],
        },
        geometry=[Point(77.05, 28.58), Point(80.0, 20.0)],
        crs="EPSG:4326",
    )
    monkeypatch.setattr(places, "load_delhi_localities", lambda: (localities, "test-release"))
    start = smoke.ist_timestamp(date(2025, 10, 30)) - 3600
    wind = make_wind(4.0, 0.0, pbl=300.0, hours=24 * 7, start=start)
    monkeypatch.setattr(outlook.winds, "load", lambda first, last, source: wind)
    return tmp_path


def test_replay_publishes_one_run_per_day(world) -> None:
    params = smoke.SmokeParams(max_particles_per_day=2000, trips_cap=300)
    result = outlook.replay(2025, ["Test"], "historical_forecast", params)

    assert [run["run_id"] for run in result.runs] == ["2025-11-01", "2025-11-02"]
    folder = world / "smoke" / "2025-11-01"
    trips = json.loads((folder / "trips.json").read_text())
    sai = json.loads((folder / "delhi_sai_h3r7.json").read_text())
    localities = json.loads((folder / "localities.json").read_text())
    index = json.loads((world / "smoke" / "index.json").read_text())

    for payload in (trips, sai, localities, index):
        assert payload["demo"] is False and "generated_at" in payload
        assert "Open-Meteo" in payload["source_versions"]["winds_attribution"]
    assert 0 < len(trips["items"]) <= 300
    assert set(trips["items"][0]) == {"path", "ts", "w", "age0"}
    assert len(sai["hours"]) == 48
    assert sai["hours"][0] == smoke.ist_timestamp(date(2025, 11, 1))
    values = np.array(list(sai["cells"].values()))
    assert values.shape[1] == 48 and values.min() >= 0 and values.max() <= 100
    # A steady westerly carries the smoke into Delhi, so the index must register it.
    assert values.max() > 0
    assert [item["name"] for item in localities["items"]] == ["Dwarka"]
    assert localities["items"][0]["name_hi"] == "द्वारका"
    assert len(localities["items"][0]["sai"]) == 48
    assert [run["run_id"] for run in index["runs"]] == ["2025-11-01", "2025-11-02"]
    assert index["runs"][0]["peak_level"] in {name for name, _ in smoke.LEVELS}
    assert (world / "smoke" / "sai_2025.npz").exists()


def test_daily_delhi_sai_is_per_ist_day(world) -> None:
    params = smoke.SmokeParams(max_particles_per_day=500, trips_cap=50)
    outlook.replay(2025, ["Test"], "historical_forecast", params)
    daily = outlook.daily_delhi_sai(2025)
    assert list(daily.index) == [date(2025, 11, 1), date(2025, 11, 2)]
