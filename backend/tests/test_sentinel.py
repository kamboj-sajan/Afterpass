from datetime import UTC, datetime

import pystac
from odc.geo.geobox import GeoBox
from shapely.geometry import box, mapping

from afterpass import sentinel, worldcover


def _item(item_id: str, left: float, top: float, code: str = "EPSG:32643") -> pystac.Item:
    item = pystac.Item(
        id=item_id,
        geometry=mapping(box(75, 29, 76, 30)),
        bbox=[75, 29, 76, 30],
        datetime=datetime(2025, 11, 4, 5, 40, tzinfo=UTC),
        properties={"proj:code": code},
    )
    item.add_asset(
        sentinel.BANDS[0],
        pystac.Asset(
            href="https://example.com/B8A.tif",
            extra_fields={
                "proj:transform": [20, 0, left, 0, -20, top],
                "proj:shape": [5490, 5490],
            },
        ),
    )
    return item


def test_utm_zone_from_centroid() -> None:
    assert sentinel.utm_crs(box(75.5, 29.7, 76.2, 30.7)) == "EPSG:32643"
    assert sentinel.utm_crs(box(78.5, 29.7, 79.0, 30.7)) == "EPSG:32644"


def test_worldcover_tiles_for_sangrur() -> None:
    assert worldcover.tile_names((75.557, 29.728, 76.204, 30.695)) == ["N27E075", "N30E075"]
    assert worldcover.tile_names((74.3, 30.7, 75.1, 31.2)) == ["N30E072", "N30E075"]


def test_strips_tile_the_overlap_exactly_once() -> None:
    geobox = GeoBox.from_bbox((566_120, 3_288_880, 628_300, 3_395_980), "EPSG:32643", resolution=20)
    item = _item("T43REP", 499_980, 3_400_020)
    clip = box(*geobox.boundingbox)
    strips = sentinel._strips(item, geobox, clip)

    # The tile covers x up to 609,780 m and y down to 3,290,220 m, so the overlap is a
    # rectangle of the grid: every pixel of it must be planned exactly once.
    columns = round((609_780 - 566_120) / 20)
    rows = round((3_395_980 - 3_290_220) / 20)
    assert sum(s.window.width * s.window.height for s in strips) == columns * rows
    assert [s.rows.start for s in strips] == sorted(s.rows.start for s in strips)
    assert all(a.rows.stop == b.rows.start for a, b in zip(strips, strips[1:], strict=False))
    # Strip edges fall on the 512 px block rows of the source file.
    assert all((s.window.row_off + s.window.height) % 512 == 0 for s in strips[:-1])
    # Source window and destination slices describe the same ground.
    first = strips[0]
    assert 499_980 + first.window.col_off * 20 == 566_120 + first.cols.start * 20
    assert 3_400_020 - first.window.row_off * 20 == 3_395_980 - first.rows.start * 20


def test_strips_skip_rows_outside_the_district() -> None:
    geobox = GeoBox.from_bbox((566_120, 3_288_880, 628_300, 3_395_980), "EPSG:32643", resolution=20)
    item = _item("T43REP", 499_980, 3_400_020)
    clip = box(570_000, 3_300_000, 580_000, 3_320_000)
    strips = sentinel._strips(item, geobox, clip)
    assert 0 < len(strips) <= 3
    assert all(s.window.width == 500 for s in strips)


def test_strips_refuse_other_grids() -> None:
    geobox = GeoBox.from_bbox((566_120, 3_288_880, 628_300, 3_395_980), "EPSG:32643", resolution=20)
    clip = box(*geobox.boundingbox)
    assert sentinel._strips(_item("zone44", 199_980, 3_400_020, "EPSG:32644"), geobox, clip) is None
    assert sentinel._strips(_item("shifted", 499_990, 3_400_020), geobox, clip) is None
