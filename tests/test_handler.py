from dataclasses import replace
from datetime import datetime

import pytest

from app.config import Settings
from app.handler import RemnawaveWebhookHandler, WebhookIgnored
from app.models import NotificationMessage, RemnawaveWebhook


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish_once(self, dedupe_key: str, message: NotificationMessage) -> bool:
        self.calls.append((dedupe_key, message))
        return True


@pytest.fixture()
def settings():
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


def webhook(event: str, telegram_id: str | None = "123456") -> RemnawaveWebhook:
    return RemnawaveWebhook.model_validate(
        {
            "scope": "user",
            "event": event,
            "timestamp": "2026-04-20T10:00:00Z",
            "data": {
                "uuid": "user-uuid",
                "username": "fallback-username",
                "telegramId": telegram_id,
                "expireAt": "2026-04-21T10:00:00Z",
            },
        }
    )


@pytest.mark.asyncio
async def test_72h_event_publishes_3_days_left(settings):
    publisher = FakePublisher()
    handler = RemnawaveWebhookHandler(settings, publisher)

    result = await handler.handle(webhook("user.expires_in_72_hours"))

    assert result.published is True
    assert result.notification_type == "3-days-left"
    assert publisher.calls[0][1].model_dump() == {
        "service": "monkey-island-vpn-bot",
        "type": "notificate-user",
        "notification_type": "3-days-left",
        "telegram_id": 123456,
    }
    assert publisher.calls[0][0] == (
        "test-prefix:sent:user.expires_in_72_hours:"
        "123456:2026-04-21T10:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_24h_event_publishes_1_day_left(settings):
    publisher = FakePublisher()
    handler = RemnawaveWebhookHandler(settings, publisher)

    result = await handler.handle(webhook("user.expires_in_24_hours"))

    assert result.notification_type == "1-day-left"


@pytest.mark.asyncio
async def test_expired_event_publishes_subscription_expired(settings):
    publisher = FakePublisher()
    handler = RemnawaveWebhookHandler(settings, publisher)

    result = await handler.handle(webhook("user.expired"))

    assert result.notification_type == "subscription-expired"


@pytest.mark.asyncio
async def test_48h_event_is_ignored_by_default(settings):
    handler = RemnawaveWebhookHandler(settings, FakePublisher())

    with pytest.raises(WebhookIgnored):
        await handler.handle(webhook("user.expires_in_48_hours"))


@pytest.mark.asyncio
async def test_48h_event_can_be_enabled(settings):
    settings = replace(settings, notify_48h_type="2-days-left")
    publisher = FakePublisher()
    handler = RemnawaveWebhookHandler(settings, publisher)

    result = await handler.handle(webhook("user.expires_in_48_hours"))

    assert result.notification_type == "2-days-left"


@pytest.mark.asyncio
async def test_username_is_used_as_fallback_telegram_id(settings):
    payload = webhook("user.expired", telegram_id=None)
    payload.data["username"] = "777"
    publisher = FakePublisher()
    handler = RemnawaveWebhookHandler(settings, publisher)

    result = await handler.handle(payload)

    assert result.telegram_id == 777


@pytest.mark.asyncio
async def test_missing_telegram_id_is_ignored(settings):
    handler = RemnawaveWebhookHandler(settings, FakePublisher())

    with pytest.raises(WebhookIgnored):
        await handler.handle(webhook("user.expired", telegram_id=None))
