from datetime import date

from afterpass import firms

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight\n"
)


def _parse(rows: str):
    return firms.parse(HEADER + rows, "VIIRS_SNPP_SP")


def test_acq_time_converts_to_ist() -> None:
    df = _parse("30.2,75.8,330.1,0.4,0.4,2025-11-03,0805,N,VIIRS,n,2,290.1,4.2,D\n")
    assert df["acq_dt_utc"].iloc[0].isoformat() == "2025-11-03T08:05:00+00:00"
    assert df["acq_dt_ist"].iloc[0].isoformat() == "2025-11-03T13:35:00+05:30"


def test_acq_time_is_zero_padded() -> None:
    # FIRMS drops leading zeros: "5" is 00:05 UTC and "45" is 00:45 UTC.
    df = _parse(
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,5,N,VIIRS,n,2,290.1,4.2,N\n"
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,45,N,VIIRS,h,2,290.1,4.2,N\n"
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,2010,N,VIIRS,l,2,290.1,4.2,N\n"
    )
    assert df["acq_time"].tolist() == ["0005", "0045", "2010"]
    assert df["acq_dt_ist"].iloc[0].isoformat() == "2025-11-03T05:35:00+05:30"
    # 20:10 UTC is already the next day in IST.
    assert df["acq_dt_ist"].iloc[2].isoformat() == "2025-11-04T01:40:00+05:30"


def test_confident_viirs_filter() -> None:
    df = _parse(
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,0805,N,VIIRS,n,2,290.1,4.2,D\n"
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,0805,N,VIIRS,h,2,290.1,4.2,D\n"
        "30.2,75.8,330.1,0.4,0.4,2025-11-03,0805,N,VIIRS,l,2,290.1,4.2,D\n"
    )
    assert firms.is_confident_viirs(df).tolist() == [True, True, False]
    modis = firms.parse(
        HEADER + "30.2,75.8,330,1,1,2025-11-03,0805,Terra,MODIS,85,6.1,290,9,D\n", "MODIS_SP"
    )
    assert not firms.is_confident_viirs(modis).any()


def test_empty_response_parses() -> None:
    assert len(_parse("")) == 0


def test_plan_uses_sp_then_nrt_without_overlap() -> None:
    availability = {
        "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 6, 30)),
        "VIIRS_SNPP_NRT": (date(2026, 7, 1), date(2026, 10, 11)),
        "VIIRS_NOAA21_NRT": (date(2024, 1, 17), date(2026, 10, 11)),
    }
    plan = firms.plan_requests(date(2026, 6, 27), date(2026, 7, 4), availability)
    snpp = [r for r in plan if r[0].startswith("VIIRS_SNPP")]
    assert snpp == [
        ("VIIRS_SNPP_SP", date(2026, 6, 27), 4),
        ("VIIRS_SNPP_NRT", date(2026, 7, 1), 4),
    ]
    noaa21 = [r for r in plan if r[0].startswith("VIIRS_NOAA21")]
    assert noaa21 == [
        ("VIIRS_NOAA21_NRT", date(2026, 6, 27), 5),
        ("VIIRS_NOAA21_NRT", date(2026, 7, 2), 3),
    ]


def test_plan_2025_replay_is_all_standard_processing_where_available() -> None:
    availability = {
        "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 6, 30)),
        "VIIRS_SNPP_NRT": (date(2026, 7, 1), date(2026, 10, 11)),
    }
    plan = firms.plan_requests(date(2025, 11, 1), date(2025, 11, 12), availability)
    assert plan == [
        ("VIIRS_SNPP_SP", date(2025, 11, 1), 5),
        ("VIIRS_SNPP_SP", date(2025, 11, 6), 5),
        ("VIIRS_SNPP_SP", date(2025, 11, 11), 2),
    ]
