"""AfterPass command-line interface."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from afterpass.config import (
    CACHE_DIR,
    DEMO_DISTRICTS,
    IST,
    PUBLIC_DIR,
    REPORTS_DIR,
    SEASONS,
    VALIDATION_DIR,
    season_window,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)
IST_TZ = ZoneInfo(IST)


def _todo(phase: int) -> None:
    typer.echo(f"Not implemented yet (Phase {phase}).")
    raise typer.Exit(1)


@app.command()
def detect(
    district: str = "Sangrur",
    start: str = "2025-11-01",
    end: str = "2025-11-15",
    recalibrate: bool = typer.Option(False, help="Recompute thresholds even if saved."),
) -> None:
    """Detect burn scars for one district and window, and render the quick-look."""
    # Imported here so `afterpass --help` stays fast.
    from afterpass import burns, calibrate, firms, match, pipeline, quicklook

    first, last = date.fromisoformat(start), date.fromisoformat(end)
    place = pipeline.load_district(district)
    typer.echo(f"{place.name}: grid {place.geobox.shape.x} x {place.geobox.shape.y} at 20 m")
    loaded = pipeline.load_scenes(place, first, last, log=typer.echo)
    if loaded.missing:
        typer.echo(f"Could not download: {', '.join(map(str, loaded.missing))}", err=True)
        raise typer.Exit(1)
    days, scenes = loaded.days, loaded.scenes
    detections = pipeline.load_detections(place, first, last)
    mask = pipeline.detection_mask(place)
    typer.echo(f"FIRMS: {len(detections):,} detections in or within 1 km of the district")

    if recalibrate or not burns.THRESHOLDS_PATH.exists():
        confident = pipeline.in_district(detections[firms.is_confident_viirs(detections)], place)
        samples = calibrate.collect(scenes, mask, confident, place.geobox.affine)
        results = calibrate.grid_search(samples)
        chosen, loosest = calibrate.choose(results), calibrate.most_recall(results)
        best = calibrate.best_scoring(results)
        thresholds = chosen["thresholds"]
        thresholds.save(burns.THRESHOLDS_PATH)
        calibrate.plot(samples, thresholds, REPORTS_DIR / "calibration.png")
        report = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "season": first.year,
            "district": place.name,
            "sentinel2_dates": [scene.day.isoformat() for scene in scenes],
            "firms_window": [
                (first - pipeline.FIRMS_LEAD).isoformat(),
                (last + pipeline.FIRMS_TAIL).isoformat(),
            ],
            "samples": {
                "confident_viirs_detections": len(confident),
                "positive_pixels": len(samples.positives),
                "clear_negative_pixels": len(samples.negatives),
                "background_pixels": len(samples.background),
            },
            "thresholds": json.loads(burns.THRESHOLDS_PATH.read_text()),
            "metrics": calibrate.metrics(samples, thresholds),
            "starting_guess_metrics": calibrate.metrics(samples, burns.Thresholds()),
            "best_scoring_alternative": {
                "thresholds": best["thresholds"].__dict__,
                "metrics": calibrate.metrics(samples, best["thresholds"]),
            },
            "max_recall_alternative": {
                "thresholds": loosest["thresholds"].__dict__,
                "metrics": calibrate.metrics(samples, loosest["thresholds"]),
            },
            "selection": " ".join(calibrate.choose.__doc__.split("\n\n", 1)[1].split()),
            "caveats": calibrate.CAVEATS,
        }
        VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
        (VALIDATION_DIR / f"{first.year}.json").write_text(json.dumps(report, indent=2) + "\n")
        typer.echo(f"Calibrated thresholds: {thresholds}")
    thresholds = burns.Thresholds.load(burns.THRESHOLDS_PATH)

    scars, stats = burns.detect(
        scenes, mask, thresholds, place.geobox.affine, place.crs, place.name
    )
    in_window = (scars["first_detected"] >= start) & (scars["first_detected"] <= end)
    scars = scars[in_window].reset_index(drop=True)
    scars["recorded"] = match.recorded(scars, detections)
    centroids = scars.geometry.centroid.to_crs("EPSG:4326")
    scars["centroid_lon"] = centroids.x.round(5)
    scars["centroid_lat"] = centroids.y.round(5)

    out = CACHE_DIR / "scars" / f"{place.slug}_{start}_{end}.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    scars.to_crs("EPSG:4326").to_file(out, driver="GeoJSON", COORDINATE_PRECISION=6)

    inside = pipeline.in_district(detections, place)
    in_dates = inside[(inside["acq_date"] >= start) & (inside["acq_date"] <= end)]
    quicklook.render(
        REPORTS_DIR / f"quicklook_{place.slug}.png",
        district=place.name,
        slug=place.slug,
        geometry_utm=place.geometry_utm,
        geobox=place.geobox,
        days=days,
        scars=scars,
        recorded=scars["recorded"].to_numpy(),
        detections=inside,
        start=first,
        end=last,
    )

    burned = float(scars["area_ha"].sum())
    recorded_ha = float(scars.loc[scars["recorded"], "area_ha"].sum())
    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "district": place.name,
        "window": [start, end],
        "thresholds": json.loads(burns.THRESHOLDS_PATH.read_text()),
        "sentinel2": stats,
        "firms_in_district_in_window": {
            "total": len(in_dates),
            "by_source": in_dates.groupby("source").size().to_dict(),
        },
        "scars": {
            "count": len(scars),
            "burned_ha": round(burned, 1),
            "recorded_ha": round(recorded_ha, 1),
            "unrecorded_ha": round(burned - recorded_ha, 1),
            "unrecorded_share": round(1 - recorded_ha / burned, 3) if burned else None,
            "cropland_ha": round(float(mask.sum()) * 0.04, 0),
        },
    }
    summary_path = out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    typer.echo(json.dumps(summary["scars"], indent=2))
    typer.echo(f"Wrote {out}, {summary_path} and {REPORTS_DIR / f'quicklook_{place.slug}.png'}")


@app.command()
def fetch(season: int = 2025, districts: str = ",".join(DEMO_DISTRICTS)) -> None:
    """Download and cache the season's Sentinel-2 scenes and FIRMS detections."""
    from afterpass import firms, pipeline

    first, last = season_window(season)
    table = firms.fetch(first - pipeline.FIRMS_TAIL, last + pipeline.FIRMS_TAIL)
    typer.echo(f"FIRMS: {len(table):,} detections in the region, {first} to {last}")
    incomplete = False
    for name in districts.split(","):
        place = pipeline.load_district(name.strip())
        loaded = pipeline.load_scenes(place, first, last, log=typer.echo, tail=timedelta(0))
        typer.echo(f"{place.name}: {len(loaded.scenes)} dates cached")
        if loaded.missing:
            incomplete = True
            typer.echo(f"{place.name}: MISSING {', '.join(map(str, loaded.missing))}", err=True)
    if incomplete:
        raise typer.Exit(1)
    typer.echo("FETCH DONE")


