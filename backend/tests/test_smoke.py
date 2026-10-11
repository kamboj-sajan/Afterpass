import math
from datetime import date, datetime

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from afterpass import smoke

RNG = np.random.default_rng(0)


def test_constant_wind_moves_u_times_t(make_wind) -> None:
    # Brief §8.7: constant wind, no diffusion -> displacement u * t.
    wind = make_wind(5.0, -2.0, hours=3)
    lon, lat = np.array([75.0]), np.array([30.0])
    for k in range(6):  # one hour of 10-minute steps
        lon, lat = smoke.step(lon, lat, k * 600.0, wind, 600.0, 0.0, RNG)
    north_m = (lat[0] - 30.0) / smoke.DEG_PER_M
    east_m = (lon[0] - 75.0) / smoke.DEG_PER_M * math.cos(math.radians(30.0))
    assert north_m == pytest.approx(-2.0 * 3600, rel=1e-3)
    # Moving south changes cos(lat) slightly, hence the looser tolerance.
    assert east_m == pytest.approx(5.0 * 3600, rel=2e-3)


def test_zero_wind_zero_diffusion_stays_put(make_wind) -> None:
    wind = make_wind(0.0, 0.0)
    lon, lat = smoke.step(np.array([75.0, 76.2]), np.array([30.0, 29.1]), 0.0, wind, 600, 0, RNG)
    assert lon.tolist() == [75.0, 76.2] and lat.tolist() == [30.0, 29.1]


def test_diffusion_spread_matches_sigma(make_wind) -> None:
    params = smoke.SmokeParams()
    assert params.sigma_m == pytest.approx(math.sqrt(2 * 1000 * 600))
    wind = make_wind(0.0, 0.0)
    n = 20_000
    lon, lat = smoke.step(np.full(n, 75.0), np.full(n, 30.0), 0.0, wind, 600, params.sigma_m, RNG)
    spread = np.std((lat - 30.0) / smoke.DEG_PER_M)
    assert spread == pytest.approx(params.sigma_m, rel=0.03)


def test_weight_decays_to_1_over_e_at_tau() -> None:
    w = smoke.decayed(2.0, np.array([0.0, 36 * 3600.0]), 36.0)
    assert w.tolist() == pytest.approx([2.0, 2.0 / math.e])


def test_burn_days_run_from_window_start_to_the_day_before_the_scar() -> None:
    assert smoke.burn_days("2025-11-01", "2025-11-04") == [
        date(2025, 11, 1),
        date(2025, 11, 2),
        date(2025, 11, 3),
    ]
    assert smoke.burn_days("2025-11-03", "2025-11-04") == [date(2025, 11, 3)]


def test_sources_spread_area_over_burn_days() -> None:
    # A small field near Sangrur, in UTM 43N like the replay scars.
    scars = gpd.GeoDataFrame(
        {"window_start": ["2025-11-01"], "first_detected": ["2025-11-05"], "area_ha": [8.0]},
        geometry=[box(75.8, 30.2, 75.801, 30.201)],
        crs="EPSG:4326",
    ).to_crs("EPSG:32643")
    table = smoke.sources_replay(scars)
    assert table["day"].tolist() == [date(2025, 11, d) for d in (1, 2, 3, 4)]
    assert table["ha"].tolist() == [2.0, 2.0, 2.0, 2.0]
    assert h3.get_resolution(table["cell"].iloc[0]) == 7


def test_release_is_in_the_ist_burn_window_and_keeps_the_area() -> None:
    cell = h3.latlng_to_cell(30.2, 75.8, 7)
    sources = pd.DataFrame(
        {"cell": [cell, cell], "day": [date(2025, 11, 1), date(2025, 11, 2)], "ha": [300.0, 150.0]}
    )
    params = smoke.SmokeParams(max_particles_per_day=3000)
    particles = smoke.release(sources, params, np.random.default_rng(1))
    assert particles.ha_each == pytest.approx(0.1)
    assert len(particles) == 4500
    hours = [datetime.fromtimestamp(t, smoke.IST_TZ) for t in particles.released[::97]]
    assert all(15 <= h.hour < 19 for h in hours)
    assert np.all(np.diff(particles.released) >= 0)
    # Within about one cell edge of the cell centre.
    assert np.abs(particles.lat - 30.2).max() < 0.03


def test_sources_live_persists_the_last_three_days() -> None:
    cell = h3.latlng_to_cell(30.2, 75.8, 7)
    recent = pd.DataFrame({"cell": [cell] * 3, "day": [None] * 3, "ha": [3.0, 6.0, 9.0]})
    days = [date(2026, 10, 11), date(2026, 10, 12)]
    firms_today = pd.DataFrame({"latitude": [30.2], "longitude": [75.8], "frp": [10.0]})
    table = smoke.sources_live(recent, days, firms_today, days[0], ha_per_frp=0.5)
    assert table.set_index("day")["ha"].to_dict() == {days[0]: 6.0 + 5.0, days[1]: 6.0}


