from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ConversionEvent(str, Enum):
    HAS_TRAFFIC = "has-traffic"
    HAS_TRAFFIC_MORE_THAN_5MB = "has-traffic-more-than-5mb"
    HAS_TRAFFIC_MORE_THAN_100MB = "has-traffic-more-than-100mb"


class SendConversionMessage(BaseModel):
    service: Literal["monkey-island-ym-stat"] = "monkey-island-ym-stat"
    type: Literal["send-conversion"] = "send-conversion"
    client_id: str
    event: ConversionEvent


class ReferralReachedTrafficBonusApplied(BaseModel):
    service: Literal["monkey-island-vpn-bot"] = "monkey-island-vpn-bot"
    type: Literal["standard-ref-referral-traffic-reached"] = (
        "standard-ref-referral-traffic-reached"
    )
    notification_type: Literal["referral_traffic_reached_bonus_applied"] = (
        "referral_traffic_reached_bonus_applied"
    )
    telegram_id: int
    referral_reached_traffic_count: int
    bonus_days_count: int
