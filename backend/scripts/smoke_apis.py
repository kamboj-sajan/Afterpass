"""Phase 0 check: Earth Search and FIRMS both return data for Sangrur. Never prints the key."""

import httpx
from pystac_client import Client

from afterpass.config import settings

SANGRUR = (75.5, 29.9, 76.3, 30.6)  # rough bbox, W,S,E,N

stac = Client.open("https://earth-search.aws.element84.com/v1")
search = stac.search(
    collections=["sentinel-2-c1-l2a"], bbox=SANGRUR, datetime="2025-11-01/2025-11-15"
)
items = list(search.items())
dates = sorted({i.datetime.date().isoformat() for i in items if i.datetime})
print(f"Earth Search sentinel-2-c1-l2a, 1-15 Nov 2025: {len(items)} items on {len(dates)} dates")
print(f"  dates: {', '.join(dates)}")

key = settings().require_firms_key()
base = "https://firms.modaps.eosdis.nasa.gov/api"
avail = httpx.get(f"{base}/data_availability/csv/{key}/ALL", timeout=60)
print(f"FIRMS data_availability: HTTP {avail.status_code}")
if avail.status_code == 200:
    print("  " + avail.text.strip().replace("\n", "\n  "))
bbox = ",".join(map(str, SANGRUR))
for source in ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"):
    r = httpx.get(f"{base}/area/csv/{key}/{source}/{bbox}/5/2025-11-01", timeout=60)
    rows = r.text.strip().splitlines()
    print(f"FIRMS {source}, 1-5 Nov 2025: HTTP {r.status_code}, {max(len(rows) - 1, 0)} rows")
    if r.status_code == 200 and rows:
        print(f"  columns: {rows[0]}")
