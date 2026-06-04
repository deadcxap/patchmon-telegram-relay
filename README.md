# patchmon-telegram-relay

A minimal webhook relay that forwards [PatchMon](https://github.com/PatchMon/PatchMon) notifications to a Telegram chat.

PatchMon's webhook destination sends its own JSON payload. This relay receives it, formats a human-readable message, and calls the Telegram Bot API.

## Prerequisites

- Docker + Docker Compose
- A running PatchMon instance (same Docker host)
- A Telegram bot token — create one via [@BotFather](https://t.me/botfather)
- The Telegram chat ID of the target chat

### Getting the chat ID

1. Start a conversation with your bot (send it any message).
2. Fetch updates:
   ```
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. The `chat.id` field in the response is your chat ID.

## Setup

```bash
git clone https://github.com/var-log-skynet/patchmon-telegram-relay
cd patchmon-telegram-relay
cp .env.example .env
```

Edit `.env`:
```
TELEGRAM_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

Set `PATCHMON_NETWORK` to the name of PatchMon's internal Docker network.

## Deploy

```bash
docker compose up -d --build
```

Verify it's running:
```bash
docker compose logs -f
```

> **Tip:** Instead of running this as a separate stack, you can add the `patchmon_telegram_relay` service block directly to your PatchMon `compose.yml`. In that case the network is already shared and the `networks:` section in this file is not needed.

## Configure PatchMon

In the PatchMon UI, go to **Notifications → Destinations** and add a new destination:

- **Type:** Webhook
- **URL:** `http://patchmon_telegram_relay:9090/webhook`

Then create a **Route** that links the destination to the alert types you want delivered.

## Message format

| Field | Source in PatchMon payload |
|---|---|
| Event title | `event_type` |
| Host | `host.friendly_name` or `host.hostname` |
| Severity | `severity` |
| Message | `message` |

Severity levels map to emojis: 🔴 critical · 🟠 error · 🟡 warning · 🔵 info. Unknown payloads are forwarded as a raw JSON dump.

## Updating

After editing `relay.py`, rebuild and restart:
```bash
docker compose up -d --build
```
