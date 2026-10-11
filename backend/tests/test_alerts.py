from afterpass import alerts

RUN = {"run_id": "2026-10-11T2200", "start": 1791736200}  # 11 Oct 2026, 22:00 IST


def _place(name: str, zone: str, sai: list[int]) -> dict:
    return {"name": name, "district": zone, "sai": sai}


def test_a_zone_is_told_when_any_place_in_it_reaches_high() -> None:
    places = [
        _place("Dwarka", "South West", [0, 20, 62, 55, 10]),
        _place("Najafgarh", "South West", [0, 5, 30, 20, 0]),
        _place("Rohini", "North ", [0, 10, 49, 12, 0]),
    ]
    messages = alerts.messages(RUN, places, "https://example.org")
    assert [m["zone"] for m in messages] == ["South West"]
    body = messages[0]["body"]
    assert "High (Smoke Arrival Index 62 of 100)" in body and "near Dwarka" in body
    assert "Hours at High or above in the next 48: 2" in body
    assert "Mon 12 Oct, 00:00 IST" in body  # two hours after the forecast was made
    assert "not a PM2.5 reading" in body and "SAMEER" in body
    assert "https://example.org/delhi" in body
    assert messages[0]["subject"] == "AfterPass: High smoke outlook, South West Delhi"


def test_nothing_is_sent_when_no_zone_reaches_high() -> None:
    assert alerts.messages(RUN, [_place("Rohini", "North", [0, 10, 49])], "https://x") == []
    assert alerts.messages(RUN, [], "https://x") == []


def test_zone_names_match_the_sign_up_form() -> None:
    peaks = alerts.zone_peaks(RUN, [_place("Rohini", "North ", [80])])
    assert list(peaks) == ["North"] and set(peaks) <= set(alerts.ZONES)
    assert alerts.level(80) == "Very high"
