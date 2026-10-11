"""AfterPass command-line interface."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import typer

from afterpass.config import CACHE_DIR, REPORTS_DIR, VALIDATION_DIR

app = typer.Typer(no_args_is_help=True, add_completion=False)


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
    days, scenes = pipeline.load_scenes(place, first, last, log=typer.echo)
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
def replay(season: int = 2025, districts: str = "Sangrur,Bathinda,Firozpur") -> None:
    """Process a full past season."""
    _todo(2)


@app.command()
def live() -> None:
    """Process the current season up to today."""
    _todo(6)


@app.command()
def smoke() -> None:
    """Run the 48-hour smoke forecast."""
    _todo(4)


@app.command()
def imagery(top: int = 20) -> None:
    """Render before/after crops for the top villages."""
    _todo(2)


@app.command()
def validate() -> None:
    """Compute validation metrics."""
    _todo(2)


@app.command()
def publish(target: str = "local") -> None:
    """Publish data-contract files to data/public or S3."""
    _todo(2)


if __name__ == "__main__":
    app()
