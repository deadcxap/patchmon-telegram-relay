# patchmon-telegram-relay

A minimal webhook relay that forwards [PatchMon](https://github.com/PatchMon/PatchMon) notifications to a Telegram chat.

PatchMon's webhook destination sends its own JSON payload. This relay receives it, formats a human-readable message, and calls the Telegram Bot API.

## Container image

This fork publishes `ghcr.io/deadcxap/patchmon-telegram-relay:latest` for `linux/amd64` and `linux/arm64`.

[GitHub Actions](https://github.com/deadcxap/patchmon-telegram-relay/actions/workflows/build-image.yml) builds and publishes the image:

- After every push to `main`.
- Every Monday at 03:17 UTC (06:17 Moscow time).
- On demand via **Actions → Build container image → Run workflow**, with `main` selected.

Each build pulls the current base image and reinstalls the Python dependencies without using cached build layers.

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
git clone https://github.com/deadcxap/patchmon-telegram-relay.git
cd patchmon-telegram-relay
cp .env.example .env
```

Edit `.env`:
```
TELEGRAM_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
PATCHMON_NETWORK=<patchmon-internal-docker-network-name>
```

Set `PATCHMON_NETWORK` to the name of PatchMon's internal Docker network.

## Deploy

```bash
docker compose pull
docker compose up -d
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

Pull the latest image and recreate the container:
```bash
docker compose pull
docker compose up -d
```

Publishing a new image does not update running containers automatically; run these commands on each Docker host when you want to update.

## GitHub Actions setup

Enable workflows in the fork's **Actions** tab if GitHub has disabled them. The workflow uses the built-in `GITHUB_TOKEN` with `packages: write`; no extra repository secrets are needed.

After the first successful build, open the package's **Package settings → Change visibility** and choose **Public** to allow pulling without authentication. GitHub creates new container packages as private by default; see [the Container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Scheduled workflows run from the default branch, which should remain `main`. GitHub can disable scheduled workflows in public repositories after 60 days without repository activity; re-enable the workflow in **Actions** if this happens. See [scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

For another fork, the workflow automatically publishes to `ghcr.io/<owner>/<repository>:latest` (in lowercase). Update the image reference in `compose.yml` to match.
