"""Upload the published files to the data bucket (`afterpass publish --target s3`).

Files go under `public/`, which CloudFront serves. JSON and GeoJSON are stored gzipped, so even
the largest scar files compress (CloudFront itself does not compress files over 10 MB). A file
whose content has not changed is not uploaded again.
"""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Callable
from pathlib import Path

import boto3

from afterpass.config import PUBLIC_DIR, REPO_ROOT, settings

PREFIX = "public"
CONTENT_TYPES = {
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".webp": "image/webp",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
}
GZIPPED = {".json", ".geojson", ".md"}
METHOD_DOC = REPO_ROOT / "docs" / "METHOD.md"
# The hash of what was uploaded is kept on the object, since the stored bytes are compressed.
HASH_KEY = "sha256"


def stack_output(name: str, stack: str = "afterpass") -> str:
    """One output of the deployed stack, such as DataBucketName."""
    client = boto3.client("cloudformation", region_name=settings().aws_region)
    outputs = client.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == name:
            return output["OutputValue"]
    raise KeyError(f"The {stack} stack has no output called {name}.")


def upload_file(client, bucket: str, path: Path, name: str, known: bool = True) -> int:
    """Publish one file as `public/<name>` unless the bucket already has this content.

    Returns 1 if it was uploaded, 0 if it was unchanged. `known` says whether the object may
    already exist (it saves a request when it cannot).
    """
    key = f"{PREFIX}/{name}"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if known:
        try:
            head = client.head_object(Bucket=bucket, Key=key)
            if head.get("Metadata", {}).get(HASH_KEY) == digest:
                return 0
        except client.exceptions.ClientError:
            pass  # Not there yet.
    extra = {
        "ContentType": CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
        "Metadata": {HASH_KEY: digest},
    }
    body = raw
    if path.suffix in GZIPPED:
        body = gzip.compress(raw, compresslevel=6)
        extra["ContentEncoding"] = "gzip"
    client.put_object(Bucket=bucket, Key=key, Body=body, **extra)
    return 1


def upload_public(
    bucket: str, root: Path = PUBLIC_DIR, log: Callable[[str], None] = lambda _: None
) -> dict:
    """Mirror `root` to `s3://bucket/public/`. Returns counts of what was sent and removed."""
    client = boto3.client("s3", region_name=settings().aws_region)
    existing = set()
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=f"{PREFIX}/"
    ):
        existing.update(item["Key"] for item in page.get("Contents", []))
    files = {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    }
    # The method document is published with the data, where the deployed agent reads it.
    if METHOD_DOC.exists():
        files["METHOD.md"] = METHOD_DOC
    sent = 0
    for name, path in files.items():
        sent += upload_file(client, bucket, path, name, known=f"{PREFIX}/{name}" in existing)
        if sent and sent % 50 == 0:
            log(f"Uploaded {sent} files")
    # Files that are no longer published (an older smoke run, a village dropped from the top 20).
    stale = sorted(existing - {f"{PREFIX}/{name}" for name in files})
    for start in range(0, len(stale), 1000):
        batch = [{"Key": key} for key in stale[start : start + 1000]]
        client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
    return {"uploaded": sent, "unchanged": len(files) - sent, "removed": len(stale)}


def put_firms_key() -> str:
    """Copy the FIRMS key from `.env` into an SSM SecureString. The key is never printed."""
    name = "/afterpass/firms_map_key"
    client = boto3.client("ssm", region_name=settings().aws_region)
    client.put_parameter(
        Name=name, Value=settings().require_firms_key(), Type="SecureString", Overwrite=True
    )
    return name
