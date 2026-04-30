from __future__ import annotations

import logging
from datetime import UTC

from pydantic import ValidationError

from app.config import Settings
from app.models import NotificationMessage, PublishResult, RemnawaveUser, RemnawaveWebhook
from app.publisher import RedisNotificationPublisher


class WebhookIgnored(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RemnawaveWebhookHandler:
    def __init__(
        self,
        settings: Settings,
        publisher: RedisNotificationPublisher,
    ) -> None:
        self._settings = settings
        self._publisher = publisher
        self._logger = logging.getLogger(self.__class__.__name__)

    async def handle(self, webhook: RemnawaveWebhook) -> PublishResult:
        notification_type = self._notification_type_for_event(webhook.event)
        if notification_type is None:
            raise WebhookIgnored(f"event {webhook.event!r} is not mapped")

        if webhook.scope != "user":
            raise WebhookIgnored(f"scope {webhook.scope!r} is not handled")

        try:
            user = RemnawaveUser.model_validate(webhook.data)
        except ValidationError as exc:
            raise WebhookIgnored("user payload is invalid") from exc

        telegram_id = self._extract_telegram_id(user)
        if telegram_id is None:
            raise WebhookIgnored("telegram id is missing")

        message = NotificationMessage(
            service=self._settings.service_name,
            notification_type=notification_type,
            telegram_id=telegram_id,
        )
        dedupe_key = self._dedupe_key(webhook, user, telegram_id)
        published = await self._publisher.publish_once(dedupe_key, message)

        return PublishResult(
            published=published,
            dedupe_key=dedupe_key,
            notification_type=notification_type,
            telegram_id=telegram_id,
        )

    def _notification_type_for_event(self, event: str) -> str | None:
        mapping = {
            "user.expires_in_72_hours": "3-days-left",
            "user.expires_in_24_hours": "1-day-left",
            "user.expired": "subscription-expired",
            "user.not_connected": self._settings.notify_not_connected_type,
            "user.expires_in_48_hours": self._settings.notify_48h_type,
            "user.expired_24_hours_ago": self._settings.notify_expired_24h_type,
        }
        return mapping.get(event)

    @staticmethod
    def _extract_telegram_id(user: RemnawaveUser) -> int | None:
        for candidate in (user.telegram_id, user.username):
            if candidate is None:
                continue

            stripped = str(candidate).strip()
            if stripped.isdecimal():
                return int(stripped)

        return None

    def _dedupe_key(
        self,
        webhook: RemnawaveWebhook,
        user: RemnawaveUser,
        telegram_id: int,
    ) -> str:
        expire_at = user.expire_at
        if expire_at is not None:
            if expire_at.tzinfo is None:
                expire_at = expire_at.replace(tzinfo=UTC)
            period_marker = expire_at.astimezone(UTC).isoformat()
        else:
            period_marker = webhook.timestamp.date().isoformat()

        return (
            f"{self._settings.redis_key_prefix}:sent:"
            f"{webhook.event}:{telegram_id}:{period_marker}"
        )
