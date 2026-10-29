import csv
import io
import os
import unittest
from html.parser import HTMLParser
from unittest.mock import Mock, patch

with patch.dict(os.environ, {
    'TELEGRAM_TOKEN': 'test-token',
    'TELEGRAM_CHAT_ID': 'test-chat',
    'TELEGRAM_THREAD_ID': '',
}):
    import relay


WEEKLY_CSV = '''section,metric,value
executive_summary,total_hosts,0
executive_summary,average_score,0.0
patching_status,completed,1
hosts_by_updates,0nothing.help,14|0
hosts_by_updates,ten.notfunny.pics,2|0
hosts_by_updates,mon.notfunny.pics,1|0
hosts_by_updates,your.fckng.click,1|0
hosts_by_updates,next.fckng.click,1|0
hosts_by_updates,what.fckng.help,1|0
hosts_by_updates,vibe.notfunny.pics,1|0
hosts_by_updates,usa.notfunny.pics,1|0
hosts_by_updates,lnd.notfunny.pics,1|0
hosts_by_updates,ind.notfunny.pics,1|0
open_alerts,total,0
open_alerts,critical,0
open_alerts,error,0
open_alerts,warning,0
open_alerts,informational,0
'''
WEEKLY_REPORT = {
    'csv': WEEKLY_CSV,
    # The user's pasted email is truncated after the intact title.
    'html': '<!DOCTYPE html><html><body><h1 style="color:#0f172a;">'
            'main status</h1><p>Generated Thu, Oct 29 2026 at 21:41 UTC</p>'
            '<table><tr><td style="font-size:22',
}


