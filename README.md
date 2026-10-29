# patchmon-telegram-relay

[Русская документация](README.ru.md)

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

### Selecting a forum topic (optional)

1. Add the bot to your Telegram forum group and allow it to send messages.
2. Send a command addressed to the bot, such as `/start@YourBotUsername`, inside the desired topic.
3. Fetch `getUpdates` as above. In the matching update, use `message.chat.id` as `TELEGRAM_CHAT_ID` and `message.message_thread_id` as `TELEGRAM_THREAD_ID`.

For example, `TELEGRAM_THREAD_ID=123` sends all notifications to topic `123` in the configured group. The relay passes this value as [`message_thread_id` to Telegram's `sendMessage` method](https://core.telegram.org/bots/api#sendmessage).

Leave `TELEGRAM_THREAD_ID` unset or empty to keep the existing behavior without a topic ID. If set, it must be a positive integer; an invalid value stops the relay at startup with a configuration error.

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
TELEGRAM_THREAD_ID=
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

### Scheduled reports

Weekly and other scheduled PatchMon reports are recognized by a string `csv` field with the header `section,metric,value`. They use the same webhook URL and chat/topic configuration as alerts.

Reports are formatted in Russian and include:

- The report title from `report_name`, `title`, the first `<h1>` in `html`, or `subject`, in that order; the default is `Отчёт PatchMon`.
- Executive summary values and patch run status counts exactly as reported by PatchMon.
- Open alert totals and severity counts, ahead of the host list so they remain visible in long reports.
- Host update counts: `hosts_by_updates,example.org,14|3` becomes `• example.org: 14 (🔒 безопасность: 3)`. Host names are preserved, including leading digits.
- Other CSV sections as lists of their metric/value pairs.

The `total|security` host counts follow [PatchMon's report CSV format](https://github.com/PatchMon/PatchMon/blob/main/server-source-code/internal/notifications/report_render.go). A missing host section does not imply that every host is up to date. Summary values are not recalculated from the host list, which PatchMon may limit to its top hosts.

Malformed rows are skipped with an incomplete-report notice; a CSV parsing error stops reading the remaining rows. Empty reports show a no-data notice. Invalid headers and non-string `csv` fields retain the existing notification/JSON fallback.

The email HTML is used only to extract the title. All report text is escaped for Telegram. Long reports are shortened to at most 4,000 UTF-16 units with `… Отчёт сокращён.`; titles are limited to 256 units. This stays below Telegram's [sendMessage limit](https://core.telegram.org/bots/api#sendmessage) without cutting formatting tags or HTML entities.

## Updating

Pull the latest image and recreate the container:
```bash
docker compose pull
docker compose up -d
```

Publishing a new image does not update running containers automatically; run these commands on each Docker host when you want to update.

To build and run changes from a local checkout using this fork's configured image name:

```bash
docker build -t ghcr.io/deadcxap/patchmon-telegram-relay:latest .
docker compose up -d --force-recreate --pull never
```

## Tests

Using Python 3.12 with `flask` and `requests` installed:

```bash
python -m unittest -v
```

The tests cover report formatting, malformed and quoted CSV, HTML escaping, long messages, existing alerts, and both webhook routes with and without a forum topic. Telegram requests are mocked; tests do not send messages or require real credentials.

## GitHub Actions setup

Enable workflows in the fork's **Actions** tab if GitHub has disabled them. The workflow uses the built-in `GITHUB_TOKEN` with `packages: write`; no extra repository secrets are needed.

After the first successful build, open the package's **Package settings → Change visibility** and choose **Public** to allow pulling without authentication. GitHub creates new container packages as private by default; see [the Container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Scheduled workflows run from the default branch, which should remain `main`. GitHub can disable scheduled workflows in public repositories after 60 days without repository activity; re-enable the workflow in **Actions** if this happens. See [scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

For another fork, the workflow automatically publishes to `ghcr.io/<owner>/<repository>:latest` (in lowercase). Update the image reference in `compose.yml` to match.
