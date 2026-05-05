from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import User, UserTrafficProgress, save_traffic_threshold_reached_event_log
from app.messages import ConversionEvent, SendConversionMessage
from app.models import RemnawaveUser
from app.publisher import RedisConversionPublisher


class FirstConnectionResult(BaseModel):
    recorded: bool
    reason: str | None = None
    user_id: int | None = None
    username: str | None = None


class FirstConnectionRecorder:
    def __init__(
        self,
        session_maker: async_sessionmaker,
        conversion_publisher: RedisConversionPublisher,
    ) -> None:
        self._session_maker = session_maker
        self._conversion_publisher = conversion_publisher
        self._log = logging.getLogger(self.__class__.__name__)

    async def record(self, remnawave_user: RemnawaveUser) -> FirstConnectionResult:
        telegram_id = self._extract_telegram_id(remnawave_user)
        username = str(remnawave_user.username) if remnawave_user.username else None

        if telegram_id is None and username is None:
            return FirstConnectionResult(recorded=False, reason="user identity missing")

        async with self._session_maker() as session:
            async with session.begin():
                user = await self._find_user(
                    session=session,
                    telegram_id=telegram_id,
                    username=username,
                )
                if user is None:
                    self._log.warning(
                        "first_connected webhook user not found telegram_id=%s username=%s",
                        telegram_id,
                        username,
                    )
                    return FirstConnectionResult(
                        recorded=False,
                        reason="user not found",
                    )

                progress = await self._get_or_create_progress(
                    session=session,
                    user_id=user.id,
                )
                if progress.passed_0:
                    return FirstConnectionResult(
                        recorded=False,
                        reason="already recorded",
                        user_id=user.id,
                        username=user.username,
                    )

                progress.passed_0 = True
                await save_traffic_threshold_reached_event_log(
                    session=session,
                    user_id=user.id,
                    threshold=0,
                )

        await self._conversion_publisher.publish_conversion(
            SendConversionMessage(
                client_id=user.username,
                event=ConversionEvent.HAS_TRAFFIC,
            )
        )

        self._log.info(
            "recorded first connection user_id=%s username=%s",
            user.id,
            user.username,
        )
        return FirstConnectionResult(
            recorded=True,
            user_id=user.id,
            username=user.username,
        )

    @staticmethod
    def _extract_telegram_id(user: RemnawaveUser) -> int | None:
        for candidate in (user.telegram_id, user.username):
            if candidate is None:
                continue
            value = str(candidate).strip()
            if value.isdecimal():
                return int(value)
        return None

    @staticmethod
    async def _find_user(session, telegram_id: int | None, username: str | None):
        filters = []
        if telegram_id is not None:
            filters.append(User.telegram_id == telegram_id)
        if username is not None:
            filters.append(User.username == username)

        result = await session.execute(select(User).where(or_(*filters)).limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_or_create_progress(session, user_id: int) -> UserTrafficProgress:
        result = await session.execute(
            select(UserTrafficProgress).where(UserTrafficProgress.user_id == user_id)
        )
        progress = result.scalar_one_or_none()
        if progress is not None:
            return progress

        progress = UserTrafficProgress(
            user_id=user_id,
            passed_0=False,
            passed_5mb=False,
            passed_100mb=False,
        )
        session.add(progress)
        return progress
