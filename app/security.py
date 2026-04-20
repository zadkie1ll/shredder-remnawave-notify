from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def _canonical_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def calculate_signature(secret: str, body: bytes | Any) -> str:
    if not isinstance(body, bytes):
        body = _canonical_json(body)

    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    signature: str | None,
    raw_body: bytes,
    parsed_body: Any,
) -> bool:
    if not signature:
        return False

    expected_from_parsed = calculate_signature(secret, parsed_body)
    expected_from_raw = calculate_signature(secret, raw_body)

    return hmac.compare_digest(signature, expected_from_parsed) or hmac.compare_digest(
        signature, expected_from_raw
    )


def verify_timestamp(
    header_timestamp: str | None,
    payload_timestamp: datetime,
    tolerance_seconds: int,
) -> bool:
    if tolerance_seconds <= 0:
        return True

    timestamp_to_check = payload_timestamp

    if header_timestamp:
        try:
            timestamp_to_check = datetime.fromisoformat(
                header_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            return False

    if timestamp_to_check.tzinfo is None:
        timestamp_to_check = timestamp_to_check.replace(tzinfo=UTC)

    delta = abs((datetime.now(UTC) - timestamp_to_check.astimezone(UTC)).total_seconds())
    return delta <= tolerance_seconds
