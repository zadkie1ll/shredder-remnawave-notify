# Remnawave Webhook Notify

Separate webhook-based replacement for the old polling notification module.
It does not read Postgres. Remnawave sends user subscription events, this service
verifies the webhook, maps the event to the existing bot message contract and
pushes the JSON message into Redis.

## Event mapping

| Remnawave event | Redis `notification_type` | Default |
| --- | --- | --- |
| `user.expires_in_72_hours` | `3-days-left` | sent |
| `user.expires_in_24_hours` | `1-day-left` | sent |
| `user.expired` | `subscription-expired` | sent |
| `user.expires_in_48_hours` | `REMNA_NOTIFY_48H_TYPE` | ignored |
| `user.expired_24_hours_ago` | `REMNA_NOTIFY_EXPIRED_24H_TYPE` | ignored |

The 48 hour and expired-after-24-hours webhooks are ignored by default because
the current bot contract only has known templates for 3 days, 1 day and expired.

## Redis message contract

The service pushes the same shape the old module used:

```json
{"service":"monkey-island-vpn-bot","type":"notificate-user","notification_type":"1-day-left","telegram_id":123456789}
```

By default the message is pushed to both queues:

```text
monkey-island-vpn-bot
monkey-island-vps-bot
```

## Idempotency

Remnawave may retry webhooks. The service writes through a Redis Lua script:
it sets a dedupe key and pushes to both bot queues atomically. The key includes
event, Telegram ID and `expireAt`, so the same user can be notified again after
a future renewal creates a new expiration date.

Default dedupe TTL is 45 days: `REMNA_DEDUPE_TTL_SECONDS=3888000`.

## Run locally

```bash
cd remnawave_webhook_notify
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
python -m app.main
```

The app listens on `0.0.0.0:8097` by default.

## Production

Build and run only this folder:

```bash
cd remnawave_webhook_notify
cp .env.example .env
docker compose up -d --build
```

Use Caddy as the public HTTPS entry point and proxy to the internal service port.
Ports `443` and `8443` do not need to be used by this service. The compose file
binds the service to `127.0.0.1:8097`, so it is available to Caddy on the host
but is not exposed directly to the public internet.

Example:

```caddyfile
notify.example.com {
    reverse_proxy 127.0.0.1:8097
}
```

Set Remnawave:

```env
WEBHOOK_ENABLED=true
WEBHOOK_URL=https://notify.example.com/webhooks/remnawave
WEBHOOK_SECRET_HEADER=<same value as REMNA_WEBHOOK_SECRET>
```

Check the service:

```bash
docker compose ps
docker compose logs -f remnawave-webhook-notify
curl http://127.0.0.1:8097/health
curl http://127.0.0.1:8097/ready
```

## Health checks

```text
GET /health
GET /ready
POST /webhooks/remnawave
```

`/ready` checks Redis connectivity.
