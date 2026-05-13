from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import (
    ReferralBonus,
    ReferralBonusType,
    ReferralType,
    User,
    UserTrafficProgress,
    extend_user_subscription_by_username,
    save_traffic_threshold_reached_event_log,
)
from app.messages import (
    ConversionEvent,
    ReferralReachedTrafficBonusApplied,
    SendConversionMessage,
)
from app.publisher import RedisBotPublisher, RedisConversionPublisher
from app.rwms_client import RwmsClient


K5MB = 5 * 1024 * 1024
K100MB = 100 * 1024 * 1024


@dataclass(frozen=True)
class TrafficThreshold:
    column: str
    event: ConversionEvent
    event_log_threshold: int
    bytes_threshold: int


THRESHOLDS = (
    TrafficThreshold(
        column="passed_0",
        event=ConversionEvent.HAS_TRAFFIC,
        event_log_threshold=0,
        bytes_threshold=0,
    ),
    TrafficThreshold(
        column="passed_5mb",
        event=ConversionEvent.HAS_TRAFFIC_MORE_THAN_5MB,
        event_log_threshold=5,
        bytes_threshold=K5MB,
    ),
    TrafficThreshold(
        column="passed_100mb",
        event=ConversionEvent.HAS_TRAFFIC_MORE_THAN_100MB,
        event_log_threshold=100,
        bytes_threshold=K100MB,
    ),
)


@dataclass(frozen=True)
class UserProgress:
    user_id: int
    passed_0: bool
    passed_5mb: bool
    passed_100mb: bool


@dataclass(frozen=True)
class ConversionToSend:
    username: str
    user_id: int
    event: ConversionEvent
    event_log_threshold: int


