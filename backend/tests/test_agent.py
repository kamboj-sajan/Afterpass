import json

import pytest

from agent import data, gazetteer, grounding, handler, tools

HOUR = 3600
RUN_START = 1762367400  # 2025-11-06 00:00 IST


def _write(root, path: str, payload: dict) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload, ensure_ascii=False))


def _district(name: str, burned: float, missing: float) -> dict:
    return {
        "district": name,
        "state": "Punjab",
        "cropland_ha": 1000.0,
        "burned_ha": burned,
        "recorded_ha": burned - missing,
        "unrecorded_ha": missing,
        "unrecorded_share": round(missing / burned, 3),
        "scar_count": 10,
        "firms": {"firms_count": 4},
        "by_week": [
            {
                "week": "2025-W44",
                "burned_ha": 40.0,
                "recorded_ha": 30.0,
                "unrecorded_ha": 10.0,
                "unrecorded_share": 0.25,
                "scar_count": 4,
            },
            {
                "week": "2025-W45",
                "burned_ha": burned - 40.0,
                "recorded_ha": burned - missing - 30.0,
                "unrecorded_ha": missing - 10.0,
                "unrecorded_share": 0.5,
                "scar_count": 6,
            },
        ],
    }


@pytest.fixture
def public(tmp_path, monkeypatch):
    """A tiny published data folder and method document, and the agent pointed at them."""
    hours = [0, 15, 27, 3, 1, 0, 0, 0, 0, 1, 0, 0, 312, 2000, 1263, 755] + [0] * 8
    _write(tmp_path, "latest.json", {"season": 2025, "data_through": "2025-11-29"})
    _write(
        tmp_path,
        "seasons/2025/summary.json",
        {
            "season": 2025,
            "window": ["2025-10-01", "2025-11-30"],
            "totals": {
                "burned_ha": 300.0,
                "recorded_ha": 120.0,
                "unrecorded_ha": 180.0,
                "unrecorded_share": 0.6,
                "scar_count": 20,
            },
            "firms": {"firms_count": sum(hours), "by_ist_hour": hours},
            "districts": [_district("Sangrur", 200.0, 100.0), _district("Bathinda", 100.0, 80.0)],
        },
    )
    _write(
        tmp_path,
        "seasons/2025/districts.geojson",
        {
            "features": [
                {
                    "properties": {"district": "Sangrur"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[75.0, 30.0], [76.0, 30.0], [76.0, 30.4], [75.0, 30.0]]],
                    },
                }
            ]
        },
    )
    village = {"district": "Sangrur", "lon": 75.5, "lat": 30.2}
    _write(
        tmp_path,
        "seasons/2025/villages.json",
        {
            "items": [
                village
                | {
                    "id": "a-alpha",
                    "name": "Alpha",
                    "burned_ha": 90.0,
                    "unrecorded_ha": 30.0,
                    "weekly": [{"week": "2025-W45", "burned_ha": 20.0, "unrecorded_ha": 5.0}],
                },
                village
                | {
                    "id": "b-beta",
                    "name": "Beta",
                    "burned_ha": 60.0,
                    "unrecorded_ha": 55.0,
                    "weekly": [{"week": "2025-W44", "burned_ha": 60.0, "unrecorded_ha": 55.0}],
                },
                {
                    "id": "c-gamma",
                    "name": "Gamma",
                    "district": "Bathinda",
                    "lon": 75.0,
                    "lat": 30.3,
                    "burned_ha": 100.0,
                    "unrecorded_ha": 80.0,
                    "weekly": [],
                },
            ]
        },
    )
    _write(tmp_path, "imagery/index.json", {"items": [{"village_id": "b-beta"}]})
    run = {
        "run_id": "2025-11-06",
        "kind": "replay",
        "start": RUN_START,
        "hours": 48,
        "delhi_mean_peak": 98.9,
    }
    quiet = run | {
        "run_id": "2025-10-05",
        "start": RUN_START - 32 * 24 * HOUR,
        "delhi_mean_peak": 0.0,
    }
    _write(tmp_path, "smoke/index.json", {"runs": [quiet, run]})
    series = [100, 100, 37, 13] + [0] * 22 + [52, 100, 75, 42] + [0] * 18
    for item in (run, quiet):
        _write(
            tmp_path,
            f"smoke/{item['run_id']}/localities.json",
            {
                "items": [
                    {
                        "id": "x-dwarka",
                        "name": "Dwarka",
                        "name_hi": "द्वारका",
                        "district": "South West",
                        "lon": 77.04,
                        "lat": 28.6,
                        "h3": "h",
                        "sai": series,
                    },
                    {
                        "id": "y-dwarka",
                        "name": "Dwarka",
                        "district": "South West",
                        "lon": 77.06,
                        "lat": 28.58,
                        "h3": "g",
                        "sai": [0] * 48,
                    },
                    {
                        "id": "z-rohini",
                        "name": "Rohini",
                        "name_hi": "रोहिणी",
                        "district": "North ",
                        "lon": 77.1,
                        "lat": 28.7,
                        "h3": "f",
                        "sai": [0] * 48,
                    },
                ]
            },
        )
        _write(
            tmp_path,
            f"smoke/{item['run_id']}/delhi_sai_h3r7.json",
            {
                "hours": [item["start"] + i * HOUR for i in range(48)],
                "source_versions": {"burn_sources": "AfterPass 2025 replay burn scars: Sangrur"},
            },
        )
    _write(
        tmp_path,
        "validation/2025.json",
        {
            "district": "Sangrur",
            "samples": {"confident_viirs_detections": 1275},
            "thresholds": {"t_nbr": 0.0},
            "metrics": {"recall_on_firms_positives": 0.3182, "fpr_on_clear_negatives": 0.0},
        },
    )
    method = tmp_path / "METHOD.md"
    method.write_text(
        "# Method\n\nIntro.\n\n## How scars are found {#detection}\n\nChar under\n0.5 hectares "
        "is dropped.\n\n## Limits {#limitations}\n\nClouds leave gaps.\n\n"
        "## Checks {#validation}\n\nThree.\n"
    )
    monkeypatch.setenv("AFTERPASS_DATA", str(tmp_path))
    monkeypatch.setenv("AFTERPASS_METHOD", str(method))
    data.clear_cache()
    yield tmp_path
    data.clear_cache()


