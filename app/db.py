from __future__ import annotations

from enum import Enum

from sqlalchemy import BigInteger, Boolean, Column, Enum as SQLEnum, ForeignKey, Index, Integer, Sequence, String, TIMESTAMP, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class ReferralType(str, Enum):
    STANDARD = "STANDARD"
    ONLY_REGISTRATIONS = "ONLY_REGISTRATIONS"
    ALL_PAYMENTS_PERCENTAGE = "ALL_PAYMENTS_PERCENTAGE"


class ReferralBonusType(str, Enum):
    REGISTRATION = "REGISTRATION"
    TRAFFIC = "TRAFFIC"
    PURCHASE = "PURCHASE"


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, Sequence("users_id_seq"), primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(256), unique=True, nullable=True)
    referred_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    referral_type = Column(SQLEnum(ReferralType, native_enum=False), nullable=True)
    expire_at = Column(TIMESTAMP)

    __table_args__ = (Index("ix_users_username", "username"),)


class ReferralBonus(Base):
    __tablename__ = "referral_bonuses"

    id = Column(BigInteger, primary_key=True)
    referral_id = Column(BigInteger, ForeignKey("users.id"))
    referrer_id = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    bonus_type = Column(SQLEnum(ReferralBonusType, native_enum=False), nullable=False)
    days_added = Column(Integer)


class UserTrafficProgress(Base):
    __tablename__ = "user_traffic_progress"

    id = Column(BigInteger, Sequence("user_traffic_progress_id_seq"), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    passed_0 = Column(Boolean, default=False, server_default="false", nullable=False)
    passed_5mb = Column(Boolean, default=False, server_default="false", nullable=False)
    passed_100mb = Column(Boolean, default=False, server_default="false", nullable=False)


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(BigInteger, Sequence("event_logs_id_seq"), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(256), nullable=False)
    event_payload = Column(JSONB, nullable=False, default=dict)
    timestamp = Column(TIMESTAMP, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_event_logs_user_id", "user_id"),
        Index("ix_event_logs_event_type", "event_type"),
    )


async def save_traffic_threshold_reached_event_log(
    session: AsyncSession,
    user_id: int,
    threshold: int,
) -> None:
    session.add(
        EventLog(
            user_id=user_id,
            event_type="traffic_threshold_reached",
            event_payload={
                "event_type": "traffic_threshold_reached",
                "threshold": threshold,
            },
        )
    )


async def extend_user_subscription_by_username(
    session: AsyncSession,
    username: str,
    interval,
) -> None:
    extend_expire_at_query = text("""
        UPDATE users
            SET expire_at =
            CASE
                WHEN expire_at > (NOW() AT TIME ZONE 'UTC') THEN expire_at + (:interval)::interval
                ELSE (NOW() AT TIME ZONE 'UTC') + (:interval)::interval
            END
            WHERE username = :username
        """)

    await session.execute(
        extend_expire_at_query,
        {
            "username": username,
            "interval": interval,
        },
    )
