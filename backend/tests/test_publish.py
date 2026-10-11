import json

import geopandas as gpd
import pandas as pd
import pytest
from odc.geo.geobox import GeoBox
from shapely.geometry import Point, box

from afterpass import places, publish
from afterpass.pipeline import District, Replay

CRS = "EPSG:32643"
X0, Y0 = 590_000.0, 3_340_000.0


@pytest.fixture
def replay() -> Replay:
    scars = gpd.GeoDataFrame(
        {
            "scar_id": ["sangrur-000000", "sangrur-000001", "sangrur-000002"],
            "district": ["Sangrur"] * 3,
            "first_detected": ["2025-11-02", "2025-11-02", "2025-11-09"],
            "window_start": ["2025-10-25", "2025-10-25", "2025-11-07"],
            "area_ha": [2.0, 6.0, 1.0],
            "recorded": [True, False, False],
            "village_id": ["aaaa1111-alpha", "aaaa1111-alpha", "bbbb2222-beta"],
            "village": ["Alpha", "Alpha", "Beta"],
            "village_lon": [75.93, 75.93, 75.99],
            "village_lat": [30.19, 30.19, 30.19],
        },
        geometry=[
            box(X0, Y0, X0 + 200, Y0 + 100),
            box(X0 + 500, Y0, X0 + 800, Y0 + 200),
            box(X0 + 5000, Y0, X0 + 5100, Y0 + 100),
        ],
        crs=CRS,
    )
    firms = gpd.GeoDataFrame(
        {
            "longitude": [75.9312345],
            "latitude": [30.1912345],
            "acq_date": ["2025-11-01"],
            "acq_dt_ist": pd.to_datetime(["2025-11-01 13:35"]).tz_localize("Asia/Kolkata"),
            "satellite": ["N"],
            "source": ["VIIRS_SNPP_SP"],
            "confidence": ["n"],
            "frp": [4.26],
        },
        geometry=[Point(X0 + 50, Y0 + 50)],
        crs=CRS,
    )
    outline = gpd.GeoSeries([box(X0 - 3000, Y0 - 3000, X0 + 9000, Y0 + 4000)], crs=CRS)
    district = District(
        "Sangrur",
        "sangrur",
        outline.to_crs("EPSG:4326").iloc[0],
        outline.iloc[0],
        GeoBox.from_bbox(outline.total_bounds, CRS, resolution=20),
    )
    info = {
        "window": ["2025-10-01", "2025-11-30"],
        "cropland_ha": 5000.0,
        "sentinel2": [{"date": "2025-11-09", "valid_pct": 100.0, "scars": 1, "burned_ha": 1.0}],
        "missing_dates": [],
    }
    return Replay(district, scars, firms, info)


