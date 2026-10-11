"""A simple per-address limit on questions (brief §10.5): a counter in DynamoDB that expires.

The address is stored only as a salted hash, in hour-long buckets, and removed by DynamoDB's
time-to-live an hour after its bucket ends.
"""

from __future__ import annotations

import hashlib
import os
import time

LIMIT_PER_HOUR = 20
WINDOW_S = 3600


def _key(address: str, bucket: int) -> str:
    salt = os.environ.get("RATE_LIMIT_SALT", "afterpass")
    return hashlib.sha256(f"{salt}:{address}:{bucket}".encode()).hexdigest()[:32]


def allow(address: str, table, now: float | None = None) -> bool:
    """Count one question from `address`; False once it has asked more than the limit this hour.

    `table` is a boto3 DynamoDB Table (or anything with the same `update_item`).
    """
    bucket = int(now if now is not None else time.time()) // WINDOW_S
    result = table.update_item(
        Key={"pk": _key(address, bucket)},
        UpdateExpression="ADD hits :one SET expires = if_not_exists(expires, :expires)",
        ExpressionAttributeValues={":one": 1, ":expires": (bucket + 2) * WINDOW_S},
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["hits"]) <= LIMIT_PER_HOUR