class TrafficProgressWatcher:
    def __init__(
        self,
        session_maker: async_sessionmaker,
        rwms_client: RwmsClient,
        conversion_publisher: RedisConversionPublisher,
        bot_publisher: RedisBotPublisher,
    ) -> None:
        self._session_maker = session_maker
        self._rwms_client = rwms_client
        self._conversion_publisher = conversion_publisher
        self._bot_publisher = bot_publisher
        self._log = logging.getLogger(self.__class__.__name__)

    async def run_forever(self, interval_seconds: int) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception("traffic watcher iteration failed")

            await asyncio.sleep(interval_seconds)

    async def run_once(self) -> None:
        self._log.info("checking user traffic progress")
        rwms_users = await self._get_all_rwms_users()
        if not rwms_users:
            self._log.warning("RWMS returned no users; skipping traffic check")
            return

        async with self._session_maker() as session:
            progress_by_username = await self._get_users_progress(session)

        updates = []
        conversions = []
        referrals_reached_100mb = []

        for rwms_user in rwms_users:
            progress = progress_by_username.get(rwms_user.username)
            if progress is None:
                continue

            traffic = getattr(rwms_user, "lifetime_used_traffic_bytes", 0)
            for threshold in THRESHOLDS:
                already_passed = getattr(progress, threshold.column)
                if traffic > threshold.bytes_threshold and not already_passed:
                    updates.append((progress.user_id, threshold.column))
                    conversions.append(
                        ConversionToSend(
                            username=rwms_user.username,
                            user_id=progress.user_id,
                            event=threshold.event,
                            event_log_threshold=threshold.event_log_threshold,
                        )
                    )
                    if threshold.column == "passed_100mb":
                        referrals_reached_100mb.append(progress.user_id)

        if not updates:
            self._log.info("no new traffic progress updates")
            return

        async with self._session_maker() as session:
            async with session.begin():
                for user_id, column in updates:
                    await session.execute(
                        update(UserTrafficProgress)
                        .where(UserTrafficProgress.user_id == user_id)
                        .values({column: True})
                    )

                for conversion in conversions:
                    await save_traffic_threshold_reached_event_log(
                        session=session,
                        user_id=conversion.user_id,
                        threshold=conversion.event_log_threshold,
                    )

                bonus_result = await self._add_referral_traffic_bonuses_if_needed(
                    session=session,
                    user_ids=referrals_reached_100mb,
                )

        for conversion in conversions:
            await self._conversion_publisher.publish_conversion(
                SendConversionMessage(
                    client_id=conversion.username,
                    event=conversion.event,
                )
            )

        for referrer_tg_id, referral_count in bonus_result.items():
            await self._bot_publisher.publish_referral_traffic_bonus(
                ReferralReachedTrafficBonusApplied(
                    telegram_id=referrer_tg_id,
                    referral_reached_traffic_count=referral_count,
                    bonus_days_count=referral_count * 10,
                )
            )

        self._log.info(
            "updated traffic progress: updates=%s conversions=%s",
            len(updates),
            len(conversions),
        )

    async def _add_referral_traffic_bonuses_if_needed(
        self,
        session,
        user_ids: list[int],
    ) -> dict[int, int]:
        if not user_ids:
            return {}

        referrals_result = await session.execute(
            select(User.id, User.referred_by_id)
            .where(User.id.in_(user_ids))
            .where(User.referral_type == ReferralType.STANDARD)
            .where(User.referred_by_id.isnot(None))
        )
        referral_data = [(row[0], row[1]) for row in referrals_result.all()]
        if not referral_data:
            return {}

        existing_bonuses = await session.execute(
            select(ReferralBonus.referral_id)
            .where(ReferralBonus.referral_id.in_([row[0] for row in referral_data]))
            .where(ReferralBonus.bonus_type == ReferralBonusType.TRAFFIC)
        )
        existing_referral_ids = set(existing_bonuses.scalars().all())

        referrals_by_referrer = {}
        for referral_id, referrer_id in referral_data:
            if referral_id in existing_referral_ids:
                continue
            referrals_by_referrer.setdefault(referrer_id, []).append(referral_id)

        if not referrals_by_referrer:
            return {}

        referrers_result = await session.execute(
            select(User.id, User.username, User.telegram_id).where(
                User.id.in_(referrals_by_referrer.keys())
            )
        )
        referrer_data = {
            user_id: (username, telegram_id)
            for user_id, username, telegram_id in referrers_result.all()
        }

        bonus_result = {}
        for referrer_id, referral_ids in referrals_by_referrer.items():
            referrer_info = referrer_data.get(referrer_id)
            if referrer_info is None:
                self._log.warning("not found referrer id=%s", referrer_id)
                continue

            referrer_username, referrer_tg_id = referrer_info
            referrer_sub = await self._rwms_client.get_user_by_username(
                referrer_username
            )
            if referrer_sub is None:
                self._log.warning(
                    "not found RWMS subscription for referrer username=%s",
                    referrer_username,
                )
                continue

            bonus_days = len(referral_ids) * 10
            rwms_update = await self._rwms_client.extend_user_subscription(
                user=referrer_sub,
                days=bonus_days,
            )
            if rwms_update is None:
                self._log.warning(
                    "skipped referral traffic bonus because RWMS extension failed "
                    "referrer_username=%s bonus_days=%s",
                    referrer_username,
                    bonus_days,
                )
                continue

            await extend_user_subscription_by_username(
                session=session,
                username=referrer_username,
                interval=timedelta(days=bonus_days),
            )
            for referral_id in referral_ids:
                session.add(
                    ReferralBonus(
                        referral_id=referral_id,
                        referrer_id=referrer_id,
                        bonus_type=ReferralBonusType.TRAFFIC,
                        days_added=10,
                    )
                )

            bonus_result[referrer_tg_id] = (
                bonus_result.get(referrer_tg_id, 0) + len(referral_ids)
            )

        return bonus_result

    async def _get_all_rwms_users(self):
        offset = 0
        count = 1000
        users = []

        while True:
            response = await self._rwms_client.get_all_users(offset=offset, count=count)
            if response is None:
                return []

            users.extend(response.users)
            fetched = len(response.users)
            if fetched == 0:
                break

            offset += fetched
            total = int(getattr(response, "total", 0) or 0)
            if total > 0 and offset >= total:
                break

        return users

    @staticmethod
    async def _get_users_progress(session) -> dict[str, UserProgress]:
        result = await session.execute(
            select(
                User.username,
                UserTrafficProgress.user_id,
                UserTrafficProgress.passed_0,
                UserTrafficProgress.passed_5mb,
                UserTrafficProgress.passed_100mb,
            ).join(User, User.id == UserTrafficProgress.user_id)
        )

        return {
            username: UserProgress(
                user_id=user_id,
                passed_0=passed_0,
                passed_5mb=passed_5mb,
                passed_100mb=passed_100mb,
            )
            for username, user_id, passed_0, passed_5mb, passed_100mb in result.all()
            if username is not None
        }
