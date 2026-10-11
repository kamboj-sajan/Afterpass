"""Thin Lambda handlers for the live pipeline (brief §11.2). Each one calls `afterpass.*`.

The steps share nothing but the data bucket: every handler pulls the cached files it needs,
does its work in /tmp, and pushes what it made. The state machine passes only small summaries.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime

import boto3

log = logging.getLogger("afterpass.pipeline")
log.setLevel(logging.INFO)

REFERENCE = ["boundaries/districts_pb_hr_dl.geojson", "overture", "worldcover"]


def _start() -> None:
    """Put the FIRMS key where the settings look for it. It is read from SSM, never logged."""
    if "FIRMS_MAP_KEY" not in os.environ:
        ssm = boto3.client("ssm")
        name = os.environ["FIRMS_KEY_PARAMETER"]
        value = ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        os.environ["FIRMS_MAP_KEY"] = value


def _season() -> int:
    from afterpass.config import SEASONS

    return max(SEASONS)


def _districts(event: dict) -> list[str]:
    from afterpass.config import DEMO_DISTRICTS

    return list(event.get("districts") or DEMO_DISTRICTS)


def fetch_firms(event: dict, _context: object) -> dict:
    """Download the season's official detections for the region."""
    _start()
    from afterpass import firms, pipeline, workdir
    from afterpass.config import season_window

    season = _season()
    first, last = season_window(season)
    workdir.pull(["firms"], log.info)
    table = firms.fetch(first - pipeline.S2_LEAD - pipeline.FIRMS_TAIL, last + pipeline.FIRMS_TAIL)
    workdir.push(["firms"], log.info)
    return {
        "season": season,
        "window": [first.isoformat(), last.isoformat()],
        "detections": len(table),
    }


def find_scenes(event: dict, _context: object) -> dict:
    """List the Sentinel-2 dates each district needs, for the Map state to fan out over."""
    from afterpass import pipeline, sentinel, workdir
    from afterpass.config import season_window

    season = _season()
    first, last = season_window(season)
    workdir.pull(REFERENCE, log.info)
    districts = []
    for name in _districts(event):
        place = pipeline.load_district(name)
        days = sentinel.search(place.geometry, first - pipeline.S2_LEAD, last)
        districts.append({"name": name, "dates": [day.isoformat() for day in sorted(days)]})
    return {"season": season, "districts": districts}


def detect_burns(event: dict, _context: object) -> dict:
    """One district: cache its scenes, detect and match its scars, and store the result."""
    _start()
    from afterpass import pipeline, places, workdir

    season = _season()
    name = event["name"]
    slug = name.lower().replace(" ", "_")
    workdir.pull([*REFERENCE, "firms", f"s2/{slug}"], log.info)
    localities, _ = places.load_localities()
    result = pipeline.replay_district(name, season, localities, log=log.info)
    workdir.push([f"s2/{slug}", f"replay/{season}", "firms", "worldcover"], log.info)
    scars = result.scars
    return {
        "name": name,
        "scars": int(len(scars)),
        "burned_ha": round(float(scars["area_ha"].sum()), 1),
        "in_official_counts_ha": round(float(scars.loc[scars["recorded"], "area_ha"].sum()), 1),
        "official_detections": int(len(result.detections)),
        "missing_dates": result.info["missing_dates"],
    }


def match_aggregate(event: dict, _context: object) -> dict:
    """Aggregate the districts' scars, write the season's public files and the daily stats."""
    from afterpass import pipeline, places, workdir
    from afterpass import publish as publisher
    from afterpass.config import PUBLIC_DIR

    season = _season()
    names = _districts(event)
    workdir.pull([*REFERENCE, f"replay/{season}"], log.info)
    workdir.pull_public(["latest.json"])
    _, release = places.load_localities()
    replays = [pipeline.load_replay(name, season) for name in names]
    publisher.publish_local(replays, season, release)
    # Only this season's files and the season list: imagery and smoke are published elsewhere.
    files = [p for p in (PUBLIC_DIR / "seasons" / str(season)).rglob("*") if p.is_file()]
    sent = workdir.push_public([*files, PUBLIC_DIR / "latest.json"])

    summary = json.loads((PUBLIC_DIR / "seasons" / str(season) / "summary.json").read_text())
    table = boto3.resource("dynamodb").Table(os.environ["STATS_TABLE"])
    with table.batch_writer() as batch:
        for district in summary["districts"]:
            for day in district["by_day"]:
                batch.put_item(
                    Item={
                        "pk": f"district#{district['district']}",
                        "sk": f"{season}#{day['first_detected']}",
                        "burned_ha": str(day["burned_ha"]),
                        "in_official_counts_ha": str(day["recorded_ha"]),
                        "not_in_official_counts_ha": str(day["unrecorded_ha"]),
                        "scars": day["scar_count"],
                    }
                )
    return {"season": season, "files_published": sent, "totals": summary["totals"]}


