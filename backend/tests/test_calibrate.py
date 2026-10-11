from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
from conftest import CRS, TRANSFORM
from shapely.geometry import Point

from afterpass import calibrate
from afterpass.burns import Thresholds

SHAPE = (40, 40)
STRAW = (0.34, 0.42, 0.28)
CHAR = (0.12, 0.20, 0.19)


def _fill(surface, burnt=None, burnt_surface=CHAR):
    bands = [np.full(SHAPE, v, np.float32) for v in surface]
    if burnt is not None:
        for band, value in zip(bands, burnt_surface, strict=True):
            band[burnt] = value
    return bands


def _detections(*rows):
    return gpd.GeoDataFrame(
        {"acq_dt_utc": pd.to_datetime([r[0] for r in rows], utc=True)},
        geometry=[Point(r[1], r[2]) for r in rows],
        crs=CRS,
    )


def _pixel_centre(row: int, col: int) -> tuple[float, float]:
    return TRANSFORM @ (col + 0.5, row + 0.5)


def test_flag_rate_treats_missing_drop_as_not_flagged() -> None:
    rows = np.array(
        [
            [-0.2, 1.9, 0.12, 0.4],  # char with a clear drop
            [-0.2, 1.9, 0.12, np.nan],  # char, but no earlier pass to compare with
            [0.4, 1.0, 0.40, 0.0],  # green crop
        ],
        np.float32,
    )
    assert calibrate.flag_rate(rows, Thresholds()) == 1 / 3


def test_clear_negative_definition() -> None:
    nbr = np.array([0.35, 0.10, 0.10, 0.0])
    b8a = np.array([0.20, 0.30, 0.20, 0.30])
    assert calibrate.clear_negative(nbr, b8a).tolist() == [True, True, False, False]


def test_positives_come_from_first_pass_after_the_detection(make_scene) -> None:
    burnt = np.zeros(SHAPE, bool)
    burnt[10:31, 10:31] = True  # larger than the 150 m sampling disc
    scenes = [
        make_scene(date(2025, 11, 1), *_fill(STRAW)),
        make_scene(date(2025, 11, 4), *_fill(STRAW, burnt)),
        make_scene(date(2025, 11, 6), *_fill(STRAW, burnt)),
    ]
    x, y = _pixel_centre(20, 20)
    # Seen at 13:30 IST on 2 Nov: after the 1 Nov pass, before the 4 Nov pass.
    fires = _detections(("2025-11-02 08:00", x, y))
    samples = calibrate.collect(scenes, np.ones(SHAPE, bool), fires, TRANSFORM)

    # Pixel centres within 150 m of the fire, each sampled once (on 4 Nov, not again on 6 Nov).
    rows, cols = np.mgrid[: SHAPE[0], : SHAPE[1]]
    expected = int((np.hypot(rows - 20, cols - 20) * 20 <= 150).sum())
    assert len(samples.positives) == expected
    nbr, _, _, dnbr = samples.positives.T
    assert (nbr < 0).all() and (dnbr > 0.1).all()
    assert calibrate.flag_rate(samples.positives, Thresholds()) == 1.0


def test_same_day_pass_before_the_fire_is_not_used(make_scene) -> None:
    scenes = [
        make_scene(date(2025, 11, 1), *_fill(STRAW)),
        make_scene(date(2025, 11, 2), *_fill(STRAW)),  # 05:40 UTC, before the 08:00 UTC fire
        make_scene(date(2025, 11, 4), *_fill(CHAR)),
    ]
    x, y = _pixel_centre(20, 20)
    fires = _detections(("2025-11-02 08:00", x, y))
    samples = calibrate.collect(scenes, np.ones(SHAPE, bool), fires, TRANSFORM)
    assert len(samples.positives) > 0
    assert (samples.positives[:, 0] < 0).all()  # sampled on 4 Nov, when the field is char


def test_detection_with_no_pass_within_six_days_gives_no_positives(make_scene) -> None:
    scenes = [
        make_scene(date(2025, 11, 1), *_fill(STRAW)),
        make_scene(date(2025, 11, 10), *_fill(CHAR)),
    ]
    x, y = _pixel_centre(20, 20)
    fires = _detections(("2025-11-02 08:00", x, y))
    samples = calibrate.collect(scenes, np.ones(SHAPE, bool), fires, TRANSFORM)
    assert len(samples.positives) == 0


def test_grid_search_and_choice_prefer_selective_thresholds(make_scene) -> None:
    burnt = np.zeros(SHAPE, bool)
    burnt[12:28, 12:28] = True
    scenes = [
        make_scene(date(2025, 11, 1), *_fill(STRAW)),
        make_scene(date(2025, 11, 4), *_fill(STRAW, burnt)),
    ]
    x, y = _pixel_centre(20, 20)
    fires = _detections(("2025-11-02 08:00", x, y))
    samples = calibrate.collect(scenes, np.ones(SHAPE, bool), fires, TRANSFORM)
    results = calibrate.grid_search(samples)
    chosen = calibrate.choose(results)
    assert chosen["recall"] == 1.0
    assert chosen["fpr"] == 0.0


def _result(th: Thresholds, recall: float, background: float, fpr: float = 0.0) -> dict:
    return {"thresholds": th, "recall": recall, "fpr": fpr, "background": background}


def test_choice_keeps_starting_thresholds_without_a_clear_gain() -> None:
    start = _result(Thresholds(), recall=0.30, background=0.09)
    slightly_better = _result(Thresholds(t_nir=0.24), recall=0.33, background=0.10)
    assert calibrate.choose([start, slightly_better]) is start


def test_choice_moves_when_the_gain_is_clear() -> None:
    start = _result(Thresholds(), recall=0.30, background=0.09)
    much_better = _result(Thresholds(t_nir=0.24), recall=0.45, background=0.10)
    assert calibrate.choose([start, much_better]) is much_better


def test_choice_ignores_combinations_over_the_fpr_limit() -> None:
    start = _result(Thresholds(), recall=0.30, background=0.09)
    leaky = _result(Thresholds(t_nbr=0.05), recall=0.90, background=0.10, fpr=0.05)
    assert calibrate.choose([start, leaky]) is start
    assert calibrate.most_recall([start, leaky]) is start