def _echo_summary(replays: list, paths: list) -> None:
    from afterpass import aggregate

    typer.echo(
        f"{'District':<10} {'Burned ha':>11} {'Recorded':>10} {'Unrecorded':>11} "
        f"{'Share':>6} {'Scars':>8} {'FIRMS':>7}"
    )
    for replay in replays:
        row = aggregate.totals(aggregate.with_areas(replay.scars))
        share = "-" if row["unrecorded_share"] is None else f"{row['unrecorded_share']:.0%}"
        typer.echo(
            f"{replay.district.name:<10} {row['burned_ha']:>11,.0f} {row['recorded_ha']:>10,.0f} "
            f"{row['unrecorded_ha']:>11,.0f} {share:>6} {row['scar_count']:>8,} "
            f"{len(replay.detections):>7,}"
        )
    for path in paths:
        typer.echo(f"  {path.stat().st_size / 1e6:8.2f} MB  {path.relative_to(PUBLIC_DIR.parent)}")


@app.command()
def replay(season: int = 2025, districts: str = ",".join(DEMO_DISTRICTS)) -> None:
    """Process a full season: detect, match, locate, aggregate and publish locally."""
    from afterpass import pipeline, places
    from afterpass import publish as publisher

    localities, release = places.load_localities()
    typer.echo(f"Overture {release}: {len(localities):,} localities in the region")
    replays = []
    for name in districts.split(","):
        result = pipeline.replay_district(name.strip(), season, localities, log=typer.echo)
        if result.info["missing_dates"]:
            missing = ", ".join(result.info["missing_dates"])
            typer.echo(f"{result.district.name}: MISSING Sentinel-2 dates {missing}", err=True)
        replays.append(result)
    _echo_summary(replays, publisher.publish_local(replays, season, release))


