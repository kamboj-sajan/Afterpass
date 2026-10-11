import numpy as np
import pandas as pd
import pytest

from afterpass import pm25


def _row(day: str, value, complete: float = 100.0) -> dict:
    return {
        "value": value,
        "period": {"datetimeFrom": {"utc": f"{day}T18:30:00Z", "local": f"{day}T00:00:00+05:30"}},
        "coverage": {"percentComplete": complete},
    }


def test_parse_days_keeps_well_covered_real_values_on_their_ist_date() -> None:
    payload = {
        "results": [
            _row("2025-11-01", 237.0, 96.0),
            _row("2025-11-02", 180.0, 50.0),  # half the day missing
            _row("2025-11-03", -999.0),  # a missing-value code
            _row("2025-11-04", None),
            _row("2025-11-05", 90.5, 75.0),
        ]
    }
    days = pm25.parse_days(payload)
    assert days.to_dict("records") == [
        {"day": "2025-11-01", "pm25": 237.0},
        {"day": "2025-11-05", "pm25": 90.5},
    ]
    empty = pm25.parse_days({"results": []})
    assert list(empty.columns) == ["day", "pm25"] and empty["pm25"].dtype == float


def _daily(values: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"station": station, "name": f"S{station}", "day": day, "pm25": value}
            for day, row in values.items()
            for station, value in enumerate(row)
        ]
    )


def test_city_mean_needs_enough_stations() -> None:
    daily = _daily({"2025-11-01": [100, 200, 300], "2025-11-02": [50, 70]})
    city = pm25.city_mean(daily, min_stations=3)
    assert list(city.index) == ["2025-11-01"]
    assert city.loc["2025-11-01", "pm25"] == 200
    assert city.loc["2025-11-01", "stations"] == 3


def test_compare_uses_the_days_both_series_have() -> None:
    days = [f"2025-11-{d:02d}" for d in range(1, 9)]
    sai = pd.Series([0, 1, 2, 4, 8, 16, 32, 64], index=days, dtype=float)
    observed = pd.Series([10, 20, 30, 40, 50, 60, np.nan, 80], index=days)
    result = pm25.compare(sai, observed.drop("2025-11-01"))
    assert result["days"] == 6
    # The same order on every shared day: a perfect rank correlation, a weaker linear one.
    assert result["spearman"]["rho"] == 1.0
    assert 0 < result["pearson"]["r"] < 1


def test_compare_refuses_too_little_data() -> None:
    days = ["2025-11-01", "2025-11-02", "2025-11-03"]
    flat = pm25.compare(
        pd.Series([0.0, 0.0, 0.0], index=days), pd.Series([1.0, 2.0, 3.0], index=days)
    )
    assert flat == {"days": 3, "pearson": None, "spearman": None}
    short = pm25.compare(
        pd.Series([1.0, 2.0], index=days[:2]), pd.Series([1.0, 2.0], index=days[:2])
    )
    assert short["pearson"] is None


def test_report_lists_every_day_and_keeps_gaps() -> None:
    daily = _daily({f"2025-11-0{d}": [100.0 * d] * 5 for d in (1, 2, 3, 4)})
    sai = pd.Series(
        [1.0, 5.0, 2.0, 9.0], index=["2025-11-02", "2025-11-03", "2025-11-04", "2025-11-05"]
    )
    block = pm25.report(2025, sai, daily, ["Sangrur"])
    assert block["stations"] == 5 and block["station_days"] == 20 and block["days"] == 3
    assert [row["date"] for row in block["series"]] == [f"2025-11-0{d}" for d in range(1, 6)]
    assert block["series"][0] == {"date": "2025-11-01", "sai": None, "pm25": 100.0, "stations": 5}
    assert block["series"][-1] == {"date": "2025-11-05", "sai": 9.0, "pm25": None, "stations": 0}
    # Shared days 2-4: index ranks 1, 3, 2 against PM2.5 ranks 1, 2, 3.
    assert block["spearman"]["rho"] == pytest.approx(0.5)
