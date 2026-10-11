import geopandas as gpd
import numpy as np
import pytest
from odc.geo.geobox import GeoBox
from shapely.geometry import box

from afterpass import validate
from afterpass.pipeline import District, Replay


def test_wilson_interval_matches_known_values() -> None:
    low, high = validate.wilson(90, 100)
    assert low == pytest.approx(0.8256, abs=1e-3)
    assert high == pytest.approx(0.9448, abs=1e-3)
    assert validate.wilson(0, 0) is None
    low, high = validate.wilson(10, 10)
    assert high == pytest.approx(1.0) and 0.70 < low < 0.75


def test_score_excludes_unsure_and_unlabelled() -> None:
    items = [
        {"id": "s1", "kind": "scar", "detected": True},
        {"id": "s2", "kind": "scar", "detected": True},
        {"id": "s3", "kind": "scar", "detected": True},
        {"id": "s4", "kind": "scar", "detected": True},
        {"id": "p1", "kind": "point", "detected": True},
        {"id": "p2", "kind": "point", "detected": False},
        {"id": "p3", "kind": "point", "detected": False},
    ]
    labels = {"s1": "b", "s2": "b", "s3": "n", "s4": "u", "p1": "b", "p2": "b", "p3": "n"}
    result = validate.score(items, labels)
    assert result["precision"]["value"] == pytest.approx(0.667, abs=1e-3)
    assert result["precision"]["n"] == 3
    assert result["scars"] == {
        "sampled": 4,
        "burned": 2,
        "not_burned": 1,
        "unsure": 1,
        "unlabelled": 0,
    }
    assert result["detected_share_of_burned_points"]["value"] == 0.5
    assert result["points"]["burned"] == 2 and result["points"]["not_burned"] == 1


def test_score_with_no_labels() -> None:
    result = validate.score([{"id": "s1", "kind": "scar", "detected": True}], {})
    assert result["precision"] == {"value": None, "wilson_95": None, "n": 0}
    assert result["scars"]["unlabelled"] == 1


def test_sample_scars_is_seeded_and_uses_scar_windows() -> None:
    crs = "EPSG:32643"
    scars = gpd.GeoDataFrame(
        {
            "scar_id": [f"sangrur-{i:06d}" for i in range(50)],
            "first_detected": ["2025-11-02"] * 50,
            "window_start": ["2025-10-25"] * 50,
        },
        geometry=[
            box(590_000 + 200 * i, 3_340_000, 590_100 + 200 * i, 3_340_100) for i in range(50)
        ],
        crs=crs,
    )
    geobox = GeoBox.from_bbox((590_000, 3_340_000, 600_000, 3_350_000), crs, resolution=20)
    district = District("Sangrur", "sangrur", box(75.5, 29.7, 76.2, 30.7), box(0, 0, 1, 1), geobox)
    replay = Replay(district, scars, scars.iloc[:0], {"window": ["2025-10-01", "2025-11-30"]})
    first = validate.sample_scars([replay], np.random.default_rng(1), 10)
    again = validate.sample_scars([replay], np.random.default_rng(1), 10)
    assert [i.id for i in first] == [i.id for i in again]
    assert len({i.id for i in first}) == 10
    item = first[0]
    assert (item.kind, item.pre, item.post, item.detected) == (
        "scar",
        "2025-10-25",
        "2025-11-02",
        True,
    )
    assert 75 < item.lon < 77 and 29 < item.lat < 31
    assert item.outline[0] == item.outline[-1]  # closed ring


def test_chip_bounds_are_600_m_on_the_10_m_grid() -> None:
    item = validate.QAItem(
        id="x",
        kind="scar",
        district="Sangrur",
        slug="sangrur",
        crs="EPSG:32643",
        lon=75.9,
        lat=30.2,
        pre="2025-10-25",
        post="2025-11-02",
        detected=True,
        outline=[
            [590_003.0, 3_340_007.0],
            [590_103.0, 3_340_007.0],
            [590_103.0, 3_340_107.0],
            [590_003.0, 3_340_007.0],
        ],
    )
    west, south, east, north = validate._chip_bounds(item)
    assert (east - west, north - south) == (600, 600)
    assert west % 10 == 0 and south % 10 == 0
    assert west < 590_003 and east > 590_103
