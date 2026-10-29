# patchmon-telegram-relay

[English documentation](README.md)

Простой webhook-релей для отправки уведомлений [PatchMon](https://github.com/PatchMon/PatchMon) в чат Telegram.

PatchMon отправляет на webhook данные в собственном формате JSON. Релей принимает их, формирует удобное для чтения сообщение и отправляет его через Telegram Bot API.

## Образ контейнера

Этот форк публикует образ `ghcr.io/deadcxap/patchmon-telegram-relay:latest` для `linux/amd64` и `linux/arm64`.

[GitHub Actions](https://github.com/deadcxap/patchmon-telegram-relay/actions/workflows/build-image.yml) собирает и публикует образ:

- После каждого push в `main`.
- Каждый понедельник в 03:17 UTC (06:17 по Москве).
- По запросу: **Actions → Build container image → Run workflow**, с выбранной веткой `main`.

При каждой сборке загружается актуальный базовый образ и заново устанавливаются зависимости Python без использования кеша слоёв сборки.

## Требования

- Docker и Docker Compose.
- Работающий экземпляр PatchMon на том же Docker-хосте.
- Токен Telegram-бота — создайте бота через [@BotFather](https://t.me/botfather).
- ID чата Telegram, в который нужно отправлять сообщения.

### Как получить ID чата

1. Начните диалог с ботом: отправьте ему любое сообщение.
2. Запросите обновления, заменив `<TOKEN>` токеном бота:

   ```
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

3. Значение поля `chat.id` в ответе — это ID вашего чата.

### Выбор темы в группе (необязательно)

1. Добавьте бота в группу Telegram с включёнными темами и разрешите ему отправлять сообщения.
2. В нужной теме отправьте команду, адресованную боту, например `/start@YourBotUsername`.
3. Запросите `getUpdates`, как показано выше. В обновлении с этим сообщением возьмите `message.chat.id` для `TELEGRAM_CHAT_ID`, а `message.message_thread_id` — для `TELEGRAM_THREAD_ID`.

Например, `TELEGRAM_THREAD_ID=123` направит все уведомления в тему `123` указанной группы. Релей передаёт это значение в параметре [`message_thread_id` метода `sendMessage`](https://core.telegram.org/bots/api#sendmessage).

Оставьте `TELEGRAM_THREAD_ID` пустым или не задавайте его, чтобы отправлять сообщения без указания темы. Если значение задано, оно должно быть положительным целым числом; при некорректном значении релей завершится при запуске с ошибкой конфигурации.

## Настройка

```bash
git clone https://github.com/deadcxap/patchmon-telegram-relay.git
cd patchmon-telegram-relay
cp .env.example .env
```

Отредактируйте `.env`, подставив свои значения:

```
TELEGRAM_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
TELEGRAM_THREAD_ID=
PATCHMON_NETWORK=<patchmon-internal-docker-network-name>
```

В `PATCHMON_NETWORK` укажите имя внутренней Docker-сети PatchMon.

## Запуск

```bash
docker compose pull
docker compose up -d
```

Проверьте работу по логам:

```bash
docker compose logs -f
```

> **Совет:** блок сервиса `patchmon_telegram_relay` можно добавить непосредственно в `compose.yml` PatchMon. В таком случае сеть уже общая и отдельный раздел `networks:` из этого файла не нужен.

## Настройка PatchMon

В интерфейсе PatchMon откройте **Notifications → Destinations** и добавьте новое назначение:

- **Type:** Webhook
- **URL:** `http://patchmon_telegram_relay:9090/webhook`

Затем создайте **Route**, связывающий это назначение с нужными типами алертов.

## Формат сообщений

| Поле | Источник в данных PatchMon |
|---|---|
| Заголовок события | `event_type` |
| Хост | `host.friendly_name` или `host.hostname` |
| Уровень важности | `severity` |
| Сообщение | `message` |

Уровни важности обозначаются эмодзи: 🔴 critical · 🟠 error · 🟡 warning · 🔵 info. Неизвестные форматы пересылаются в виде исходного JSON.

### Отчёты по расписанию

Недельные и другие отчёты PatchMon по расписанию распознаются по строковому полю `csv` с заголовком `section,metric,value`. Для них используются тот же URL webhook и те же настройки чата и темы, что и для алертов.

Отчёты оформляются на русском языке и содержат:

- Название из `report_name`, `title`, первого `<h1>` в `html` или `subject` — в указанном порядке приоритета. Если название отсутствует, используется `Отчёт PatchMon`.
- Показатели общей сводки и количество запусков обновлений по статусам в том виде, в котором их передал PatchMon.
- Общее число открытых алертов и их количество по уровням важности. Этот блок расположен перед списком хостов, чтобы оставаться видимым в длинных отчётах.
- Количество обновлений по хостам: `hosts_by_updates,example.org,14|3` превращается в `• example.org: 14 (🔒 безопасность: 3)`. Имена хостов сохраняются, включая цифры в начале имени.
- Другие разделы CSV в виде списков пар «показатель — значение».

Значения `total|security` соответствуют [формату CSV-отчёта PatchMon](https://github.com/PatchMon/PatchMon/blob/main/server-source-code/internal/notifications/report_render.go): общее число обновлений и число обновлений безопасности. Отсутствие раздела с хостами не означает, что все хосты обновлены. Показатели сводки не пересчитываются по списку хостов: PatchMon может ограничить этот список первыми хостами в рейтинге.

Некорректные строки пропускаются, а в отчёт добавляется предупреждение о неполных данных. При ошибке разбора CSV чтение оставшихся строк прекращается. Пустой отчёт сопровождается сообщением об отсутствии данных. Если заголовок CSV не соответствует ожидаемому или поле `csv` не является строкой, используется обычная обработка уведомления либо вывод JSON.

HTML письма используется только для извлечения названия. Весь текст отчёта экранируется для Telegram. Длинные отчёты сокращаются до 4 000 кодовых единиц UTF-16 с пометкой `… Отчёт сокращён.`; название ограничено 256 кодовыми единицами. Это укладывается в [лимит `sendMessage`](https://core.telegram.org/bots/api#sendmessage), не обрывая теги форматирования и HTML-сущности.

## Обновление

Загрузите свежий образ и пересоздайте контейнер:

```bash
docker compose pull
docker compose up -d
```

Публикация нового образа не обновляет работающие контейнеры автоматически. Выполните эти команды на каждом Docker-хосте, который нужно обновить.

Чтобы собрать и запустить изменения из локальной копии репозитория с именем образа, указанным в настройках этого форка:

```bash
docker build -t ghcr.io/deadcxap/patchmon-telegram-relay:latest .
docker compose up -d --force-recreate --pull never
```

## Тесты

Используйте Python 3.12 с установленными пакетами `flask` и `requests`:

```bash
python -m unittest -v
```

Тесты проверяют форматирование отчётов, некорректные строки и поля CSV в кавычках, экранирование HTML, длинные сообщения, обычные алерты и оба маршрута webhook с темой и без неё. Запросы к Telegram подменяются: тесты не отправляют сообщения и не требуют настоящих токенов или ID чата.

## Настройка GitHub Actions

Если GitHub отключил workflow в форке, включите их на вкладке **Actions**. Workflow использует встроенный `GITHUB_TOKEN` с правом `packages: write`; дополнительные секреты репозитория не нужны.

После первой успешной сборки откройте **Package settings → Change visibility** у пакета и выберите **Public**, чтобы образ можно было загружать без авторизации. GitHub по умолчанию создаёт новые пакеты контейнеров приватными; подробнее — в [документации Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Запуски по расписанию выполняются из ветки по умолчанию, которой должна оставаться `main`. GitHub может отключить их в публичном репозитории после 60 дней без активности; при необходимости включите workflow заново на вкладке **Actions**. Подробнее — в [документации о запусках по расписанию](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Для другого форка workflow автоматически публикует образ `ghcr.io/<owner>/<repository>:latest`, приводя имя к нижнему регистру. Обновите ссылку на образ в `compose.yml`, чтобы она соответствовала вашему форку.
