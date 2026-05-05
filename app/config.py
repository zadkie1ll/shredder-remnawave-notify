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


def _get_first_optional_str(*names: str) -> str | None:
    for name in names:
        value = _get_optional_str(name)
        if value is not None:
            return value
    return None


def _get_first_int(default: int, *names: str) -> int:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return _get_int(name, default)
    return default


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
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
    notify_not_connected_type: str
    notify_48h_type: str | None
    notify_expired_24h_type: str
    traffic_watcher_enabled: bool = False
    traffic_watcher_interval_seconds: int = 900
    rwms_address: str | None = None
    rwms_port: int | None = None
    pg_host: str | None = None
    pg_port: int = 5432
    pg_user: str | None = None
    pg_password: str | None = None
    pg_db: str | None = None
    ym_stat_queue: str = "monkey-island-ym-stat"

    @classmethod
    def from_env(cls) -> "Settings":
        webhook_secret = os.getenv("REMNA_WEBHOOK_SECRET")
        if not webhook_secret:
            raise ValueError("REMNA_WEBHOOK_SECRET environment variable is not set.")

        redis_host = os.getenv("REMNA_REDIS_HOST")
        if not redis_host:
            raise ValueError("REMNA_REDIS_HOST environment variable is not set.")

        redis_port = _get_int("REMNA_REDIS_PORT", 6379)

        redis_password = _get_optional_str("REMNA_REDIS_PASSWORD")

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
            vpn_queue=os.getenv("REMNA_VPN_BOT_QUEUE", "shredder-vpn-bot"),
            notify_not_connected_type=os.getenv(
                "REMNA_NOTIFY_NOT_CONNECTED_TYPE", "nc-yesterday-created"
            ),
            notify_48h_type=_get_optional_str("REMNA_NOTIFY_48H_TYPE"),
            notify_expired_24h_type=_get_str(
                "REMNA_NOTIFY_EXPIRED_24H_TYPE", "subscription-expired"
            ),
            traffic_watcher_enabled=_get_bool("REMNA_TRAFFIC_WATCHER_ENABLED"),
            traffic_watcher_interval_seconds=_get_int(
                "REMNA_TRAFFIC_WATCHER_INTERVAL_SECONDS", 900
            ),
            rwms_address=_get_first_optional_str("REMNA_RWMS_ADDR", "MI_UN_RWMS_ADDR"),
            rwms_port=(
                _get_first_int(0, "REMNA_RWMS_PORT", "MI_UN_RWMS_PORT")
                if _get_first_optional_str("REMNA_RWMS_PORT", "MI_UN_RWMS_PORT")
                is not None
                else None
            ),
            pg_host=_get_first_optional_str(
                "REMNA_POSTGRES_HOST", "MI_UN_POSTGRES_HOST"
            ),
            pg_port=_get_first_int(5432, "REMNA_POSTGRES_PORT", "MI_UN_POSTGRES_PORT"),
            pg_user=_get_first_optional_str(
                "REMNA_POSTGRES_USER", "MI_UN_POSTGRES_USER"
            ),
            pg_password=_get_first_optional_str(
                "REMNA_POSTGRES_PASSWORD", "MI_UN_POSTGRES_PASSWORD"
            ),
            pg_db=_get_first_optional_str("REMNA_POSTGRES_DB", "MI_UN_POSTGRES_DB"),
            ym_stat_queue=_get_str(
                "REMNA_YM_STAT_QUEUE",
                os.getenv("MI_UN_YM_STAT_QUEUE_NAME", "monkey-island-ym-stat"),
            ),
        )

    def has_postgres_settings(self) -> bool:
        return all(
            value not in (None, "")
            for value in (
                self.pg_host,
                self.pg_user,
                self.pg_password,
                self.pg_db,
            )
        )

    def require_traffic_watcher_settings(self) -> None:
        if not self.traffic_watcher_enabled:
            return

        missing = [
            name
            for name, value in {
                "REMNA_RWMS_ADDR": self.rwms_address,
                "REMNA_RWMS_PORT": self.rwms_port,
                "REMNA_POSTGRES_HOST": self.pg_host,
                "REMNA_POSTGRES_USER": self.pg_user,
                "REMNA_POSTGRES_PASSWORD": self.pg_password,
                "REMNA_POSTGRES_DB": self.pg_db,
            }.items()
            if value in (None, "", 0)
        ]
        if missing:
            raise ValueError(
                "Traffic watcher is enabled, but required environment variables are missing: "
                + ", ".join(missing)
            )
