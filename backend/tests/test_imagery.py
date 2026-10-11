"""Imagery crops are stored per season: imagery/{season}/{village_id}/."""

import json
from datetime import date

from typer.testing import CliRunner

from afterpass import cli, imagery
from afterpass import publish as publisher


def _crop(village_id: str, slug: str, pre: str, post: str) -> imagery.Crop:
    return imagery.Crop(
        village_id=village_id,
        name=village_id,
        district=slug.title(),
        slug=slug,
        crs="EPSG:32643",
        bounds=(0.0, 0.0, 1500.0, 1500.0),
        pre=date.fromisoformat(pre),
        post=date.fromisoformat(post),
        village_unrecorded_ha=1.0,
        window_burned_ha=1.0,
        window_unrecorded_ha=1.0,
    )


def test_needed_scenes_are_each_districts_before_and_after_dates() -> None:
    crops = [
        _crop("a", "sangrur", "2025-10-25", "2025-11-02"),
        _crop("b", "sangrur", "2025-10-25", "2025-11-04"),
        _crop("c", "bathinda", "2025-10-30", "2025-11-02"),
    ]
    assert imagery.needed_scenes(crops) == {
        "sangrur": {date(2025, 10, 25), date(2025, 11, 2), date(2025, 11, 4)},
        "bathinda": {date(2025, 10, 30), date(2025, 11, 2)},
    }


def test_render_season_writes_under_the_season_and_drops_stale_villages(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(imagery, "PUBLIC_DIR", tmp_path)
    stale = tmp_path / "imagery" / "2026" / "old-village"
    stale.mkdir(parents=True)
    other_season = tmp_path / "imagery" / "2025" / "old-village"
    other_season.mkdir(parents=True)

    class District:
        name, slug, geometry, geobox = "Sangrur", "sangrur", None, None

    class Replay:
        district = District()

    loaded: list[date] = []
    monkeypatch.setattr(
        imagery,
        "pick_crops",
        lambda replays, top: [_crop("new", "sangrur", "2026-10-02", "2026-10-07")],
    )
    monkeypatch.setattr(
        imagery.sentinel,
        "cache_scene",
        lambda slug, day, items, geobox, geometry: loaded.append(day) or day,
    )
    monkeypatch.setattr(
        imagery.sentinel, "search", lambda g, s, e: {date(2026, 10, 2): [], date(2026, 10, 7): []}
    )

    def fake_render_all(crops, days, scenes, meta, season):
        for crop in crops:
            (imagery.season_dir(season) / crop.village_id).mkdir(parents=True, exist_ok=True)
        return [{"village_id": crop.village_id, "season": season} for crop in crops]

    monkeypatch.setattr(imagery, "render_all", fake_render_all)
    records = imagery.render_season(2026, [Replay()], 20, {})

    assert records == [{"village_id": "new", "season": 2026}]
    assert sorted(loaded) == [date(2026, 10, 2), date(2026, 10, 7)]
    assert (tmp_path / "imagery" / "2026" / "new").is_dir()
    assert not stale.exists()
    # Another season's crops are never touched.
    assert other_season.is_dir()


def test_migrate_moves_old_crops_into_the_season(tmp_path, monkeypatch) -> None:
    for module in (cli, imagery, publisher):
        monkeypatch.setattr(module, "PUBLIC_DIR", tmp_path)
    root = tmp_path / "imagery"
    record = {
        "village_id": "aaaa1111-alpha",
        "name": "Alpha",
        "district": "Sangrur",
        "pre_date": "2025-10-25",
        "post_date": "2025-11-02",
    }
    (root / "aaaa1111-alpha").mkdir(parents=True)
    (root / "aaaa1111-alpha" / "meta.json").write_text(json.dumps(record))
    (root / "aaaa1111-alpha" / "pre_tc.webp").write_bytes(b"webp")
    meta = {"generated_at": "2026-10-11T00:00:00+00:00", "source_versions": {"x": 1}, "demo": False}
    (root / "index.json").write_text(json.dumps({**meta, "items": [record]}))

    result = CliRunner().invoke(cli.app, ["imagery-migrate", "--season", "2025"])

    assert result.exit_code == 0, result.output
    moved = root / "2025" / "aaaa1111-alpha"
    assert (moved / "pre_tc.webp").read_bytes() == b"webp"
    assert json.loads((moved / "meta.json").read_text())["season"] == 2025
    index = json.loads((root / "2025" / "index.json").read_text())
    assert index["items"] == [record]
    assert index["generated_at"] == meta["generated_at"]
    assert not (root / "aaaa1111-alpha").exists()
    assert not (root / "index.json").exists()
    # Running it again finds nothing left to move.
    again = CliRunner().invoke(cli.app, ["imagery-migrate", "--season", "2025"])
    assert again.exit_code == 0 and "Nothing to move" in again.output
