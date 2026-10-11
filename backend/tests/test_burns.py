from datetime import date

import numpy as np
from affine import Affine

from afterpass import burns
from afterpass.burns import PixelState, Thresholds

TH = Thresholds()
# Typical 0-1 reflectances (B8A, B11, B12) for the surfaces the rule must tell apart.
CHAR = (0.12, 0.20, 0.19)
STRAW = (0.32, 0.42, 0.30)
GREEN = (0.40, 0.20, 0.10)
WATER = (0.03, 0.02, 0.01)
CLOUD = (0.60, 0.50, 0.45)


def _layers(surface: tuple[float, float, float], shape=(1, 1)):
    b8a, b11, b12 = (np.full(shape, v, np.float32) for v in surface)
    nbr, _, mirbi = burns.indices(b8a, b11, b12)
    return nbr, mirbi, b8a


def _is_char(surface) -> bool:
    nbr, mirbi, b8a = _layers(surface)
    return bool(burns.char_signature(nbr, mirbi, b8a, TH)[0, 0])


def test_indices_match_formulas() -> None:
    nbr, nbr2, mirbi = burns.indices(*(np.array([v], np.float32) for v in CHAR))
    assert np.isclose(nbr[0], (0.12 - 0.19) / (0.12 + 0.19), atol=1e-6)
    assert np.isclose(nbr2[0], (0.20 - 0.19) / (0.20 + 0.19), atol=1e-6)
    assert np.isclose(mirbi[0], 10 * 0.19 - 9.8 * 0.20 + 2, atol=1e-6)


def test_indices_zero_denominator_is_nan() -> None:
    zero = np.zeros(1, np.float32)
    nbr, nbr2, _ = burns.indices(zero, zero, zero)
    assert np.isnan(nbr[0]) and np.isnan(nbr2[0])


def test_char_signature_separates_surfaces() -> None:
    assert _is_char(CHAR)
    assert not _is_char(STRAW)
    assert not _is_char(GREEN)
    assert not _is_char(WATER)
    assert not _is_char(CLOUD)


def test_valid_mask_scl_and_cloud_probability() -> None:
    scl = np.array([[0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]], np.uint8)
    cloud = np.zeros_like(scl)
    nodata = np.zeros(scl.shape, bool)
    valid = burns.valid_mask(scl, cloud, nodata)
    assert valid.tolist() == [[False, False, True, True, True, False, True] + [False] * 4]

    cloud[0, 3] = 30
    nodata[0, 4] = True
    valid = burns.valid_mask(scl, cloud, nodata)
    assert not valid[0, 3] and not valid[0, 4] and valid[0, 2]


def test_cloud_shadow_invalid_only_near_cloud() -> None:
    scl = np.full((1, 200), 5, np.uint8)
    scl[0, 0] = 9  # cloud
    scl[0, 10] = 3  # shadow 200 m from cloud
    scl[0, 150] = 3  # "shadow" 3 km from cloud: likely a scar
    zeros = np.zeros(scl.shape, np.uint8)
    valid = burns.valid_mask(scl, zeros, zeros.astype(bool))
    assert not valid[0, 10]
    assert valid[0, 150]


def test_isolated_shadow_valid_when_no_cloud_in_scene() -> None:
    scl = np.full((3, 3), 3, np.uint8)
    zeros = np.zeros(scl.shape, np.uint8)
    assert burns.valid_mask(scl, zeros, zeros.astype(bool)).all()


def _step(state, day, surface, valid=True):
    nbr, mirbi, b8a = _layers(surface)
    fresh, start = burns.fresh_burn(state, day, np.full((1, 1), valid), nbr, mirbi, b8a, TH)
    return bool(fresh[0, 0]), int(start[0, 0])


def test_fresh_burn_needs_previous_observation_and_drop() -> None:
    state = PixelState((1, 1))
    assert _step(state, date(2025, 11, 1), CHAR) == (False, 0)  # no earlier observation
    assert _step(state, date(2025, 11, 3), CHAR) == (False, 0)  # already dark: no drop

    state = PixelState((1, 1))
    _step(state, date(2025, 11, 1), STRAW)
    fresh, start = _step(state, date(2025, 11, 4), CHAR)
    assert fresh and start == date(2025, 11, 1).toordinal()


def test_first_detection_date_is_kept() -> None:
    state = PixelState((1, 1))
    _step(state, date(2025, 11, 1), STRAW)
    assert _step(state, date(2025, 11, 4), CHAR)[0]
    _step(state, date(2025, 11, 6), STRAW)
    assert not _step(state, date(2025, 11, 9), CHAR)[0]  # flagged once only
    assert state.first_detected[0, 0] == date(2025, 11, 4).toordinal()


def test_invalid_dates_do_not_reset_the_reference() -> None:
    state = PixelState((1, 1))
    _step(state, date(2025, 11, 1), STRAW)
    _step(state, date(2025, 11, 3), CLOUD, valid=False)
    fresh, start = _step(state, date(2025, 11, 5), CHAR)
    assert fresh and start == date(2025, 11, 1).toordinal()


def test_lookback_limit() -> None:
    state = PixelState((1, 1))
    _step(state, date(2025, 10, 1), STRAW)
    assert not _step(state, date(2025, 10, 22), CHAR)[0]  # 21 days: too old to compare

    state = PixelState((1, 1))
    _step(state, date(2025, 10, 1), STRAW)
    assert _step(state, date(2025, 10, 21), CHAR)[0]  # exactly 20 days


def test_min_area_and_opening() -> None:
    fresh = np.zeros((40, 40), bool)
    fresh[2:6, 2:6] = True  # 16 px = 0.64 ha: kept
    fresh[20:23, 20:24] = True  # 12 px = 0.48 ha: dropped
    fresh[30, 5:35] = True  # 1 px wide line: removed by the 3x3 opening
    labels, count = burns.clean_components(fresh)
    assert count == 1
    assert labels[3, 3] == 1 and labels[21, 21] == 0 and labels[30, 10] == 0


def test_vectorise_attributes() -> None:
    fresh = np.zeros((20, 20), bool)
    fresh[5:10, 5:10] = True  # 25 px = 1 ha
    day, prev = date(2025, 11, 4), date(2025, 11, 2)
    start = np.where(fresh, prev.toordinal(), 0).astype(np.int32)
    start[5, 5] = date(2025, 10, 25).toordinal()  # one pixel was cloudy on 2 Nov
    transform = Affine(20, 0, 500_000, 0, -20, 3_400_000)
    scars = burns.vectorise(fresh, start, day, transform, "EPSG:32643", "Sangrur")
    assert len(scars) == 1
    scar = scars.iloc[0]
    assert scar["area_ha"] == 1.0
    assert scar["first_detected"] == "2025-11-04"
    assert scar["window_start"] == "2025-11-02"
    assert scar["district"] == "Sangrur"


def test_vectorise_empty() -> None:
    empty = np.zeros((10, 10), bool)
    transform = Affine(20, 0, 0, 0, -20, 0)
    scars = burns.vectorise(
        empty, empty.astype(np.int32), date(2025, 11, 4), transform, "EPSG:32643", "Sangrur"
    )
    assert len(scars) == 0