@app.command()
def live() -> None:
    """Process the current season up to today."""
    _todo(6)


@app.command()
def smoke(
    season: int = 2025,
    districts: str = ",".join(DEMO_DISTRICTS),
    live: bool = typer.Option(False, help="Forecast 48 hours from now instead of a replay."),
    winds: str = typer.Option(
        "historical_forecast", help="Replay winds: historical_forecast or era5."
    ),
    particles_per_day: int = typer.Option(0, help="Particles on the busiest day (0: default)."),
) -> None:
    """Run the smoke model: a season replay (one 48-hour run per day) or a live forecast."""
    import time

    from afterpass import outlook
    from afterpass import smoke as model

    params = model.SmokeParams()
    if particles_per_day:
        params = model.SmokeParams(max_particles_per_day=particles_per_day)
    names = [name.strip() for name in districts.split(",")]
    tic = time.perf_counter()
    if live:
        live_season = max(SEASONS)
        try:
            result = outlook.live(live_season, names, params, log=typer.echo)
        except FileNotFoundError as exc:
            typer.echo(f"{exc}\nA live forecast needs this season's scars from `afterpass live`.")
            raise typer.Exit(1) from None
    else:
        result = outlook.replay(season, names, winds, params, log=typer.echo)

    typer.echo(f"Winds: {result.wind_source}")
    typer.echo(f"Particles: {result.particles:,} at {result.ha_each:.3f} ha each")
    typer.echo(f"Normaliser (SAI 100): {result.normaliser['p95_raw']:.4g} raw units")
    typer.echo(
        f"{'Run':<16} {'Peak SAI':>8} {'Level':>10} {'Delhi mean':>10} {'Peak (IST)':<12} "
        f"{'Trips':>7} {'MB':>6}"
    )
    for run in result.runs:
        peak = datetime.fromtimestamp(run["delhi_mean_peak_hour"], IST_TZ)
        typer.echo(
            f"{run['run_id']:<16} {run['peak_sai']:>8} {run['peak_level']:>10} "
            f"{run['delhi_mean_peak']:>10.1f} {peak:%d %b %H:%M} "
            f"{run['trips']:>7,} {run['trips_mb']:>6.2f}"
        )
    typer.echo(f"Done in {(time.perf_counter() - tic) / 60:.1f} min")


@app.command()
def pm25(season: int = 2025, districts: str = ",".join(DEMO_DISTRICTS)) -> None:
    """Compare the season's daily Delhi smoke index with observed PM2.5 from OpenAQ."""
    from afterpass import outlook, pipeline, places
    from afterpass import pm25 as observed
    from afterpass import publish as publisher

    names = [name.strip() for name in districts.split(",")]
    try:
        sai = outlook.daily_delhi_sai(season)
    except FileNotFoundError:
        typer.echo(f"No smoke replay for {season}. Run `afterpass smoke` first.")
        raise typer.Exit(1) from None
    sai.index = [day.isoformat() for day in sai.index]
    daily = observed.fetch_daily(season, log=typer.echo)
    block = observed.report(season, sai, daily, names)
    report_path = VALIDATION_DIR / f"{season}.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    report["pm25"] = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), **block}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    chart = REPORTS_DIR / "pm25_vs_sai.png"
    observed.plot(block, season, chart)

    replays = [pipeline.load_replay(name, season) for name in names]
    _, release = places.load_localities()
    publisher.publish_validation(season, publisher.metadata(replays, release))
    summary = {key: block[key] for key in ("stations", "station_days", "days", "pearson")}
    typer.echo(json.dumps(summary | {"spearman": block["spearman"]}, indent=2))
    typer.echo(f"Wrote {report_path}, {chart} and the public validation file")


