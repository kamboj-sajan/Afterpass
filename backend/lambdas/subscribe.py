"""The "Notify me" endpoint (brief §11.6): subscribes an email to one Delhi zone's alerts.

SNS sends its own confirmation email, so nobody is subscribed without clicking it. Only the
email and the zone are kept, by SNS; nothing else is stored.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time

import boto3

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$")
ZONES = {
    "Central",
    "East",
    "New Delhi",
    "North",
    "North East",
    "North West",
    "Shahdara",
    "South",
    "South East",
    "South West",
    "West",
}
REQUESTS_PER_HOUR = 5
WINDOW_S = 3600


def _respond(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload),
    }


def _allowed(address: str) -> bool:
    """A few sign-ups an hour per address, so the form cannot be used to flood an inbox."""
    bucket = int(time.time()) // WINDOW_S
    key = hashlib.sha256(f"subscribe:{os.environ['RATE_LIMIT_SALT']}:{address}:{bucket}".encode())
    result = (
        boto3.resource("dynamodb")
        .Table(os.environ["RATE_LIMIT_TABLE"])
        .update_item(
            Key={"pk": key.hexdigest()[:32]},
            UpdateExpression="ADD hits :one SET expires = if_not_exists(expires, :expires)",
            ExpressionAttributeValues={":one": 1, ":expires": (bucket + 2) * WINDOW_S},
            ReturnValues="UPDATED_NEW",
        )
    )
    return int(result["Attributes"]["hits"]) <= REQUESTS_PER_HOUR


def handler(event: dict, _context: object) -> dict:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "replace")
    try:
        request = json.loads(body)
        email = str(request.get("email", "")).strip()
        zone = str(request.get("zone", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        return _respond(400, {"error": "bad_request"})
    if not EMAIL.match(email) or len(email) > 254:
        return _respond(400, {"error": "bad_email"})
    if zone not in ZONES:
        return _respond(400, {"error": "bad_zone"})
    address = event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown")
    if not _allowed(address):
        return _respond(429, {"error": "rate_limited"})
    boto3.client("sns").subscribe(
        TopicArn=os.environ["ALERT_TOPIC"],
        Protocol="email",
        Endpoint=email,
        Attributes={"FilterPolicy": json.dumps({"zone": [zone]})},
    )
    return _respond(200, {"status": "confirmation_sent", "zone": zone})
