"""Phase 4 check: which Open-Meteo endpoints return 100 m wind and boundary-layer height."""

from datetime import date

from afterpass import winds

for name, day in (
    ("historical_forecast", date(2025, 11, 3)),
    ("era5", date(2025, 11, 3)),
    ("forecast", date.today()),
):
    try:
        shares = winds.probe(name, day)
    except Exception as exc:  # noqa: BLE001 - report every endpoint, whatever fails
        print(f"{name:<20} {day}  FAILED: {exc}")
        continue
    cells = "  ".join(f"{k}={v:.0%}" for k, v in shares.items())
    print(f"{name:<20} {day}  {cells}")
