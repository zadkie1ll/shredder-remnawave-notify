from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RemnawaveUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: str | None = None
    subscription_uuid: str | None = Field(default=None, alias="subscriptionUuid")
    username: str | None = None
    telegram_id: str | None = Field(default=None, alias="telegramId")
    expire_at: datetime | None = Field(default=None, alias="expireAt")
    email: str | None = None


class RemnawaveWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    event: str
    timestamp: datetime
    data: dict[str, Any]


class NotificationMessage(BaseModel):
    service: str
    type: Literal["notificate-user"] = "notificate-user"
    notification_type: str
    telegram_id: int


class PublishResult(BaseModel):
    published: bool
    dedupe_key: str
    notification_type: str
    telegram_id: int
