from datetime import UTC, datetime, timedelta

from app.security import calculate_signature, verify_signature, verify_timestamp


def test_verify_signature_accepts_canonical_json_body():
    secret = "secret"
    parsed = {
        "scope": "user",
        "event": "user.expired",
        "timestamp": "2026-04-20T10:00:00Z",
        "data": {"telegramId": "123"},
    }
    raw = b'{\n  "scope": "user", "event": "user.expired"}'
    signature = calculate_signature(secret, parsed)

    assert verify_signature(secret, signature, raw, parsed)


def test_verify_signature_rejects_wrong_secret():
    parsed = {"event": "user.expired"}
    signature = calculate_signature("secret", parsed)

    assert not verify_signature("other-secret", signature, b"{}", parsed)


def test_verify_timestamp_rejects_old_timestamp():
    old_timestamp = datetime.now(UTC) - timedelta(hours=2)

    assert not verify_timestamp(None, old_timestamp, tolerance_seconds=600)


def test_verify_timestamp_can_be_disabled():
    old_timestamp = datetime.now(UTC) - timedelta(days=10)

    assert verify_timestamp(None, old_timestamp, tolerance_seconds=0)
