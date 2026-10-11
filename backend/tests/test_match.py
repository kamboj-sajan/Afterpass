import geopandas as gpd
from shapely.geometry import Point, box

from afterpass import match

CRS = "EPSG:32643"


def _scars(*rows):
    return gpd.GeoDataFrame(
        [{"window_start": ws, "first_detected": fd, "geometry": geom} for ws, fd, geom in rows],
        crs=CRS,
    )


def _detections(*rows):
    return gpd.GeoDataFrame(
        {"sensor": [r[0] for r in rows], "acq_date": [r[1] for r in rows]},
        geometry=[Point(r[2], r[3]) for r in rows],
        crs=CRS,
    )


FIELD = box(0, 0, 100, 100)


def test_viirs_distance_limit() -> None:
    scars = _scars(("2025-11-02", "2025-11-04", FIELD))
    assert match.recorded(scars, _detections(("VIIRS", "2025-11-03", 470, 50))).tolist() == [True]
    assert match.recorded(scars, _detections(("VIIRS", "2025-11-03", 480, 50))).tolist() == [False]


def test_modis_reaches_one_kilometre() -> None:
    scars = _scars(("2025-11-02", "2025-11-04", FIELD))
    assert match.recorded(scars, _detections(("MODIS", "2025-11-03", 1090, 50))).tolist() == [True]
    assert match.recorded(scars, _detections(("MODIS", "2025-11-03", 1110, 50))).tolist() == [False]


def test_date_window_has_one_day_of_slack() -> None:
    scars = _scars(("2025-11-02", "2025-11-04", FIELD))
    for day, expected in (
        ("2025-10-31", False),
        ("2025-11-01", True),
        ("2025-11-05", True),
        ("2025-11-06", False),
    ):
        assert match.recorded(scars, _detections(("VIIRS", day, 50, 50))).tolist() == [expected]


def test_each_scar_is_judged_on_its_own_window() -> None:
    scars = _scars(
        ("2025-11-02", "2025-11-04", FIELD),
        ("2025-11-09", "2025-11-12", box(5000, 0, 5100, 100)),
    )
    detections = _detections(("VIIRS", "2025-11-03", 50, 50), ("VIIRS", "2025-11-03", 5050, 50))
    assert match.recorded(scars, detections).tolist() == [True, False]


def test_empty_inputs() -> None:
    scars = _scars(("2025-11-02", "2025-11-04", FIELD))
    assert match.recorded(scars, _detections()).tolist() == [False]
    assert match.recorded(scars.iloc[:0], _detections(("VIIRS", "2025-11-03", 0, 0))).tolist() == []
