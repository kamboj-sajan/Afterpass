"""Delhi smoke alerts (brief §11.6): which zones to tell, and what the email says.

A zone is one of Delhi's districts. It is told when the forecast for any named place in it
reaches High. The email gives the level and the hours, says what the index is and is not, and
points to official AQI. It never states a concentration.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
HIGH = 50
LEVELS = (("Low", 0), ("Moderate", 25), ("High", 50), ("Very high", 75))
ZONES = (
    "Central",
    "East",
    "New Delhi",
    "North",
    "North East",
    "North West",
    "Shahdara",
    "South",
    "South East",
    "South West",
    "West",
)


def level(value: float) -> str:
    return [name for name, lowest in LEVELS if value >= lowest][-1]


def _ist(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).astimezone(IST).strftime("%a %d %b, %H:%M")


def zone_peaks(run: dict, localities: list[dict]) -> dict[str, dict]:
    """For each zone, its highest forecast value, when, and at which named place."""
    peaks: dict[str, dict] = {}
    for place in localities:
        zone = place["district"].strip()
        top = max(place["sai"], default=0)
        if zone not in peaks or top > peaks[zone]["index"]:
            hour = place["sai"].index(top) if place["sai"] else 0
            peaks[zone] = {
                "index": top,
                "at": run["start"] + hour * 3600,
                "place": place["name"],
                "hours_high": sum(1 for value in place["sai"] if value >= HIGH),
            }
    return peaks


def messages(run: dict, localities: list[dict], web_url: str) -> list[dict]:
    """One email per zone whose forecast reaches High: `zone`, `subject` and `body`."""
    out = []
    for zone, peak in sorted(zone_peaks(run, localities).items()):
        if peak["index"] < HIGH:
            continue
        name = level(peak["index"])
        body = (
            f"AfterPass smoke outlook for {zone} Delhi\n\n"
            f"Level: {name} (Smoke Arrival Index {peak['index']} of 100)\n"
            f"Highest around: {_ist(peak['at'])} IST, near {peak['place']}\n"
            f"Hours at High or above in the next 48: {peak['hours_high']}\n"
            f"Forecast made: {_ist(run['start'])} IST\n\n"
            "This is a relative index of stubble smoke from a simplified transport model. "
            "It is not a PM2.5 reading and not medical advice. It assumes burning continues at "
            "the recent rate and covers only the districts AfterPass maps.\n"
            "For health decisions, check official AQI: CPCB's SAMEER app, "
            "https://airquality.cpcb.gov.in/AQI_India/\n\n"
            f"See the outlook: {web_url}/delhi\n"
            "To stop these emails, use the unsubscribe link below."
        )
        out.append(
            {
                "zone": zone,
                "subject": f"AfterPass: {name} smoke outlook, {zone} Delhi",
                "body": body,
            }
        )
    return out