def test_public_files_follow_the_contract(replay, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(publish, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(publish, "VALIDATION_DIR", tmp_path / "validation")
    monkeypatch.setattr(
        places,
        "load_districts",
        lambda: pd.DataFrame({"district": ["Sangrur"], "state": ["Punjab"]}),
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "2025.json").write_text(json.dumps({"thresholds": {}}))

    paths = publish.publish_local([replay], 2025, "2026-09-23.1")
    root = tmp_path / "public"
    names = sorted(str(p.relative_to(root)) for p in paths)
    assert names == [
        "imagery/2025/index.json",
        "latest.json",
        "seasons/2025/burns_h3_r8.json",
        "seasons/2025/districts.geojson",
        "seasons/2025/firms_points.json",
        "seasons/2025/scars/sangrur/2025-W44.geojson",
        "seasons/2025/scars/sangrur/2025-W45.geojson",
        "seasons/2025/summary.json",
        "seasons/2025/villages.json",
        "validation/2025.json",
    ]
    for path in paths:
        payload = json.loads(path.read_text())
        assert payload["demo"] is False
        assert payload["generated_at"].endswith("+00:00")
        assert payload["source_versions"]["overture"] == "2026-09-23.1"

    latest = json.loads((root / "latest.json").read_text())
    assert latest["season"] == 2025 and latest["districts"] == ["Sangrur"]
    assert latest["data_through"] == "2025-11-09" and latest["run_id"].startswith("2025-")
    assert latest["seasons"]["2025"]["mode"] == "replay"
    assert latest["seasons"]["2025"]["data_through"] == "2025-11-09"

    summary = json.loads((root / "seasons/2025/summary.json").read_text())
    assert summary["totals"] == {
        "burned_ha": 9.0,
        "recorded_ha": 2.0,
        "unrecorded_ha": 7.0,
        "unrecorded_share": 0.778,
        "scar_count": 3,
    }
    district = summary["districts"][0]
    assert district["state"] == "Punjab" and district["firms"]["firms_count"] == 1
    assert district["firms"]["by_ist_hour"][13] == 1
    assert [d["first_detected"] for d in district["by_day"]] == ["2025-11-02", "2025-11-09"]
    assert [w["week"] for w in district["by_week"]] == ["2025-W44", "2025-W45"]

    cells = json.loads((root / "seasons/2025/burns_h3_r8.json").read_text())["items"]
    assert sum(c["burned_ha"] for c in cells) == pytest.approx(9.0, abs=0.05)
    assert sum(c["unrecorded_ha"] for c in cells) == pytest.approx(7.0, abs=0.05)
    assert set(cells[0]) == {"h3", "week", "district", "burned_ha", "recorded_ha", "unrecorded_ha"}
    assert {c["district"] for c in cells} == {"Sangrur"}

    villages = json.loads((root / "seasons/2025/villages.json").read_text())["items"]
    assert [(v["id"], v["burned_ha"], v["unrecorded_ha"]) for v in villages] == [
        ("aaaa1111-alpha", 8.0, 6.0),
        ("bbbb2222-beta", 1.0, 1.0),
    ]

    point = json.loads((root / "seasons/2025/firms_points.json").read_text())["items"][0]
    assert point == {
        "lon": 75.9312,
        "lat": 30.1912,
        "ist": "2025-11-01T13:35+05:30",
        "sat": "N",
        "conf": "n",
        "frp": 4.3,
        "district": "Sangrur",
    }

    week_44 = json.loads((root / "seasons/2025/scars/sangrur/2025-W44.geojson").read_text())
    week_45 = json.loads((root / "seasons/2025/scars/sangrur/2025-W45.geojson").read_text())
    assert (week_44["week"], len(week_44["features"])) == ("2025-W44", 2)
    assert (week_45["week"], len(week_45["features"])) == ("2025-W45", 1)
    first = week_44["features"][0]
    assert first["properties"]["scar_id"] == "sangrur-000000"
    assert first["properties"]["recorded"] is True
    for lon, lat in first["geometry"]["coordinates"][0]:
        assert round(lon, 5) == lon and round(lat, 5) == lat

    outlines = json.loads((root / "seasons/2025/districts.geojson").read_text())
    properties = outlines["features"][0]["properties"]
    assert properties["district"] == "Sangrur" and properties["unrecorded_ha"] == 7.0


def test_republishing_removes_stale_scar_files(replay, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(publish, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(publish, "VALIDATION_DIR", tmp_path / "validation")
    monkeypatch.setattr(
        places,
        "load_districts",
        lambda: pd.DataFrame({"district": ["Sangrur"], "state": ["Punjab"]}),
    )
    stale = tmp_path / "public/seasons/2025/scars/sangrur.geojson"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    publish.publish_local([replay], 2025, "2026-09-23.1")
    assert not stale.exists()
    assert (tmp_path / "public/seasons/2025/scars/sangrur/2025-W44.geojson").exists()


def test_imagery_index_lists_villages_with_crops(tmp_path, monkeypatch) -> None:
    root = tmp_path / "public"
    monkeypatch.setattr(publish, "PUBLIC_DIR", root)
    meta = {"generated_at": "2026-10-11T00:00:00+00:00", "source_versions": {}, "demo": False}
    assert json.loads(publish.write_imagery_index(meta, 2026).read_text())["items"] == []

    record = {
        "village_id": "aaaa1111-alpha",
        "name": "Alpha",
        "district": "Sangrur",
        "pre_date": "2025-10-25",
        "post_date": "2025-11-02",
        "bounds": [75.9, 30.1, 75.92, 30.12],
    }
    (root / "imagery" / "2025" / "aaaa1111-alpha").mkdir(parents=True)
    (root / "imagery" / "2025" / "aaaa1111-alpha" / "meta.json").write_text(json.dumps(record))
    index_path = publish.write_imagery_index(meta, 2025)
    assert index_path == root / "imagery" / "2025" / "index.json"
    index = json.loads(index_path.read_text())
    assert index["demo"] is False
    assert index["items"] == [{k: v for k, v in record.items() if k != "bounds"}]
    # Each season lists only its own crops.
    assert json.loads(publish.write_imagery_index(meta, 2026).read_text())["items"] == []


def test_latest_lists_every_season_with_the_newest_on_top(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(publish, "PUBLIC_DIR", tmp_path)
    meta = {"generated_at": "2026-10-11T12:00:00+00:00", "source_versions": {}, "demo": False}
    replay = {
        "season": 2025,
        "mode": "replay",
        "run_id": "2025-x",
        "data_through": "2025-11-29",
        "districts": ["Sangrur"],
        "generated_at": meta["generated_at"],
    }
    live = replay | {
        "season": 2026,
        "mode": "live",
        "run_id": "2026-y",
        "data_through": "2026-10-09",
    }
    (tmp_path / "latest.json").write_text(json.dumps(publish.latest_with(replay, meta)))
    both = publish.latest_with(live, meta)
    assert list(both["seasons"]) == ["2025", "2026"]
    assert both["season"] == 2026 and both["data_through"] == "2026-10-09"
    # Publishing the older season again does not move the top of the file back.
    (tmp_path / "latest.json").write_text(json.dumps(both))
    again = publish.latest_with(replay | {"run_id": "2025-z"}, meta)
    assert again["season"] == 2026 and again["seasons"]["2025"]["run_id"] == "2025-z"


def test_latest_keeps_a_season_published_before_seasons_were_listed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(publish, "PUBLIC_DIR", tmp_path)
    old = {
        "season": 2025,
        "run_id": "2025-x",
        "data_through": "2025-11-29",
        "districts": ["Sangrur"],
        "generated_at": "2026-10-11T11:55:32+00:00",
        "source_versions": {},
        "demo": False,
    }
    (tmp_path / "latest.json").write_text(json.dumps(old))
    meta = {"generated_at": "2026-10-11T18:00:00+00:00", "source_versions": {}, "demo": False}
    live = {
        "season": 2026,
        "mode": "live",
        "run_id": "2026-y",
        "data_through": "2026-10-09",
        "districts": ["Sangrur"],
        "generated_at": meta["generated_at"],
    }
    merged = publish.latest_with(live, meta)
    assert merged["seasons"]["2025"] == {
        "season": 2025,
        "run_id": "2025-x",
        "data_through": "2025-11-29",
        "districts": ["Sangrur"],
        "generated_at": "2026-10-11T11:55:32+00:00",
        "mode": "replay",
    }
    assert merged["season"] == 2026
