import csv
import html
import io
import json
import logging
import os
from html.parser import HTMLParser

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

TOKEN   = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
THREAD_ID = os.getenv('TELEGRAM_THREAD_ID', '').strip()
try:
    THREAD_ID = int(THREAD_ID) if THREAD_ID else None
    if THREAD_ID is not None and THREAD_ID <= 0:
        raise ValueError
except ValueError:
    raise ValueError('TELEGRAM_THREAD_ID must be a positive integer or empty') from None
TG_URL  = f'https://api.telegram.org/bot{TOKEN}/sendMessage'

SEVERITY_EMOJI = {
    'critical': '🔴', 'error': '🟠', 'warning': '🟡',
    'informational': '🔵', 'info': '🔵',
}

REPORT_SECTIONS = {
    'executive_summary': ('Сводка PatchMon', {
        'total_hosts': 'Хостов в сводке',
        'average_score': 'Средний compliance',
    }),
    'patching_status': ('Запуски обновлений', {
        'completed': 'Завершено', 'failed': 'Ошибки',
        'running': 'Выполняется', 'pending': 'В ожидании',
        'cancelled': 'Отменено',
    }),
    'open_alerts': ('Открытые алерты', {
        'total': 'Всего', 'critical': '🔴 Критические',
        'error': '🟠 Ошибки', 'warning': '🟡 Предупреждения',
        'informational': '🔵 Информационные',
    }),
    'hosts_by_updates': ('Обновления по хостам', {}),
}


class ReportTitleParser(HTMLParser):
    """Read the first h1 as text; never forward the email's HTML markup."""

    def __init__(self):
        super().__init__()
        self.in_heading = False
        self.finished = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'h1' and not self.finished:
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag == 'h1' and self.in_heading:
            self.in_heading = False
            self.finished = True

    def handle_data(self, data):
        if self.in_heading:
            self.parts.append(data)


def report_title(data):
    for key in ('report_name', 'title'):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return ' '.join(value.split())

    if isinstance(data.get('html'), str):
        parser = ReportTitleParser()
        try:
            parser.feed(data['html'])
            parser.close()
        except (ValueError, AssertionError):
            pass  # A damaged email template must not prevent CSV delivery.
        else:
            title = ' '.join(''.join(parser.parts).split())
            if title:
                return title

    subject = data.get('subject')
    if isinstance(subject, str) and subject.strip():
        return ' '.join(subject.split())
    return 'Отчёт PatchMon'


def truncate_report_text(text, limit, suffix='…'):
    # Count UTF-16 units conservatively, including emoji. Truncate before HTML
    # escaping so neither entities nor Telegram formatting tags can be cut.
    encoded = text.encode('utf-16-le')
    if len(encoded) // 2 <= limit:
        return text
    available = limit - len(suffix.encode('utf-16-le')) // 2
    shortened = encoded[:available * 2].decode('utf-16-le', errors='ignore')
    if '\n' in shortened:
        shortened = shortened.rsplit('\n', 1)[0]
    return shortened.rstrip() + suffix


def format_report(data):
    """Return a Telegram report, or None for an unrelated CSV payload."""
    csv_text = data.get('csv')
    if not isinstance(csv_text, str):
        return None
    reader = csv.reader(io.StringIO(csv_text.lstrip('\ufeff')), strict=True)
    try:
        header = next(reader, [])
    except csv.Error:
        return None
    if [cell.strip() for cell in header] != ['section', 'metric', 'value']:
        return None

    sections = {}
    skipped = 0
    try:
        for row in reader:
            if not row:
                continue
            if len(row) != 3 or not all(cell.strip() for cell in row):
                skipped += 1
                continue
            section, metric, value = (cell.strip() for cell in row)
            if section == 'hosts_by_updates':
                try:
                    counts = [int(part) for part in value.split('|')]
                    if len(counts) not in (1, 2) or any(n < 0 for n in counts):
                        raise ValueError
                except ValueError:
                    skipped += 1
                    continue
                line = f'• {metric}: {counts[0]}'
                if len(counts) == 2 and counts[1]:
                    line += f' (🔒 безопасность: {counts[1]})'
            else:
                labels = REPORT_SECTIONS.get(section, ('', {}))[1]
                label = labels.get(metric, metric)
                if section == 'executive_summary' and metric == 'average_score':
                    value += '%'
                line = f'• {label}: {value}'
            sections.setdefault(section, []).append(line)
    except csv.Error:
        skipped += 1

    lines = []
    if skipped:
        lines.append('⚠️ Часть CSV не удалось разобрать; отчёт неполный.')
    # Keep summary counts ahead of potentially long host lists.
    order = list(REPORT_SECTIONS) + [s for s in sections if s not in REPORT_SECTIONS]
    for section in order:
        if section not in sections:
            continue
        heading = REPORT_SECTIONS.get(section, (section.replace('_', ' '), {}))[0]
        lines.append(heading + ':\n' + '\n'.join(sections[section]))
    if not sections:
        lines.append('В CSV отчёта нет доступных данных.')

    title = truncate_report_text(report_title(data), 256)
    heading = f'📊 {title}\n\n'
    body_limit = 4000 - len(heading.encode('utf-16-le')) // 2
    body = truncate_report_text(
        '\n\n'.join(lines), body_limit, '\n\n… Отчёт сокращён.',
    )
    return f'📊 <b>{html.escape(title)}</b>\n\n{html.escape(body)}'


def format_message(data):
    logging.info('payload: %s', json.dumps(data))
    report = format_report(data)
    if report is not None:
        return report
    lines = []

    event = html.escape((data.get('event_type') or data.get('type') or 'notification').replace('_', ' ').upper())
    severity = (data.get('severity') or data.get('default_severity') or '').lower()
    emoji = SEVERITY_EMOJI.get(severity, '🔔')
    lines.append(f'{emoji} <b>{event}</b>')

    host = data.get('host') or {}
    hostname = (host.get('friendly_name') or host.get('hostname')
                or data.get('hostname') or data.get('host_name'))
    if hostname:
        lines.append(f'Host: <code>{html.escape(str(hostname))}</code>')

    if severity:
        lines.append(f'Severity: {html.escape(severity)}')

    msg = data.get('message') or data.get('body') or data.get('description')
    if msg:
        lines.append(f'Message: {html.escape(str(msg))}')

    alert_type = data.get('alert_type') or data.get('category')
    if alert_type:
        lines.append(f'Type: {html.escape(str(alert_type))}')

    # Fallback: dump unknown payload
    if len(lines) == 1:
        dumped = json.dumps(data, indent=2)[:3500]
        lines.append(f'<pre>{html.escape(dumped)}</pre>')

    return '\n'.join(lines)


@app.route('/', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True, silent=True) or {}
    text = format_message(data)
    payload = {
        'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'
    }
    if THREAD_ID is not None:
        payload['message_thread_id'] = THREAD_ID
    resp = requests.post(TG_URL, json=payload, timeout=10)
    logging.info('telegram response: %s %s', resp.status_code, resp.text[:200])
    return jsonify({'ok': resp.ok}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9090)
