from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from redis.asyncio import Redis

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