def _square_receptors() -> smoke.Receptors:
    return smoke.delhi_receptors(box(77.0, 28.5, 77.1, 28.6))


def test_receptors_cover_the_area_and_look_up_points() -> None:
    receptors = _square_receptors()
    assert all(h3.get_resolution(c) == 7 for c in receptors.cells)
    where = receptors.index(np.array([77.05, 75.0]), np.array([28.55, 30.0]))
    assert receptors.cells[where[0]] == h3.latlng_to_cell(28.55, 77.05, 7)
    assert where[1] == -1


def test_sai_divides_by_mixing_height_with_a_floor(make_wind) -> None:
    receptors = _square_receptors()
    start = smoke.ist_timestamp(date(2025, 11, 3))
    centre = receptors.cells.index(h3.latlng_to_cell(28.55, 77.05, 7))
    lat, lng = h3.cell_to_latlng(receptors.cells[centre])
    particles = smoke.Particles(np.array([lng]), np.array([lat]), np.array([start]), ha_each=1.0)
    for pbl, divisor in ((50.0, 100.0), (400.0, 400.0)):
        wind = make_wind(0.0, 0.0, pbl=pbl, hours=3, start=start)
        params = smoke.SmokeParams(diffusivity_m2s=0.0, tau_h=1e9)
        sai = smoke.simulate(
            particles, wind, receptors, start, start + 3600, params, [], lambda *_: None
        )
        assert sai.raw.shape == (1, len(receptors.cells))
        assert sai.raw[0, centre] == pytest.approx(1.0 / divisor)
        assert sai.raw[0].sum() == pytest.approx(1.0 / divisor)


def test_simulate_emits_capped_trips_for_each_run(make_wind) -> None:
    receptors = _square_receptors()
    start = smoke.ist_timestamp(date(2025, 11, 3))
    wind = make_wind(3.0, -3.0, hours=8, start=start)
    n = 500
    particles = smoke.Particles(
        np.full(n, 75.8), np.full(n, 30.2), start + np.linspace(0, 3600, n), ha_each=0.5
    )
    params = smoke.SmokeParams(run_hours=4, trips_cap=100, diffusivity_m2s=100.0)
    runs = {}
    smoke.simulate(
        particles,
        wind,
        receptors,
        start,
        start + 6 * 3600,
        params,
        [start],
        lambda s, trips: runs.__setitem__(s, trips),
    )
    trips = runs[start]
    assert len(trips) == 100
    first = trips[0]
    # A vertex every 2 hours over a 4-hour window, plus the release point for some.
    assert len(first["path"]) == len(first["ts"]) >= 3
    assert all(start <= ts <= start + 4 * 3600 for ts in first["ts"])
    assert first["ts"] == sorted(first["ts"])
    assert all(round(x, 4) == x for point in first["path"] for x in point)
    # Each drawn trail stands for the area of the particles it replaces.
    assert sum(t["w"] for t in trips) == pytest.approx(n * 0.5, rel=0.01)
    # Trails that start at release are newborn; older ones carry their age in.
    assert all(t["age0"] >= 0 for t in trips) and min(t["age0"] for t in trips) == 0
    # Moving south-east.
    assert first["path"][-1][0] > first["path"][0][0] > 75.7
    assert first["path"][-1][1] < first["path"][0][1]


def test_trips_lead_into_a_run_so_smoke_arrives_with_its_trail(make_wind) -> None:
    receptors = _square_receptors()
    start = smoke.ist_timestamp(date(2025, 11, 3))
    wind = make_wind(1.0, -1.0, hours=16, start=start)
    n = 50
    particles = smoke.Particles(np.full(n, 75.8), np.full(n, 30.2), np.full(n, start), ha_each=1.0)
    run_start = start + 8 * 3600
    earliest = {}
    for lead in (0, 6):
        params = smoke.SmokeParams(run_hours=4, diffusivity_m2s=0.0, trail_lead_h=lead)
        runs = {}
        smoke.simulate(
            particles,
            wind,
            receptors,
            start,
            start + 14 * 3600,
            params,
            [run_start],
            lambda s, trips, runs=runs: runs.__setitem__(s, trips),
        )
        earliest[lead] = min(trip["ts"][0] for trip in runs[run_start])
        assert max(trip["ts"][-1] for trip in runs[run_start]) == run_start + 4 * 3600
    assert earliest[0] == run_start
    assert earliest[6] == run_start - 6 * 3600


def test_normalise_and_levels() -> None:
    raw = np.array([[0.0, 1.0], [2.0, 4.0]])
    p95 = smoke.normaliser(raw)
    assert p95 == pytest.approx(np.percentile([1.0, 2.0, 4.0], 95))
    assert smoke.normalise(raw, p95).max() == 100
    assert smoke.normalise(raw, 0.0).sum() == 0
    assert [smoke.level(x) for x in (0, 24, 25, 50, 74, 75, 100)] == [
        "low",
        "low",
        "moderate",
        "high",
        "high",
        "very_high",
        "very_high",
    ]
