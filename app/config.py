from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _get_optional_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    log_level: str
    webhook_secret: str
    signature_tolerance_seconds: int
    redis_host: str
    redis_port: int
    redis_password: str | None
    redis_db: int
    redis_key_prefix: str
    dedupe_ttl_seconds: int
    vpn_queue: str
    vps_queue: str
    service_name: str
    notify_48h_type: str | None
    notify_expired_24h_type: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        webhook_secret = os.getenv("REMNA_WEBHOOK_SECRET")
        if not webhook_secret:
            raise ValueError("REMNA_WEBHOOK_SECRET environment variable is not set.")

        redis_host = os.getenv("REMNA_REDIS_HOST") or os.getenv("MI_UN_REDIS_HOST")
        if not redis_host:
            raise ValueError(
                "REMNA_REDIS_HOST or MI_UN_REDIS_HOST environment variable is not set."
            )

        redis_port = _get_int(
            "REMNA_REDIS_PORT",
            _get_int("MI_UN_REDIS_PORT", 6379),
        )

        redis_password = _get_optional_str("REMNA_REDIS_PASSWORD")
        if redis_password is None:
            redis_password = _get_optional_str("MI_UN_REDIS_PASSWORD")

        return cls(
            host=os.getenv("REMNA_WEBHOOK_HOST", "0.0.0.0"),
            port=_get_int("REMNA_WEBHOOK_PORT", 8097),
            log_level=os.getenv("REMNA_LOG_LEVEL", "info"),
            webhook_secret=webhook_secret,
            signature_tolerance_seconds=_get_int(
                "REMNA_SIGNATURE_TOLERANCE_SECONDS", 600
            ),
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_db=_get_int("REMNA_REDIS_DB", 0),
            redis_key_prefix=os.getenv(
                "REMNA_REDIS_KEY_PREFIX", "remnawave-webhook-notify"
            ),
            dedupe_ttl_seconds=_get_int("REMNA_DEDUPE_TTL_SECONDS", 60 * 60 * 24 * 45),
            vpn_queue=os.getenv("REMNA_VPN_BOT_QUEUE", "monkey-island-vpn-bot"),
            vps_queue=os.getenv("REMNA_VPS_BOT_QUEUE", "monkey-island-vps-bot"),
            service_name=os.getenv("REMNA_MESSAGE_SERVICE", "monkey-island-vpn-bot"),
            notify_48h_type=_get_optional_str("REMNA_NOTIFY_48H_TYPE"),
            notify_expired_24h_type=_get_optional_str("REMNA_NOTIFY_EXPIRED_24H_TYPE"),
        )
