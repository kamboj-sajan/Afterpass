"""Match burn scars with official FIRMS detections (brief §7)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

MATCH_DISTANCE_M = {"VIIRS": 375.0, "MODIS": 1000.0}
DATE_SLACK = pd.Timedelta(days=1)


def recorded(scars: gpd.GeoDataFrame, detections: gpd.GeoDataFrame) -> np.ndarray:
    """True for scars with a FIRMS detection close enough in space and time.

    A detection counts when it lies within the sensor's match distance of the scar polygon and
    its `acq_date` falls in [window_start - 1 day, first_detected + 1 day]. Both inputs must be
    in the same projected CRS (metres).
    """
    hit = np.zeros(len(scars), bool)
    if len(scars) == 0 or len(detections) == 0:
        return hit
    earliest = pd.to_datetime(scars["window_start"]).to_numpy() - DATE_SLACK
    latest = pd.to_datetime(scars["first_detected"]).to_numpy() + DATE_SLACK
    for sensor, distance in MATCH_DISTANCE_M.items():
        points = detections[detections["sensor"] == sensor]
        if len(points) == 0:
            continue
        reach = gpd.GeoDataFrame(
            {"scar": np.arange(len(scars))}, geometry=scars.geometry.buffer(distance).to_numpy()
        ).set_crs(scars.crs)
        pairs = gpd.sjoin(reach, points[["acq_date", "geometry"]], predicate="intersects")
        when = pd.to_datetime(pairs["acq_date"]).to_numpy()
        index = pairs["scar"].to_numpy()
        in_window = (when >= earliest[index]) & (when <= latest[index])
        hit[index[in_window]] = True
    return hit