def smoke_forecast(event: dict, _context: object) -> dict:
    """The 48-hour smoke forecast from the season's scars and today's detections."""
    _start()
    from afterpass import outlook, smoke, workdir
    from afterpass.config import PUBLIC_DIR

    season = _season()
    names = _districts(event)
    workdir.pull([*REFERENCE, f"replay/{season}", "replay/2025", "smoke", "firms"], log.info)
    # The index is rewritten with the new run. Runs whose folders exist locally are kept in it,
    # so the replay's runs get empty folders here; older forecasts do not, and drop out.
    workdir.pull_public(["smoke/index.json"])
    index_path = PUBLIC_DIR / "smoke" / "index.json"
    earlier = json.loads(index_path.read_text())["runs"] if index_path.exists() else []
    for run in earlier:
        if run["kind"] == "replay":
            (PUBLIC_DIR / "smoke" / run["run_id"]).mkdir(parents=True, exist_ok=True)

    outcome = outlook.live(season, names, smoke.SmokeParams(), log=log.info)
    made = [run["run_id"] for run in outcome.runs]
    files = [index_path]
    for run_id in made:
        files += [p for p in (PUBLIC_DIR / "smoke" / run_id).rglob("*") if p.is_file()]
    workdir.push_public(files)
    workdir.push(["firms"], log.info)

    # Forecasts that are no longer in the index are removed from the bucket.
    bucket = boto3.resource("s3").Bucket(workdir.bucket_name())
    for run in earlier:
        if run["kind"] == "live" and run["run_id"] not in made:
            bucket.objects.filter(Prefix=f"public/smoke/{run['run_id']}/").delete()
    return {
        "runs": [
            {k: run[k] for k in ("run_id", "peak_sai", "peak_level", "trips")}
            for run in outcome.runs
        ]
    }


def render_imagery(event: dict, _context: object) -> dict:
    """Before and after crops for the season's top villages, under imagery/{season}/.

    Only the Sentinel-2 dates the crops are drawn from are pulled from the cache; the burn
    detection step pushed every date it used.
    """
    from afterpass import imagery, pipeline, places, workdir
    from afterpass import publish as publisher

    season = _season()
    names = _districts(event)
    workdir.pull([*REFERENCE, f"replay/{season}"], log.info)
    replays = [pipeline.load_replay(name, season) for name in names]
    needed = imagery.needed_scenes(imagery.pick_crops(replays, imagery.TOP_VILLAGES))
    workdir.pull(
        [f"s2/{slug}/{day.isoformat()}.tif" for slug, days in needed.items() for day in days],
        log.info,
    )
    _, release = places.load_localities()
    meta = publisher.metadata(replays, release)
    records = imagery.render_season(season, replays, imagery.TOP_VILLAGES, meta, log=log.info)
    publisher.write_imagery_index(meta, season)  # inside the season folder
    folder = imagery.season_dir(season)
    sent = workdir.push_public(p for p in folder.rglob("*") if p.is_file())
    # Folders of villages that left the top list are removed from the bucket too.
    keep = {record["village_id"] for record in records}
    bucket = boto3.resource("s3").Bucket(workdir.bucket_name())
    prefix = f"public/imagery/{season}/"
    for obj in bucket.objects.filter(Prefix=prefix):
        village_id, _, rest = obj.key.removeprefix(prefix).partition("/")
        if rest and village_id not in keep:
            obj.delete()
    return {"season": season, "rendered": len(records), "files_published": sent}


def publish(event: dict, _context: object) -> dict:
    """Make the new files visible at once instead of after the five-minute cache."""
    cloudfront = boto3.client("cloudfront")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    cloudfront.create_invalidation(
        DistributionId=os.environ["DISTRIBUTION_ID"],
        InvalidationBatch={
            "Paths": {
                "Quantity": 4,
                "Items": ["/latest.json", "/smoke/index.json", "/seasons/*", "/imagery/*"],
            },
            "CallerReference": f"pipeline-{stamp}",
        },
    )
    return {"published_at": stamp}


def publish_alerts(event: dict, _context: object) -> dict:
    """Email the people who asked, for each part of Delhi whose forecast reaches High."""
    from afterpass import alerts, workdir
    from afterpass.config import PUBLIC_DIR

    shutil.rmtree(PUBLIC_DIR / "smoke", ignore_errors=True)
    workdir.pull_public(["smoke/index.json"])
    index = json.loads((PUBLIC_DIR / "smoke" / "index.json").read_text())
    live = [run for run in index["runs"] if run["kind"] == "live"]
    if not live:
        return {"sent": 0, "reason": "no forecast is published"}
    run = max(live, key=lambda item: item["start"])
    workdir.pull_public([f"smoke/{run['run_id']}/localities.json"])
    localities = json.loads((PUBLIC_DIR / "smoke" / run["run_id"] / "localities.json").read_text())
    messages = alerts.messages(run, localities["items"], os.environ["WEB_URL"])
    sns = boto3.client("sns")
    for message in messages:
        sns.publish(
            TopicArn=os.environ["ALERT_TOPIC"],
            Subject=message["subject"],
            Message=message["body"],
            MessageAttributes={"zone": {"DataType": "String", "StringValue": message["zone"]}},
        )
    return {"sent": len(messages), "zones": [message["zone"] for message in messages]}