def report_csv(*rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(('section', 'metric', 'value'))
    writer.writerows(rows)
    return stream.getvalue()


class TelegramHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        assert tag in ('b', 'code', 'pre'), f'Unexpected Telegram tag: {tag}'
        assert not attrs, f'Unexpected attributes: {attrs}'
        self.tags.append(tag)

    def handle_endtag(self, tag):
        assert self.tags.pop() == tag, f'Unbalanced tag: {tag}'

    def handle_data(self, text):
        self.text.append(text)


class ReportTests(unittest.TestCase):
    def setUp(self):
        logger = patch.object(relay.logging, 'info')
        logger.start()
        self.addCleanup(logger.stop)

    def assert_valid_telegram_message(self, message):
        parser = TelegramHTML()
        parser.feed(message)
        parser.close()
        self.assertEqual(parser.tags, [])
        text = ''.join(parser.text)
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        return text

    def test_weekly_report_from_user(self):
        message = relay.format_message(WEEKLY_REPORT)
        self.assertTrue(message.startswith('📊 <b>main status</b>\n\n'))
        self.assertIn('Хостов в сводке: 0', message)
        self.assertIn('Средний compliance: 0.0%', message)
        self.assertIn('Завершено: 1', message)
        self.assertIn('Открытые алерты:\n• Всего: 0', message)
        self.assertIn('• 0nothing.help: 14', message)
        self.assertIn('• ten.notfunny.pics: 2', message)
        self.assertIn('• ind.notfunny.pics: 1', message)
        self.assertEqual(message.count('.pics:'), 6)
        self.assertNotIn('14|0', message)
        self.assertNotIn('<pre>', message)
        self.assertNotIn('DOCTYPE', message)
        self.assert_valid_telegram_message(message)

    def test_title_sources_and_precedence(self):
        cases = [
            ({'report_name': 'Weekly', 'title': 'Other', **WEEKLY_REPORT}, 'Weekly'),
            ({'title': 'Explicit', **WEEKLY_REPORT}, 'Explicit'),
            ({'subject': 'PatchMon Report: Weekly'}, 'PatchMon Report: Weekly'),
            ({'subject': 'Subject', **WEEKLY_REPORT}, 'main status'),
            ({'html': '<h1>Week <span>42</span> &amp; fleet</h1><h1>Other</h1>'},
             'Week 42 &amp; fleet'),
            ({'report_name': 42, 'title': ' ', 'html': None}, 'Отчёт PatchMon'),
            ({'html': '<![invalid]>', 'subject': 'Fallback'}, 'Fallback'),
            ({}, 'Отчёт PatchMon'),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                message = relay.format_message({'csv': WEEKLY_CSV, **fields})
                self.assertTrue(message.startswith(f'📊 <b>{expected}</b>'))

    def test_security_counts_and_quoted_csv(self):
        message = relay.format_message({'csv': '\ufeff' + report_csv(
            ('hosts_by_updates', 'host, "one" & <two>', '14|3'),
            ('hosts_by_updates', 'legacy', '2'),
            ('hosts_by_updates', 'updated', '0|0'),
            ('hosts_by_updates', 'two\nlines', '1|0'),
        )})
        text = self.assert_valid_telegram_message(message)
        self.assertIn('host, "one" & <two>: 14 (🔒 безопасность: 3)', text)
        self.assertIn('• legacy: 2', text)
        self.assertIn('• updated: 0', text)
        self.assertIn('two\nlines: 1', text)

    def test_payload_text_cannot_inject_telegram_html(self):
        message = relay.format_message({
            'title': '<a href="https://example.com">title & more</a>',
            'csv': report_csv(
                ('hosts_by_updates', '<b>host & name</b>', '2|1'),
                ('unknown<script>', '<i>metric</i>', '<a>value & more</a>'),
            ),
        })
        text = self.assert_valid_telegram_message(message)
        self.assertIn('<b>host & name</b>: 2', text)
        self.assertIn('<a>value & more</a>', text)
        self.assertNotIn('<script>', message)

    def test_bad_rows_do_not_discard_good_data(self):
        csv_text = report_csv(
            ('hosts_by_updates', 'bad-count', 'NaN|0'),
            ('hosts_by_updates', 'negative', '-1|0'),
            ('hosts_by_updates', 'extra-count', '1|2|3'),
            ('hosts_by_updates', 'empty-security', '2|'),
            ('hosts_by_updates', 'broken'),
            ('open_alerts', '', '1'),
            ('hosts_by_updates', 'good', '4|2'),
            ('open_alerts', 'total', '1'),
        ) + 'hosts_by_updates,"unclosed,1|0\n'
        message = relay.format_message({'csv': csv_text})
        self.assertIn('отчёт неполный', message)
        self.assertIn('• good: 4 (🔒 безопасность: 2)', message)
        self.assertIn('• Всего: 1', message)
        self.assertNotIn('bad-count', message)
        self.assert_valid_telegram_message(message)

    def test_no_hosts_does_not_claim_everything_is_updated(self):
        for csv_text in [report_csv(), report_csv(('open_alerts', 'critical', '2')),
                         report_csv(('hosts_by_updates', 'bad', 'invalid'))]:
            with self.subTest(csv=csv_text):
                message = relay.format_message({'csv': csv_text})
                self.assertNotIn('Все хосты обновлены', message)
                self.assertNotIn('Всего: 0', message)
        self.assertIn('нет доступных данных', relay.format_report({'csv': report_csv()}))

    def test_other_sections_are_preserved(self):
        message = relay.format_message({'csv': report_csv(
            ('compliance', 'total_failed_rules', '7'),
            ('top_security_package', 'openssl', '3'),
            ('future_section', 'future_metric', 'some value'),
        )})
        self.assertIn('total_failed_rules: 7', message)
        self.assertIn('openssl: 3', message)
        self.assertIn('future section:\n• future_metric: some value', message)

    def test_long_report_keeps_summary_and_valid_html(self):
        message = relay.format_message({
            'title': 'Weekly 😀 & <fleet> ' * 100,
            'csv': report_csv(
                *(('hosts_by_updates', f'host-{i}-😀<&>', '12|1') for i in range(500)),
                ('open_alerts', 'total', '7'),
            ),
        })
        self.assert_valid_telegram_message(message)
        self.assertIn('• Всего: 7', message)
        self.assertIn('host-0-', message)
        self.assertIn('Отчёт сокращён.', message)
        self.assertNotIn('host-499-', message)

    def test_single_oversized_field_and_csv_reader_limit(self):
        for name in ['😀&<>' * 4000, 'x' * 140000]:
            with self.subTest(length=len(name)):
                message = relay.format_message({
                    'csv': report_csv(('hosts_by_updates', name, '1|0')),
                })
                self.assert_valid_telegram_message(message)
                self.assertTrue('сокращён' in message or 'неполный' in message)

    def test_unrelated_or_invalid_csv_retains_json_fallback(self):
        for value in [None, 123, {}, [], '', 'other,columns\n1,2', '"unclosed']:
            with self.subTest(csv=value):
                message = relay.format_message({'csv': value})
                self.assertIn('<pre>', message)
                self.assertNotIn('📊', message)

    def test_existing_alert_format(self):
        message = relay.format_message({
            'event_type': 'updates_available', 'severity': 'warning',
            'host': {'friendly_name': 'host<&>'},
            'message': 'Updates <available>', 'alert_type': 'updates',
        })
        self.assertEqual(message, '\n'.join([
            '🟡 <b>UPDATES AVAILABLE</b>',
            'Host: <code>host&lt;&amp;&gt;</code>',
            'Severity: warning', 'Message: Updates &lt;available&gt;',
            'Type: updates',
        ]))

    def test_webhook_sends_report_to_configured_chat_and_topic(self):
        client = relay.app.test_client()
        for route in ('/', '/webhook'):
            for topic in (None, 123):
                with self.subTest(route=route, topic=topic), \
                        patch.object(relay, 'THREAD_ID', topic), \
                        patch.object(relay.requests, 'post') as post:
                    post.return_value = Mock(ok=True, status_code=200, text='ok')
                    response = client.post(route, json=WEEKLY_REPORT)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json, {'ok': True})
                    post.assert_called_once()
                    self.assertEqual(post.call_args.args, (relay.TG_URL,))
                    payload = post.call_args.kwargs['json']
                    self.assertEqual(payload['chat_id'], 'test-chat')
                    self.assertEqual(payload['parse_mode'], 'HTML')
                    self.assertEqual(payload['text'], relay.format_message(WEEKLY_REPORT))
                    self.assertEqual(post.call_args.kwargs['timeout'], 10)
                    if topic is None:
                        self.assertNotIn('message_thread_id', payload)
                    else:
                        self.assertEqual(payload['message_thread_id'], topic)


if __name__ == '__main__':
    unittest.main()
