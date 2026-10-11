"""Download cache helpers. Everything fetched from the network lands under `data/cache/`."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from afterpass.config import CACHE_DIR


def cache_path(*parts: str) -> Path:
    """Path under data/cache/, with parent directories created."""
    path = CACHE_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temp file so an interrupted run never leaves a half-written cache entry."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def download(url: str, dest: Path, *, timeout: float = 300.0) -> Path:
    """Fetch `url` to `dest` unless it is already cached."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
    atomic_write_bytes(dest, resp.content)
    return dest
