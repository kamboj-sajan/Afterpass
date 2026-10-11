"""Build the frontend against the deployed stack and upload it to Amplify Hosting.

No repository is connected to the Amplify app: this is the deploy step. The frontend's settings
(data URL, agent URL, map key) are read from the stack, never typed in.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import boto3
import httpx

from afterpass import s3
from afterpass.config import REPO_ROOT, settings

FRONTEND = REPO_ROOT / "frontend"
ENV_FILE = FRONTEND / ".env.production.local"
BRANCH = "main"


def frontend_env() -> dict[str, str]:
    """The Vite variables for a production build, from the stack's outputs."""
    region = settings().aws_region
    key_name = s3.stack_output("MapsKeyName")
    key = boto3.client("location", region_name=region).describe_key(KeyName=key_name)["Key"]
    env = {
        "VITE_DATA_BASE_URL": s3.stack_output("DataUrl"),
        "VITE_AGENT_URL": s3.stack_output("AgentUrl").rstrip("/"),
        "VITE_LOCATION_KEY": key,
        "VITE_AWS_REGION": region,
    }
    # The alerts may not be deployed yet; the form is hidden without this address.
    with contextlib.suppress(KeyError):
        env["VITE_SUBSCRIBE_URL"] = s3.stack_output("SubscribeUrl").rstrip("/")
    return env


def build(log: Callable[[str], None] = lambda _: None) -> Path:
    """Write the build settings and run the production build. Returns the `dist` folder."""
    env = frontend_env()
    ENV_FILE.write_text("".join(f"{name}={value}\n" for name, value in env.items()))
    log(f"Building the frontend for {env['VITE_DATA_BASE_URL']}")
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True, capture_output=True)
    return FRONTEND / "dist"


def deploy(dist: Path, log: Callable[[str], None] = lambda _: None) -> str:
    """Upload a built frontend to Amplify and wait until it is live. Returns its address."""
    client = boto3.client("amplify", region_name=settings().aws_region)
    app_id = s3.stack_output("WebAppId")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in dist.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(dist).as_posix())
    log(f"Uploading {buffer.tell() / 1e6:.1f} MB to Amplify")
    job = client.create_deployment(appId=app_id, branchName=BRANCH)
    httpx.put(job["zipUploadUrl"], content=buffer.getvalue(), timeout=600).raise_for_status()
    client.start_deployment(appId=app_id, branchName=BRANCH, jobId=job["jobId"])
    for _ in range(90):
        job_now = client.get_job(appId=app_id, branchName=BRANCH, jobId=job["jobId"])
        status = job_now["job"]["summary"]["status"]
        if status == "SUCCEED":
            return s3.stack_output("WebUrl")
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"The Amplify deployment ended as {status}.")
        time.sleep(4)
    raise RuntimeError("The Amplify deployment did not finish in six minutes.")
