import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from afterpass import aggregate, places

CRS = "EPSG:32643"
# A point in Sangrur district, in UTM 43N metres.
X0, Y0 = 590_000.0, 3_340_000.0


def _scars(*rows) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        [
            {
                "district": "Sangrur",
                "first_detected": day,
                "window_start": "2025-10-25",
                "area_ha": geom.area / 10_000,
                "recorded": recorded,
                "geometry": geom,
            }
            for day, recorded, geom in rows
        ],
        crs=CRS,
    )


def test_iso_week_labels() -> None:
    assert aggregate.iso_week("2025-11-02") == "2025-W44"  # Sunday closes the ISO week
    assert aggregate.iso_week("2025-11-03") == "2025-W45"
    assert aggregate.iso_week("2025-12-29") == "2026-W01"


def test_totals_split_recorded_and_unrecorded() -> None:
    scars = _scars(
        ("2025-11-02", True, box(X0, Y0, X0 + 200, Y0 + 100)),  # 2 ha recorded
        ("2025-11-04", False, box(X0 + 500, Y0, X0 + 800, Y0 + 200)),  # 6 ha unrecorded
    )
    totals = aggregate.totals(aggregate.with_areas(scars))
    assert totals == {
        "burned_ha": 8.0,
        "recorded_ha": 2.0,
        "unrecorded_ha": 6.0,
        "unrecorded_share": 0.75,
        "scar_count": 2,
    }


def test_totals_with_no_scars() -> None:
    empty = pd.DataFrame({"burned_ha": [], "recorded_ha": [], "unrecorded_ha": []})
    totals = aggregate.totals(empty)
    assert totals["burned_ha"] == 0 and totals["scar_count"] == 0
    assert totals["unrecorded_share"] is None


def test_h3_split_conserves_area_across_cells() -> None:
    # A 2 km x 1 km scar is far wider than one resolution-8 cell (about 0.9 km across).
    big = box(X0, Y0, X0 + 2000, Y0 + 1000)
    scars = _scars(
        ("2025-11-02", False, big), ("2025-11-09", True, box(X0, Y0 + 3000, X0 + 100, Y0 + 3100))
    )
    district = gpd.GeoSeries([box(X0 - 5000, Y0 - 5000, X0 + 8000, Y0 + 8000)], crs=CRS)
    cells = aggregate.h3_cells(district.to_crs("EPSG:4326").iloc[0], CRS)
    table = aggregate.burns_by_h3_week(scars, cells)

    assert table["burned_ha"].sum() == pytest.approx(201.0, rel=1e-6)
    assert table["unrecorded_ha"].sum() == pytest.approx(200.0, rel=1e-6)
    assert table["recorded_ha"].sum() == pytest.approx(1.0, rel=1e-6)
    first_week = table[table["week"] == "2025-W44"]
    assert len(first_week) > 1  # split over several cells
    assert (table["burned_ha"] == table["recorded_ha"] + table["unrecorded_ha"]).all()


def test_village_assignment_and_near_label() -> None:
    localities = gpd.GeoDataFrame(
        {"locality_id": ["aaaa1111-alpha", "bbbb2222-beta"], "name": ["Alpha", "Beta"]},
        geometry=[Point(X0, Y0), Point(X0 + 10_000, Y0)],
        crs=CRS,
    )
    scars = _scars(
        ("2025-11-02", False, box(X0 + 900, Y0, X0 + 1000, Y0 + 100)),  # 1 km from Alpha
        ("2025-11-02", False, box(X0 + 4400, Y0, X0 + 4500, Y0 + 100)),  # 4.4 km from Alpha
        ("2025-11-02", True, box(X0 + 9000, Y0, X0 + 9100, Y0 + 100)),  # 0.9 km from Beta
    )
    out = places.assign_villages(scars, localities)
    assert out["village"].tolist() == ["Alpha", "near Alpha", "Beta"]
    assert out["village_id"].tolist() == ["aaaa1111-alpha", "near-aaaa1111-alpha", "bbbb2222-beta"]


def test_village_records_sorted_by_unrecorded_area() -> None:
    scars = _scars(
        ("2025-11-02", False, box(X0, Y0, X0 + 100, Y0 + 100)),
        ("2025-11-09", False, box(X0, Y0 + 500, X0 + 300, Y0 + 600)),
        ("2025-11-02", True, box(X0 + 5000, Y0, X0 + 5400, Y0 + 100)),
    ).assign(
        village_id=["a-alpha", "a-alpha", "b-beta"],
        village=["Alpha", "Alpha", "Beta"],
        village_lon=[75.9, 75.9, 76.0],
        village_lat=[30.2, 30.2, 30.2],
    )
    records = aggregate.villages(aggregate.with_areas(scars))
    assert [r["id"] for r in records] == ["a-alpha", "b-beta"]
    alpha, beta = records
    assert alpha["burned_ha"] == 4.0 and alpha["unrecorded_ha"] == 4.0 and alpha["share"] == 1.0
    assert [w["week"] for w in alpha["weekly"]] == ["2025-W44", "2025-W45"]
    assert beta["unrecorded_ha"] == 0.0 and beta["share"] == 0.0


def test_firms_counts_use_ist_hours() -> None:
    table = pd.DataFrame(
        {
            "acq_date": ["2025-11-02", "2025-11-02", "2025-11-03"],
            "source": ["VIIRS_SNPP_SP", "MODIS_SP", "VIIRS_SNPP_SP"],
            "acq_dt_ist": pd.to_datetime(
                ["2025-11-02 13:35", "2025-11-02 14:10", "2025-11-04 01:40"]
            ).tz_localize("Asia/Kolkata"),
        }
    )
    counts = aggregate.firms_counts(table)
    assert counts["firms_count"] == 3
    assert counts["by_satellite"] == {"MODIS_SP": 1, "VIIRS_SNPP_SP": 2}
    assert counts["by_ist_hour"][13] == 1 and counts["by_ist_hour"][14] == 1
    assert counts["by_ist_hour"][1] == 1 and sum(counts["by_ist_hour"]) == 3