def test_gazetteer_finds_districts_in_english_hindi_and_misspelt() -> None:
    districts = ["Sangrur", "Bathinda", "Firozpur"]
    assert gazetteer.find_district("Sangroor", districts) == "Sangrur"
    assert gazetteer.find_district("संगरूर ज़िला", districts) == "Sangrur"
    assert gazetteer.find_district("Bhatinda district", districts) == "Bathinda"
    assert gazetteer.find_district("फिरोजपुर", districts) == "Firozpur"
    assert gazetteer.find_district("Ludhiana", districts) is None


def test_gazetteer_finds_localities_and_prefers_the_well_known_one(public) -> None:
    items = data.load("smoke/2025-11-06/localities.json")["items"]
    for name in ("Dwarka", "द्वारका", "Dwarkaa", "Dwarka sector 10"):
        found, _ = gazetteer.find_locality(name, items)
        assert found is not None and found["id"] == "x-dwarka", name
    missing, similar = gazetteer.find_locality("Rohni Nagar", items)
    assert missing is None or missing["name"] == "Rohini"
    nothing, similar = gazetteer.find_locality("Atlantis", items)
    assert nothing is None and similar == []


def test_season_overview_for_everything_and_for_one_district(public) -> None:
    everything = tools.season_overview(2025)
    assert everything["data"]["burned_ha"] == 300.0
    assert everything["data"]["not_in_official_counts_pct"] == 60.0
    assert everything["data"]["in_official_counts_pct"] == 40.0
    assert "Not all of Punjab" in everything["data"]["scope"]
    assert everything["data"]["data_window"]["data_through"] == "2025-11-29"

    one = tools.season_overview(2025, "संगरूर")
    assert (
        one["data"]["district"] == "Sangrur" and one["data"]["not_in_official_counts_ha"] == 100.0
    )
    assert one["ui_actions"] == [
        {"type": "highlight_district", "name": "Sangrur"},
        {"type": "fly_to", "lon": 75.5, "lat": 30.2, "zoom": 9.2},
    ]


def test_unknown_season_or_district_is_an_error_not_a_guess(public) -> None:
    assert "error" in tools.season_overview(2024)["data"]
    unknown = tools.season_overview(2025, "Ludhiana")
    assert unknown["data"]["published_districts"] == ["Sangrur", "Bathinda"]
    assert unknown["ui_actions"] == []


