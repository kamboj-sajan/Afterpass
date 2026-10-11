"""The agent's tools (brief §10.2): pure functions over the public data files.

Each returns `{"data": ..., "ui_actions": [...]}`. `data` is what the model may quote;
`ui_actions` are instructions for the map (brief §10.3) in the shapes the app's store runs.
A tool that cannot answer returns `data` with an `error` and what to try instead.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

from agent import data, gazetteer

IST = timezone(timedelta(hours=5, minutes=30))
SOURCES = "Sentinel-2 burn scars matched with NASA FIRMS detections"
LEVELS = (("Low", 0), ("Moderate", 25), ("High", 50), ("Very high", 75))
OFFICIAL_AQI = "CPCB's SAMEER app, https://airquality.cpcb.gov.in/AQI_India/"
# iFOREST's finding as the project brief cites it; not a number from this pipeline.
IFOREST = {
    "finding": "An iFOREST study using 15-minute geostationary data found that most large farm "
    "fires in Punjab in 2024 and 2025 started after 3 PM.",
    "url": "https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-"
    "delhi-air-pollution-underestimated-report",
}
METHOD_TOPICS = (
    "detection",
    "why_official_counts_miss_fires",
    "matching",
    "smoke",
    "validation",
    "limitations",
    "ethics",
    "data_sources",
)


def _result(payload: dict, actions: list[dict] | None = None) -> dict:
    return {"data": payload, "ui_actions": actions or []}


def _error(message: str, **extra) -> dict:
    return _result({"error": message, **extra})


def _season(season: int) -> tuple[dict, dict] | None:
    try:
        return data.load(f"seasons/{season}/summary.json"), data.load("latest.json")
    except data.DataError:
        return None


def _no_season(season: int) -> dict:
    return _error(f"No data is published for the {season} season.", published_seasons=[2025])


def _window(summary: dict, latest: dict) -> dict:
    return {
        "season": summary["season"],
        "from": summary["window"][0],
        "to": summary["window"][1],
        "data_through": latest.get("data_through"),
        "sources": SOURCES,
    }


def _pct(share: float | None) -> float | None:
    return None if share is None else round(share * 100, 1)


def _district(name: str, summary: dict) -> dict | None:
    names = [row["district"] for row in summary["districts"]]
    found = gazetteer.find_district(name, names)
    return next((row for row in summary["districts"] if row["district"] == found), None)


def _unknown_district(name: str, summary: dict) -> dict:
    return _error(
        f"'{name}' is not one of the districts with published data.",
        published_districts=[row["district"] for row in summary["districts"]],
    )


def _district_centre(season: int, name: str) -> tuple[float, float] | None:
    outlines = data.load(f"seasons/{season}/districts.geojson")
    for feature in outlines["features"]:
        if feature["properties"]["district"] != name:
            continue
        geometry = feature["geometry"]
        rings = (
            [geometry["coordinates"][0]]
            if geometry["type"] == "Polygon"
            else [polygon[0] for polygon in geometry["coordinates"]]
        )
        lons = [point[0] for ring in rings for point in ring]
        lats = [point[1] for ring in rings for point in ring]
        return round((min(lons) + max(lons)) / 2, 4), round((min(lats) + max(lats)) / 2, 4)
    return None


def _show_district(season: int, name: str) -> list[dict]:
    actions: list[dict] = [{"type": "highlight_district", "name": name}]
    centre = _district_centre(season, name)
    if centre is not None:
        actions.append({"type": "fly_to", "lon": centre[0], "lat": centre[1], "zoom": 9.2})
    return actions


def _totals(row: dict) -> dict:
    return {
        "burned_ha": row["burned_ha"],
        "in_official_counts_ha": row["recorded_ha"],
        "in_official_counts_pct": _pct(row["recorded_ha"] / row["burned_ha"])
        if row["burned_ha"]
        else None,
        "not_in_official_counts_ha": row["unrecorded_ha"],
        "not_in_official_counts_pct": _pct(row["unrecorded_share"]),
        "burn_scars": row["scar_count"],
    }


def season_overview(season: int = 2025, district: str | None = None) -> dict:
    """Totals for a season, for all published districts or one of them."""
    loaded = _season(season)
    if loaded is None:
        return _no_season(season)
    summary, latest = loaded
    window = _window(summary, latest)
    note = "Burned area is a lower bound; compare hectares, not counts of fire pixels."
    if district:
        row = _district(district, summary)
        if row is None:
            return _unknown_district(district, summary)
        payload = {
            "data_window": window,
            "district": row["district"],
            "state": row["state"],
            **_totals(row),
            "official_fire_detections": row["firms"]["firms_count"],
            "cropland_ha": row["cropland_ha"],
            "note": note,
        }
        return _result(payload, _show_district(season, row["district"]))
    payload = {
        "data_window": window,
        "scope": f"Only the {len(summary['districts'])} districts processed so far: "
        + ", ".join(row["district"] for row in summary["districts"])
        + ". Not all of Punjab or Haryana.",
        **_totals(summary["totals"]),
        "official_fire_detections": summary["firms"]["firms_count"],
        "districts": [
            {"district": row["district"], **_totals(row)} for row in summary["districts"]
        ],
        "note": note,
    }
    return _result(payload, [{"type": "show_layer", "id": "burns"}])


def top_unrecorded_villages(
    district: str | None = None, season: int = 2025, n: int = 10, week: str | None = None
) -> dict:
    """Villages ranked by burned area that is not in official counts."""
    loaded = _season(season)
    if loaded is None:
        return _no_season(season)
    summary, latest = loaded
    villages = data.load(f"seasons/{season}/villages.json")["items"]
    chosen = None
    if district:
        row = _district(district, summary)
        if row is None:
            return _unknown_district(district, summary)
        chosen = row["district"]
        villages = [village for village in villages if village["district"] == chosen]
    if week is not None and not re.fullmatch(r"\d{4}-W\d{2}", week):
        return _error("Give the week as an ISO week such as 2025-W45.")
    try:
        imagery = {item["village_id"] for item in data.load("imagery/index.json")["items"]}
    except data.DataError:
        imagery = set()

    rows = []
    for village in villages:
        burned, missing = village["burned_ha"], village["unrecorded_ha"]
        if week is not None:
            in_week = next((w for w in village["weekly"] if w["week"] == week), None)
            if in_week is None:
                continue
            burned, missing = in_week["burned_ha"], in_week["unrecorded_ha"]
        rows.append((missing, burned, village))
    rows.sort(key=lambda row: (-row[0], row[2]["id"]))
    n = max(1, min(int(n), 20))
    ranked = [
        {
            "rank": rank,
            "village": village["name"],
            "district": village["district"],
            "not_in_official_counts_ha": missing,
            "burned_ha": burned,
            "not_in_official_counts_pct": _pct(missing / burned) if burned else None,
            "before_after_imagery": village["id"] in imagery,
        }
        for rank, (missing, burned, village) in enumerate(rows[:n], 1)
    ]
    payload = {
        "data_window": _window(summary, latest) | ({"week": week} if week else {}),
        "district": chosen or "all published districts",
        "villages": ranked,
        "note": "A village is the named place nearest each burn scar (within 3 km). "
        "Use this to decide where to send help first.",
    }
    actions: list[dict] = _show_district(season, chosen) if chosen else []
    if rows:
        top = rows[0][2]
        actions = [action for action in actions if action["type"] != "fly_to"]
        actions.append({"type": "fly_to", "lon": top["lon"], "lat": top["lat"], "zoom": 11.5})
        actions.append({"type": "highlight_village", "id": top["id"]})
        if top["id"] in imagery:
            actions.append({"type": "open_imagery", "village_id": top["id"]})
    return _result(payload, actions)


def district_trend(district: str, season: int = 2025) -> dict:
    """Week by week: burned area in a district, split by whether official counts have it."""
    loaded = _season(season)
    if loaded is None:
        return _no_season(season)
    summary, latest = loaded
    row = _district(district, summary)
    if row is None:
        return _unknown_district(district, summary)
    weeks = [
        {
            "week": week["week"],
            "from": _week_start(week["week"]).isoformat(),
            "to": (_week_start(week["week"]) + timedelta(days=6)).isoformat(),
            "burned_ha": week["burned_ha"],
            "in_official_counts_ha": week["recorded_ha"],
            "not_in_official_counts_ha": week["unrecorded_ha"],
            "not_in_official_counts_pct": _pct(week["unrecorded_share"]),
        }
        for week in row["by_week"]
    ]
    peak = max(weeks, key=lambda week: week["burned_ha"]) if weeks else None
    payload = {
        "data_window": _window(summary, latest),
        "district": row["district"],
        "weeks": weeks,
        "peak_week": peak,
        "note": "A scar is dated by the Sentinel-2 pass that first showed it, so burning can "
        "appear a few days late.",
    }
    actions = _show_district(season, row["district"]) + [{"type": "show_layer", "id": "burns"}]
    return _result(payload, actions)


def _week_start(week: str):
    year, number = int(week[:4]), int(week[-2:])
    return datetime.fromisocalendar(year, number, 1).date()


def official_detection_times(season: int = 2025) -> dict:
    """When in the day official satellites detected fires (IST), which explains the blind spot."""
    loaded = _season(season)
    if loaded is None:
        return _no_season(season)
    summary, latest = loaded
    hours = summary["firms"]["by_ist_hour"]
    total = sum(hours)
    midday = sum(hours[12:16])
    payload = {
        "data_window": _window(summary, latest),
        "official_fire_detections": total,
        "detections_by_ist_hour": {f"{hour:02d}:00": count for hour, count in enumerate(hours)},
        "detections_12_to_16_ist": midday,
        "detections_12_to_16_ist_pct": _pct(midday / total) if total else None,
        "detections_16_to_24_ist": sum(hours[16:]),
        "satellite_pass": "The polar-orbiting satellites behind the official counts (VIIRS, "
        "MODIS) pass over Punjab at about 13:30 IST and again after midnight.",
        "why_it_matters": "A fire lit after the afternoon pass is out before the next pass, so "
        "it never becomes a detection. Its burn scar stays visible to Sentinel-2 for days.",
        "cited_study": IFOREST,
    }
    return _result(payload, [{"type": "show_layer", "id": "official"}])


def _level(value: float) -> str:
    return [name for name, lowest in LEVELS if value >= lowest][-1]


def _ist(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).astimezone(IST).strftime("%a %d %b %Y, %H:%M")


def _peak(hours: list[int], sai: list[int]) -> dict | None:
    """The stretch around the highest hour at or above half of it (and at least Moderate)."""
    if not sai or max(sai) < LEVELS[1][1]:
        return None
    top = sai.index(max(sai))
    threshold = max(LEVELS[1][1], sai[top] / 2)
    first = last = top
    while first > 0 and sai[first - 1] >= threshold:
        first -= 1
    while last < len(sai) - 1 and sai[last + 1] >= threshold:
        last += 1
    return {
        "from_ist": _ist(hours[first]),
        "to_ist": _ist(hours[last] + 3600),
        "highest_index": sai[top],
        "highest_at_ist": _ist(hours[top]),
        "level": _level(sai[top]),
        "first_hour": first,
    }


def _high_windows(hours: list[int], sai: list[int]) -> list[dict]:
    """Every unbroken stretch of hours at High or above, in order."""
    windows: list[dict] = []
    start = None
    for index, value in enumerate([*sai, 0]):
        if value >= LEVELS[2][1] and start is None:
            start = index
        elif value < LEVELS[2][1] and start is not None:
            top = max(sai[start:index])
            windows.append(
                {
                    "from_ist": _ist(hours[start]),
                    "to_ist": _ist(hours[index - 1] + 3600),
                    "hours": index - start,
                    "highest_index": top,
                    "level": _level(top),
                }
            )
            start = None
    return windows


def smoke_outlook(place: str, hours: int = 48, start_date: str | None = None) -> dict:
    """The hourly Smoke Arrival Index for a Delhi locality over a 48-hour model run."""
    try:
        runs = data.load("smoke/index.json")["runs"]
    except data.DataError:
        return _error("No smoke outlook has been published yet.")
    if not runs:
        return _error("No smoke outlook has been published yet.")
    live = [run for run in runs if run["kind"] == "live"]
    replay = sorted((run for run in runs if run["kind"] == "replay"), key=lambda run: run["start"])
    if start_date is not None:
        run = next((r for r in replay if r["run_id"] == start_date), None)
        if run is None:
            return _error(
                f"No smoke run starts on {start_date}.",
                runs_available={"from": replay[0]["run_id"], "to": replay[-1]["run_id"]},
            )
        why = "the run starting on the date asked for"
    elif live:
        run = max(live, key=lambda r: r["start"])
        why = "the latest forecast"
    else:
        run = max(replay, key=lambda r: (r["delhi_mean_peak"], -r["start"]))
        why = (
            "no live forecast is published; this is the 2025 replay's 48 hours with the most smoke"
        )

    base = f"smoke/{run['run_id']}"
    localities = data.load(f"{base}/localities.json")["items"]
    found, others = gazetteer.find_locality(place, localities)
    if found is None:
        return _error(
            f"'{place}' was not found among Delhi localities. Try the English spelling.",
            similar_names=others,
        )
    sai_file = data.load(f"{base}/delhi_sai_h3r7.json")
    count = max(1, min(int(hours), run["hours"]))
    times, series = sai_file["hours"][:count], found["sai"][:count]
    peak = _peak(times, series)
    payload = {
        "place": found["name"],
        "place_hindi": found.get("name_hi"),
        "delhi_district": found["district"].strip(),
        "run": {
            "kind": "forecast" if run["kind"] == "live" else "replay of a past season",
            "from_ist": _ist(times[0]),
            "to_ist": _ist(times[-1] + 3600),
            "chosen_because": why,
        },
        "index_scale": "Smoke Arrival Index, 0-100, relative; 100 is the 95th percentile of the "
        "2025 season. Low 0-24, Moderate 25-49, High 50-74, Very high 75-100. The index has no "
        "unit; do not write it as a percentage.",
        "hourly_index_from_start": series,
        "highest_index": max(series),
        "peak_window": peak,
        "hours_at_high_or_above": sum(1 for value in series if value >= LEVELS[2][1]),
        "hours_at_each_level": {
            name: sum(1 for value in series if _level(value) == name) for name, _ in LEVELS
        },
        "windows_at_high_or_above": _high_windows(times, series),
        "only_includes_smoke_from": str(sai_file["source_versions"].get("burn_sources", ""))
        + ". Smoke from other districts and other pollution are not in the index.",
        "caveat": "A relative index from a simplified transport model. Not a PM2.5 forecast and "
        "not medical advice. Other pollution sources are not included.",
        "for_health_decisions": OFFICIAL_AQI,
        "other_places_with_similar_names": others,
    }
    from_hour = 0 if peak is None else max(0, peak["first_hour"] - 3)
    if peak is not None:
        del peak["first_hour"]
    actions = [
        {"type": "play_smoke", "run_id": run["run_id"], "from_hour": from_hour},
        {"type": "highlight_locality", "id": found["id"]},
        {"type": "fly_to", "lon": found["lon"], "lat": found["lat"], "zoom": 10.5},
    ]
    return _result(payload, actions)


def _sections(text: str) -> dict[str, str]:
    """`## Heading {#topic}` sections of the method document, keyed by topic."""
    sections: dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        tag = re.search(r"\{#([a-z_]+)\}", heading)
        if tag:
            sections[tag.group(1)] = body.strip()
    return sections


def _validation_numbers(season: int) -> dict:
    try:
        report = data.load(f"validation/{season}.json")
    except data.DataError:
        return {}
    out: dict = {
        "calibration": {
            "district": report.get("district"),
            "confident_official_detections_used": report["samples"]["confident_viirs_detections"],
            "thresholds": report["thresholds"],
            "share_of_official_detections_also_flagged_pct": _pct(
                report["metrics"]["recall_on_firms_positives"]
            ),
            "false_flag_rate_on_clearly_unburned_pct": _pct(
                report["metrics"]["fpr_on_clear_negatives"]
            ),
        }
    }
    if "visual_qa" in report:
        out["visual_check"] = report["visual_qa"]
    else:
        out["visual_check"] = "Not done yet: the hand-labelled sample has not been scored."
    if "pm25" in report:
        block = report["pm25"]
        out["pm25_comparison"] = {
            "days": block["days"],
            "monitors": block["stations"],
            "pearson_r": None if block["pearson"] is None else block["pearson"]["r"],
            "spearman_rho": None if block["spearman"] is None else block["spearman"]["rho"],
            "source": block["source"],
            "caveats": block["caveats"],
        }
    return out


def method_and_limits(topic: str) -> dict:
    """A short section of the method document, with validation numbers where they apply."""
    try:
        sections = _sections(data.method_text())
    except data.DataError as exc:
        return _error(str(exc))
    key = topic.strip().lower().replace(" ", "_").replace("-", "_")
    if key not in sections:
        return _error(f"No method section called '{topic}'.", topics=sorted(sections))
    payload: dict = {
        "topic": key,
        "text": sections[key],
        "document": "docs/METHOD.md",
        "applies_to": "The method is the same for every season. Results are published for the "
        "2025 season (1 Oct to 30 Nov 2025).",
    }
    if key != "limitations" and "limitations" in sections:
        payload["limitations"] = sections["limitations"]
    if key == "validation":
        payload["numbers"] = _validation_numbers(2025)
    return _result(payload)
