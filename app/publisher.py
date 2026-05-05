from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from redis.asyncio import Redis

from app.messages import ReferralReachedTrafficBonusApplied, SendConversionMessage
from app.models import NotificationMessage


PUBLISH_ONCE_SCRIPT = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
  for i = 2, #KEYS do
    redis.call('RPUSH', KEYS[i], ARGV[2])
  end
  return 1
end
return 0
"""


class RedisNotificationPublisher:
    def __init__(
        self,
        redis: Redis,
        queues: Sequence[str],
        dedupe_ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._queues = list(queues)
        self._dedupe_ttl_seconds = dedupe_ttl_seconds
        self._logger = logging.getLogger(self.__class__.__name__)

    async def publish_once(
        self,
        dedupe_key: str,
        message: NotificationMessage,
    ) -> bool:
        payload = json.dumps(
            message.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        keys = [dedupe_key, *self._queues]
        result = await self._redis.eval(
            PUBLISH_ONCE_SCRIPT,
            len(keys),
            *keys,
            self._dedupe_ttl_seconds,
            payload,
        )

        published = bool(result)
        if published:
            self._logger.info(
                "published %s notification for telegram_id=%s",
                message.notification_type,
                message.telegram_id,
            )
        else:
            self._logger.info("skipped duplicate webhook dedupe_key=%s", dedupe_key)

        return published

    async def ping(self) -> bool:
        return bool(await self._redis.ping())


class RedisConversionPublisher:
    def __init__(self, redis: Redis, queue: str) -> None:
        self._redis = redis
        self._queue = queue
        self._logger = logging.getLogger(self.__class__.__name__)

    async def publish_conversion(self, message: SendConversionMessage) -> None:
        payload = json.dumps(
            message.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        queue_size = await self._redis.rpush(self._queue, payload)
        self._logger.info(
            "published conversion event=%s client_id=%s queue=%s queue_size=%s",
            message.event.value,
            message.client_id,
            self._queue,
            queue_size,
        )


class RedisBotPublisher:
    def __init__(self, redis: Redis, queue: str) -> None:
        self._redis = redis
        self._queue = queue
        self._logger = logging.getLogger(self.__class__.__name__)

    async def publish_referral_traffic_bonus(
        self,
        message: ReferralReachedTrafficBonusApplied,
    ) -> None:
        payload = json.dumps(
            message.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        queue_size = await self._redis.rpush(self._queue, payload)
        self._logger.info(
            "published referral traffic bonus telegram_id=%s count=%s queue=%s queue_size=%s",
            message.telegram_id,
            message.referral_reached_traffic_count,
            self._queue,
            queue_size,
        )
