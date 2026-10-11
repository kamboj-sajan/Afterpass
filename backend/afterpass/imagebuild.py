"""Build the pipeline's container image in AWS and return what to deploy.

The backend source is zipped and uploaded (a few hundred KB), CodeBuild builds the image next
to ECR, and the image's digest comes back. Deploying by digest means Lambda always runs
exactly the image that was just built.
"""

from __future__ import annotations

import io
import time
import zipfile
from collections.abc import Callable

import boto3

from afterpass import workdir
from afterpass.config import REPO_ROOT, settings

PROJECT = "afterpass-image"
REPOSITORY = "afterpass"
TAG = "pipeline"
SOURCE_KEY = "deploy/source/backend.zip"
BACKEND = REPO_ROOT / "backend"
# What the Dockerfile copies: nothing else is sent.
SOURCES = (
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "uv.lock",
    "afterpass",
    "agent",
    "lambdas",
)
SKIP = ("__pycache__", ".pyc", "/tests/")


def source_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in SOURCES:
            root = BACKEND / name
            paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
            for path in paths:
                relative = path.relative_to(BACKEND).as_posix()
                if not any(part in f"/{relative}" for part in SKIP):
                    archive.write(path, relative)
    return buffer.getvalue()


def build(log: Callable[[str], None] = lambda _: None) -> str:
    """Upload the source, run the build and return the image URI with its digest."""
    region = settings().aws_region
    bucket = workdir.bucket_name()
    body = source_zip()
    boto3.client("s3", region_name=region).put_object(Bucket=bucket, Key=SOURCE_KEY, Body=body)
    log(f"Uploaded {len(body) / 1e3:.0f} KB of backend source")
    codebuild = boto3.client("codebuild", region_name=region)
    build_id = codebuild.start_build(projectName=PROJECT)["build"]["id"]
    started = time.monotonic()
    while True:
        time.sleep(15)
        run = codebuild.batch_get_builds(ids=[build_id])["builds"][0]
        status = run["buildStatus"]
        if status != "IN_PROGRESS":
            break
        log(
            f"Building: {run.get('currentPhase', '')} ({(time.monotonic() - started) / 60:.1f} min)"
        )
    if status != "SUCCEEDED":
        raise RuntimeError(
            f"The image build ended as {status}. See the /afterpass/image-build logs."
        )
    return image_uri()


def image_uri() -> str:
    """The newest built image, pinned to its digest."""
    region = settings().aws_region
    ecr = boto3.client("ecr", region_name=region)
    found = ecr.describe_images(repositoryName=REPOSITORY, imageIds=[{"imageTag": TAG}])
    detail = found["imageDetails"][0]
    registry = f"{detail['registryId']}.dkr.ecr.{region}.amazonaws.com"
    return f"{registry}/{REPOSITORY}@{detail['imageDigest']}"
