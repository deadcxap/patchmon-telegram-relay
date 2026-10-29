import os, json, logging, html
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

def format_message(data):
    logging.info('payload: %s', json.dumps(data))
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
