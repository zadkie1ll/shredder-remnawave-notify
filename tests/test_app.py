from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import NotificationMessage
from app.security import calculate_signature


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish_once(self, dedupe_key: str, message: NotificationMessage) -> bool:
        self.calls.append((dedupe_key, message))
        return True

    async def ping(self) -> bool:
        return True


def settings() -> Settings:
    return Settings(
        host="0.0.0.0",
        port=8097,
        log_level="info",
        webhook_secret="secret",
        signature_tolerance_seconds=0,
        redis_host="localhost",
        redis_port=6379,
        redis_password=None,
        redis_db=0,
        redis_key_prefix="test-prefix",
        dedupe_ttl_seconds=60,
        vpn_queue="vpn",
        vps_queue="vps",
        service_name="monkey-island-vpn-bot",
        notify_48h_type=None,
        notify_expired_24h_type=None,
    )


def payload(event: str = "user.expired") -> dict:
    return {
        "scope": "user",
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "uuid": "user-uuid",
            "username": "123",
            "telegramId": "456",
            "expireAt": "2026-04-21T10:00:00Z",
        },
    }


def test_webhook_endpoint_publishes_message(monkeypatch):
    app = create_app(settings())
    publisher = FakePublisher()

    with TestClient(app) as client:
        app.state.publisher = publisher
        app.state.handler._publisher = publisher
        body = payload()
        response = client.post(
            "/webhooks/remnawave",
            json=body,
            headers={
                "X-Remnawave-Signature": calculate_signature("secret", body),
                "X-Remnawave-Timestamp": body["timestamp"],
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert publisher.calls[0][1].notification_type == "subscription-expired"


def test_webhook_endpoint_rejects_bad_signature():
    app = create_app(settings())

    with TestClient(app) as client:
        body = payload()
        response = client.post(
            "/webhooks/remnawave",
            json=body,
            headers={
                "X-Remnawave-Signature": "bad",
                "X-Remnawave-Timestamp": body["timestamp"],
            },
        )

    assert response.status_code == 401


def test_webhook_endpoint_returns_ignored_for_unmapped_event():
    app = create_app(settings())

    with TestClient(app) as client:
        body = payload("user.expires_in_48_hours")
        response = client.post(
            "/webhooks/remnawave",
            json=body,
            headers={
                "X-Remnawave-Signature": calculate_signature("secret", body),
                "X-Remnawave-Timestamp": body["timestamp"],
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
