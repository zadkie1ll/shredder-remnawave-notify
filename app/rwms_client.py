from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

import proto.rwmanager_pb2 as proto
import proto.rwmanager_pb2_grpc as proto_grpc


class RwmsClient:
    def __init__(self, addr: str, port: int) -> None:
        options = [("grpc.max_receive_message_length", 300 * 1024 * 1024)]
        self._channel = grpc.aio.insecure_channel(f"{addr}:{port}", options=options)
        self._stub = proto_grpc.RwManagerStub(self._channel)

    async def close(self) -> None:
        await self._channel.close()

    async def get_all_users(self, offset: int, count: int):
        try:
            return await self._stub.GetAllUsers(
                proto.GetAllUsersRequest(offset=offset, count=count)
            )
        except grpc.RpcError as exc:
            logging.getLogger(self.__class__.__name__).error(
                "error getting all RWMS users: %s", exc
            )
            return None

    async def get_user_by_username(self, username: str):
        try:
            return await self._stub.GetUserByUsername(
                proto.GetUserByUsernameRequest(username=username)
            )
        except grpc.RpcError as exc:
            logging.getLogger(self.__class__.__name__).error(
                "error getting RWMS user by username=%s: %s", username, exc
            )
            return None

    async def extend_user_subscription(self, user, days: int):
        expire_at = None
        if user.HasField("expire_at"):
            expire_at = user.expire_at.ToDatetime(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if expire_at is None or expire_at < now:
            expire_at = now

        expire_at = expire_at + timedelta(days=days)
        expire_at_timestamp = Timestamp()
        expire_at_timestamp.FromDatetime(expire_at)

        try:
            return await self._stub.UpdateUser(
                proto.UpdateUserRequest(
                    uuid=user.uuid,
                    expire_at=expire_at_timestamp,
                    status=proto.UserStatus.ACTIVE,
                    traffic_limit_strategy=proto.TrafficLimitStrategy.NO_RESET,
                    active_internal_squads=[
                        squad.uuid for squad in user.active_internal_squads
                    ],
                )
            )
        except (TypeError, ValueError, grpc.RpcError) as exc:
            logging.getLogger(self.__class__.__name__).error(
                "error extending RWMS user username=%s days=%s: %s",
                user.username,
                days,
                exc,
            )
            return None
