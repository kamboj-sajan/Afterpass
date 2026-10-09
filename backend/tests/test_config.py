import os

from afterpass import config


def test_gdal_env_set() -> None:
    assert os.environ["AWS_NO_SIGN_REQUEST"] == "YES"


def test_region_bbox_order() -> None:
    w, s, e, n = config.REGION_BBOX
    assert w < e and s < n
