from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import ValidationError
from redis.asyncio import Redis

from app.config import Settings
from app.handler import RemnawaveWebhookHandler, WebhookIgnored
from app.models import RemnawaveWebhook
from app.publisher import RedisNotificationPublisher
from app.security import verify_signature, verify_timestamp


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            decode_responses=True,
        )
        publisher = RedisNotificationPublisher(
            redis=redis,
            queues=[settings.vpn_queue, settings.vps_queue],
            dedupe_ttl_seconds=settings.dedupe_ttl_seconds,
        )
        app.state.settings = settings
        app.state.redis = redis
        app.state.publisher = publisher
        app.state.handler = RemnawaveWebhookHandler(settings, publisher)
        logging.getLogger("startup").info(
            "started Remnawave webhook notify on %s:%s, Redis %s:%s/%s",
            settings.host,
            settings.port,
            settings.redis_host,
            settings.redis_port,
            settings.redis_db,
        )
        try:
            yield
        finally:
            await redis.aclose()

    app = FastAPI(
        title="Remnawave Webhook Notify",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, str]:
        ok = await request.app.state.publisher.ping()
        if not ok:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return {"status": "ready"}

    @app.post("/webhooks/remnawave")
    async def remnawave_webhook(
        request: Request,
        x_remnawave_signature: str | None = Header(default=None),
        x_remnawave_timestamp: str | None = Header(default=None),
    ) -> dict[str, Any]:
        raw_body = await request.body()

        try:
            parsed_body = json.loads(raw_body)
            webhook = RemnawaveWebhook.model_validate(parsed_body)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid webhook payload",
            ) from exc

        settings = request.app.state.settings

        if not verify_signature(
            secret=settings.webhook_secret,
            signature=x_remnawave_signature,
            raw_body=raw_body,
            parsed_body=parsed_body,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid webhook signature",
            )

        if not verify_timestamp(
            header_timestamp=x_remnawave_timestamp,
            payload_timestamp=webhook.timestamp,
            tolerance_seconds=settings.signature_tolerance_seconds,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="webhook timestamp is outside tolerance",
            )

        try:
            result = await request.app.state.handler.handle(webhook)
        except WebhookIgnored as exc:
            logging.getLogger("webhook").info("ignored webhook: %s", exc.reason)
            return {"status": "ignored", "reason": exc.reason}

        return {"status": "ok", **result.model_dump()}

    return app


if __name__ == "__main__":
    import uvicorn

    runtime_settings = Settings.from_env()
    uvicorn.run(
        create_app(runtime_settings),
        host=runtime_settings.host,
        port=runtime_settings.port,
        log_level=runtime_settings.log_level,
    )