def _load_season(season: int, districts: str):
    """Cached replays plus the scenes and STAC items behind them, for imagery and QA."""
    from afterpass import pipeline

    first, last = season_window(season)
    replays = [pipeline.load_replay(name.strip(), season) for name in districts.split(",")]
    days, scenes = {}, {}
    for replay in replays:
        loaded = pipeline.load_scenes(replay.district, first, last, tail=timedelta(0))
        days[replay.district.slug] = loaded.days
        scenes[replay.district.slug] = loaded.scenes
    return replays, days, scenes


@app.command()
def imagery(top: int = 20, season: int = 2025, districts: str = ",".join(DEMO_DISTRICTS)) -> None:
    """Render before/after crops for the villages with the most unrecorded burning."""
    from afterpass import imagery as crops
    from afterpass import places
    from afterpass import publish as publisher

    replays, days, scenes = _load_season(season, districts)
    _, release = places.load_localities()
    chosen = crops.pick_crops(replays, top)
    by_day = {slug: {scene.day: scene for scene in items} for slug, items in scenes.items()}
    meta = publisher.metadata(replays, release)
    records = crops.render_all(chosen, days, by_day, meta)
    # Crops from an earlier run for villages no longer in the top list would show stale numbers.
    keep = {record["village_id"] for record in records}
    for folder in (PUBLIC_DIR / "imagery").iterdir():
        if folder.is_dir() and folder.name not in keep:
            shutil.rmtree(folder)
    publisher.write_imagery_index(meta)
    crops.contact_sheet(records[:5], REPORTS_DIR / "imagery_pairs.png")
    for record in records:
        typer.echo(
            f"{record['name']:<24} {record['district']:<10} {record['pre_date']} -> "
            f"{record['post_date']}  {record['village_unrecorded_ha']:>8,.0f} ha unrecorded"
        )
    typer.echo(f"Wrote {len(records)} villages to {PUBLIC_DIR / 'imagery'}")


@app.command()
def validate(
    labels: str = typer.Option("", help="Labels exported from the QA sheet. Omit to build it."),
    season: int = 2025,
    districts: str = ",".join(DEMO_DISTRICTS),
) -> None:
    """Build the visual QA sheet, or turn its exported labels into precision."""
    import numpy as np

    from afterpass import pipeline
    from afterpass import validate as qa

    items_path = VALIDATION_DIR / f"qa_items_{season}.json"
    report_path = VALIDATION_DIR / f"{season}.json"
    if labels:
        items = json.loads(items_path.read_text())["items"]
        result = qa.score(items, json.loads(Path(labels).read_text())["labels"])
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        report["visual_qa"] = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            **result,
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        typer.echo(json.dumps(result, indent=2))
        return

    replays, days, scenes = _load_season(season, districts)
    rng = np.random.default_rng(qa.SEED)
    masks = {r.district.slug: pipeline.detection_mask(r.district) for r in replays}
    items = qa.sample_scars(replays, rng, qa.QA_SCARS)
    items += qa.sample_points(replays, masks, scenes, rng, qa.QA_POINTS)
    # Mixed order, so position does not reveal which items are detections.
    items = [items[i] for i in rng.permutation(len(items))]
    qa.build_sheet(items, days, season, REPORTS_DIR / "qa_sheet.html", items_path)
    typer.echo(f"Wrote {REPORTS_DIR / 'qa_sheet.html'} with {len(items)} items to label")


@app.command()
def publish(
    target: str = "local", season: int = 2025, districts: str = ",".join(DEMO_DISTRICTS)
) -> None:
    """Rewrite the data-contract files in data/public from the cached replay."""
    from afterpass import pipeline, places
    from afterpass import publish as publisher

    if target != "local":
        typer.echo("Only --target local works so far; S3 publishing arrives with the deploy.")
        raise typer.Exit(1)
    _, release = places.load_localities()
    replays = [pipeline.load_replay(name.strip(), season) for name in districts.split(",")]
    _echo_summary(replays, publisher.publish_local(replays, season, release))


if __name__ == "__main__":
    app()