def test_top_villages_rank_by_area_not_in_official_counts(public) -> None:
    result = tools.top_unrecorded_villages("Sangrur", n=5)
    rows = result["data"]["villages"]
    assert [row["village"] for row in rows] == ["Beta", "Alpha"]
    assert rows[0]["before_after_imagery"] is True and rows[1]["before_after_imagery"] is False
    assert rows[0]["not_in_official_counts_pct"] == 91.7
    assert {"type": "highlight_village", "id": "b-beta"} in result["ui_actions"]
    assert {"type": "open_imagery", "village_id": "b-beta"} in result["ui_actions"]

    week = tools.top_unrecorded_villages("Sangrur", week="2025-W45")
    assert [row["village"] for row in week["data"]["villages"]] == ["Alpha"]
    assert week["data"]["villages"][0]["not_in_official_counts_ha"] == 5.0
    assert "error" in tools.top_unrecorded_villages("Sangrur", week="week 45")["data"]
    everywhere = tools.top_unrecorded_villages(n=1)
    assert everywhere["data"]["villages"][0]["village"] == "Gamma"


def test_district_trend_gives_weeks_and_the_peak(public) -> None:
    result = tools.district_trend("Sangroor")
    weeks = result["data"]["weeks"]
    assert [week["week"] for week in weeks] == ["2025-W44", "2025-W45"]
    assert weeks[1]["from"] == "2025-11-03" and weeks[1]["to"] == "2025-11-09"
    assert result["data"]["peak_week"]["week"] == "2025-W45"
    assert {"type": "show_layer", "id": "burns"} in result["ui_actions"]


def test_detection_times_show_the_midday_cluster(public) -> None:
    payload = tools.official_detection_times()["data"]
    assert payload["official_fire_detections"] == 4377
    assert payload["detections_12_to_16_ist"] == 4330
    assert payload["detections_12_to_16_ist_pct"] == 98.9
    assert payload["detections_16_to_24_ist"] == 0
    assert payload["detections_by_ist_hour"]["13:00"] == 2000


def test_smoke_outlook_uses_the_smokiest_replay_run_and_reports_every_high_window(public) -> None:
    result = tools.smoke_outlook("द्वारका")
    payload = result["data"]
    assert payload["place"] == "Dwarka" and payload["delhi_district"] == "South West"
    assert payload["run"]["from_ist"] == "Thu 06 Nov 2025, 00:00"
    assert payload["highest_index"] == 100
    assert payload["peak_window"]["to_ist"] == "Thu 06 Nov 2025, 02:00"
    assert [w["hours"] for w in payload["windows_at_high_or_above"]] == [2, 3]
    assert payload["windows_at_high_or_above"][1]["from_ist"] == "Fri 07 Nov 2025, 02:00"
    assert payload["hours_at_each_level"] == {"Low": 41, "Moderate": 2, "High": 1, "Very high": 4}
    assert payload["hours_at_high_or_above"] == 5
    assert result["ui_actions"][0] == {"type": "play_smoke", "run_id": "2025-11-06", "from_hour": 0}
    assert {"type": "highlight_locality", "id": "x-dwarka"} in result["ui_actions"]


def test_smoke_outlook_for_a_named_day_a_short_span_and_an_unknown_place(public) -> None:
    quiet = tools.smoke_outlook("Dwarka", start_date="2025-10-05")
    assert quiet["data"]["highest_index"] == 100  # the fixture reuses the series
    short = tools.smoke_outlook("Dwarka", hours=3)["data"]
    assert short["hourly_index_from_start"] == [100, 100, 37]
    assert "error" in tools.smoke_outlook("Dwarka", start_date="2025-12-25")["data"]
    unknown = tools.smoke_outlook("Atlantis")
    assert "error" in unknown["data"] and unknown["ui_actions"] == []


def test_method_sections_come_from_the_document_with_limits_and_numbers(public) -> None:
    detection = tools.method_and_limits("Detection")["data"]
    assert "0.5 hectares" in detection["text"] and detection["limitations"] == "Clouds leave gaps."
    validation = tools.method_and_limits("validation")["data"]
    assert (
        validation["numbers"]["calibration"]["share_of_official_detections_also_flagged_pct"]
        == 31.8
    )
    assert "Not done yet" in validation["numbers"]["visual_check"]
    missing = tools.method_and_limits("astrology")["data"]
    assert missing["topics"] == ["detection", "limitations", "validation"]


