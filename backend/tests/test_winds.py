import numpy as np
import pytest

from afterpass import winds


def test_grid_matches_the_brief() -> None:
    assert winds.GRID_LATS[0] == 27.5 and winds.GRID_LATS[-1] == 32.75
    assert winds.GRID_LONS[0] == 73.5 and winds.GRID_LONS[-1] == 78.0
    assert len(winds.grid_points()) == 22 * 19


@pytest.mark.parametrize(
    ("direction", "u", "v"),
    [(0, 0, -5), (90, -5, 0), (180, 0, 5), (270, 5, 0), (315, 3.5355, -3.5355)],
)
def test_direction_is_where_the_wind_comes_from(direction, u, v) -> None:
    # A north-westerly (315) blows towards the south-east: east and south.
    got = winds.wind_to_uv(np.array([5.0]), np.array([float(direction)]))
    assert got[0][0] == pytest.approx(u, abs=1e-3)
    assert got[1][0] == pytest.approx(v, abs=1e-3)


def test_bilinear_in_space(make_wind) -> None:
    # u rises 1 m/s per degree of longitude, so interpolation must reproduce it exactly.
    lon_grid = np.broadcast_to(winds.GRID_LONS, (len(winds.GRID_LATS), len(winds.GRID_LONS)))
    w = make_wind(lon_grid - 73.5, 0.0)
    u, _ = w.velocity(np.array([74.1, 76.37]), np.array([30.0, 28.9]), 0.0)
    assert u == pytest.approx([0.6, 2.87])


def test_linear_in_time(make_wind) -> None:
    w = make_wind(0.0, 0.0)
    w.u[1] = 4.0
    u, _ = w.velocity(np.array([75.0]), np.array([30.0]), 1800.0)
    assert u[0] == pytest.approx(2.0)


def test_outside_the_hours_is_an_error(make_wind) -> None:
    with pytest.raises(winds.WindError):
        make_wind(0.0, 0.0).velocity(np.array([75.0]), np.array([30.0]), 3 * 3600.0)


def test_contains(make_wind) -> None:
    w = make_wind(0.0, 0.0)
    inside = w.contains(np.array([75.0, 73.4, 78.1]), np.array([30.0, 30.0, 30.0]))
    assert inside.tolist() == [True, False, False]
