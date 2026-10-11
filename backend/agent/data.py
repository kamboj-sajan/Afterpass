"""Reads the public data files (brief §9.2) from a folder or a base URL, cached in memory.

`AFTERPASS_DATA` names the source: a folder such as `data/public`, or the CloudFront URL of
the `public/` prefix. `AFTERPASS_METHOD` names the method document; without it, the repository's
`docs/METHOD.md` is used, or the copy published next to the data.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data" / "public"
DEFAULT_METHOD = REPO_ROOT / "docs" / "METHOD.md"


class DataError(RuntimeError):
    """A public file is missing or unreadable."""


def source() -> str:
    return os.environ.get("AFTERPASS_DATA", str(DEFAULT_DATA)).rstrip("/")


@lru_cache(maxsize=256)
def _read(base: str, path: str) -> str:
    if base.startswith(("http://", "https://")):
        try:
            resp = httpx.get(f"{base}/{path}", timeout=20)
        except httpx.HTTPError as exc:
            raise DataError(f"{path}: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise DataError(f"{path}: HTTP {resp.status_code}")
        return resp.text
    file = Path(base) / path
    if not file.exists():
        raise DataError(f"{path}: not published")
    return file.read_text()


def load(path: str) -> dict:
    """One public JSON file, such as `seasons/2025/summary.json`."""
    return json.loads(_read(source(), path))


def method_text() -> str:
    """The method document: a local file if there is one, else `METHOD.md` from the data source."""
    named = os.environ.get("AFTERPASS_METHOD")
    path = Path(named) if named else DEFAULT_METHOD
    if path.exists():
        return path.read_text()
    if named:
        raise DataError("The method document is not available.")
    return _read(source(), "METHOD.md")


def clear_cache() -> None:
    _read.cache_clear()