def test_grounding_accepts_rounding_grouping_and_units() -> None:
    results = [{"burned_ha": 423996.4, "pct": 71.5, "text": "under\n0.5 hectares", "at": "13:30"}]
    for answer in (
        "4,23,996 ha burned and 71.5% is not in official counts.",
        "About 424,000 ha, roughly 72 %.",
        "लगभग 4.24 लाख हेक्टेयर, ७१.५ प्रतिशत।",
        "Fields under 0.5 ha are missed; satellites pass at 1:30 PM. "
        "PM2.5 is not modelled by Sentinel-2.",
        "423\u202f996 ha",  # a narrow no-break space groups the thousands
    ):
        check = grounding.check(answer, "How much burned in 2025?", results)
        assert check["grounded"], (answer, check)


def test_grounding_rejects_invented_figures_and_ruled_out_words() -> None:
    results = [{"burned_ha": 423996.4, "pct": 71.5}]
    invented = grounding.check("Chaunda burned 45 ha, 28 ha uncounted.", "Chaunda?", results)
    assert not invented["grounded"] and invented["unmatched"] == ["45", "28"]
    wording = grounding.check("These illegal fires were hidden.", "?", results)
    assert not wording["grounded"] and wording["banned_words"] == ["hidden", "illegal"]
    assert grounding.check("I can't share names.", "names?", [])["grounded"]


def _scripted(*answers: str, calls: int = 1):
    """A stand-in model: calls the first tool `calls` times, then gives each answer in turn."""
    remaining = list(answers)
    prompts: list[str] = []

    def runner(question, functions, system_prompt):
        prompts.append(system_prompt)
        outputs = [functions[0](season=2025) for _ in range(calls)]
        runner.outputs = outputs
        return remaining.pop(0), {"input_tokens": 100, "output_tokens": 20}

    runner.prompts = prompts
    return runner


def test_ask_returns_the_answer_the_tools_used_and_the_map_actions(public) -> None:
    reply = handler.ask("How much burned in 2025?", runner=_scripted("300 ha burned in 2025."))
    assert reply["answer"] == "300 ha burned in 2025."
    assert reply["tools_used"] == [
        {"name": "season_overview", "input": {"season": 2025}, "ok": True}
    ]
    assert reply["ui_actions"] == [{"type": "show_layer", "id": "burns"}]
    assert reply["grounding"]["grounded"] and reply["usage"]["input_tokens"] == 100


def test_ask_refuses_long_and_empty_questions_without_calling_the_model(public) -> None:
    def never(*_):
        raise AssertionError("the model must not be called")

    long = handler.ask("x" * (handler.MAX_QUESTION_CHARS + 1), runner=never)
    assert long["error"] == "too_long" and long["tools_used"] == []
    assert handler.ask("   ", runner=never)["error"] == "empty"


def test_tool_calls_stop_at_the_limit(public) -> None:
    runner = _scripted("300 ha burned in 2025.", calls=handler.MAX_TOOL_CALLS + 2)
    reply = handler.ask("How much burned in 2025?", runner=runner)
    assert len(reply["tools_used"]) == handler.MAX_TOOL_CALLS
    assert "limit" in json.loads(runner.outputs[-1])["error"]
    assert "burned_ha" in json.loads(runner.outputs[0])


def test_an_ungrounded_answer_is_asked_for_again_and_flagged_if_still_wrong(public) -> None:
    runner = _scripted("999 ha burned.", "300 ha burned.")
    fixed = handler.ask("How much burned?", runner=runner)
    assert fixed["answer"] == "300 ha burned." and fixed["grounding"]["grounded"]
    assert "999" in runner.prompts[1] and fixed["usage"]["input_tokens"] == 200

    stubborn = handler.ask("How much burned?", runner=_scripted("999 ha burned.", "998 ha burned."))
    assert not stubborn["grounding"]["grounded"] and stubborn["grounding"]["unmatched"] == ["998"]


def test_the_reply_language_follows_the_question() -> None:
    assert handler.HINDI_NOTE in handler.system_prompt("क्या द्वारका तक धुआँ पहुँचेगा?")
    assert handler.LATIN_NOTE in handler.system_prompt("Will smoke reach Dwarka?")
    assert handler.system_prompt("x").startswith("You are AfterPass")


def test_lambda_handler_reads_the_question_from_the_body(public, monkeypatch) -> None:
    monkeypatch.setattr(handler, "strands_runner", _scripted("300 ha burned in 2025."))
    ok = handler.lambda_handler(
        {"body": json.dumps({"question": "How much burned in 2025?"})}, None
    )
    assert ok["statusCode"] == 200 and json.loads(ok["body"])["answer"].startswith("300")
    bad = handler.lambda_handler({"body": "not json"}, None)
    assert bad["statusCode"] == 400 and json.loads(bad["body"])["error"] == "empty"
