"""Moves pipeline files between the local data folder and the data bucket.

On Lambda nothing survives between runs, so each step pulls what it needs from the bucket's
`cache/` prefix and pushes what it made. A file that is already there with the same size is
left alone, which is what makes a retried step cheap.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path

import boto3

from afterpass.config import CACHE_DIR, PUBLIC_DIR, settings
from afterpass.s3 import CONTENT_TYPES, GZIPPED, upload_file

CACHE_PREFIX = "cache"
PUBLIC_PREFIX = "public"


def bucket_name() -> str:
    """The data bucket: named by DATA_BUCKET on Lambda, read from the stack elsewhere."""
    named = os.environ.get("DATA_BUCKET")
    if named:
        return named
    from afterpass.s3 import stack_output

    return stack_output("DataBucketName")


def _client():
    return boto3.client("s3", region_name=settings().aws_region)


def _listing(bucket: str, prefix: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for page in _client().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            found[item["Key"]] = item["Size"]
    return found


def pull(prefixes: Iterable[str], log: Callable[[str], None] = lambda _: None) -> int:
    """Download `cache/<prefix>...` into the local cache folder. Returns the files fetched."""
    bucket, client, fetched = bucket_name(), _client(), 0
    for prefix in prefixes:
        for key, size in _listing(bucket, f"{CACHE_PREFIX}/{prefix}").items():
            dest = CACHE_DIR / key.removeprefix(f"{CACHE_PREFIX}/")
            if dest.exists() and dest.stat().st_size == size:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(dest))
            fetched += 1
    log(f"Pulled {fetched} cached files")
    return fetched


def push(prefixes: Iterable[str], log: Callable[[str], None] = lambda _: None) -> int:
    """Upload local cache files under each prefix that the bucket does not have at that size."""
    bucket, client, sent = bucket_name(), _client(), 0
    for prefix in prefixes:
        have = _listing(bucket, f"{CACHE_PREFIX}/{prefix}")
        base = CACHE_DIR / prefix
        paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in paths:
            if path.name.endswith(".part"):
                continue
            key = f"{CACHE_PREFIX}/{path.relative_to(CACHE_DIR).as_posix()}"
            if have.get(key) == path.stat().st_size:
                continue
            client.upload_file(str(path), bucket, key)
            sent += 1
    log(f"Pushed {sent} cache files")
    return sent


def pull_public(names: Iterable[str]) -> None:
    """Download published files (gzipped in the bucket) into the local public folder."""
    bucket, client = bucket_name(), _client()
    for name in names:
        dest = PUBLIC_DIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            body = client.get_object(Bucket=bucket, Key=f"{PUBLIC_PREFIX}/{name}")
        except client.exceptions.NoSuchKey:
            continue
        raw = body["Body"].read()
        if body.get("ContentEncoding") == "gzip":
            import gzip

            raw = gzip.decompress(raw)
        dest.write_bytes(raw)


def push_public(paths: Iterable[Path]) -> int:
    """Publish local files from the public folder. Returns how many were uploaded."""
    bucket, client, sent = bucket_name(), _client(), 0
    for path in paths:
        if path.suffix in CONTENT_TYPES or path.suffix in GZIPPED:
            sent += upload_file(client, bucket, path, path.relative_to(PUBLIC_DIR).as_posix())
    return sent
