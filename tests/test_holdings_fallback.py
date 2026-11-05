import datetime
import json
import unittest

from holdings_fallback import parse_holdings


def page(code='00405A', date='2026-11-04', rows=None, identity=None):
    nodes = [['ShallowReactive', 1], {'data': 2}, ['ShallowReactive', 3], {}, {}]

    def put(value):
        index = len(nodes)
        nodes.append(None)
        if isinstance(value, dict):
            nodes[index] = {key: put(item) for key, item in value.items()}
        elif isinstance(value, list):
            nodes[index] = [put(item) for item in value]
        else:
            nodes[index] = value
        return index

    nodes[3] = {f'etf-detail-base-{code}': 4}
    nodes[4] = {'info': put({'code': identity or code}), 'holdings': put({
        'etfCode': identity or code, 'snapshotDate': date, 'source': 'issuer-official',
        'snapshotDateSource': 'issuer', 'holdings': rows if rows is not None else [
            {'code': '2330', 'name': '台積電', 'shares': 2000, 'unit': '股', 'weight': 15.2}]})}
    return '<script id="__NUXT_DATA__" type="application/json">' + json.dumps(nodes) + '</script>'


class FallbackTests(unittest.TestCase):
    def parse(self, html):
        return parse_holdings(html, '00405A', datetime.date(2026, 11, 5))

    def test_complete_pagination_payload_and_source_date_are_used(self):
        rows = [{'code': str(2000 + i), 'name': '測試股', 'shares': i * 1000, 'unit': '股', 'weight': 1} for i in range(25)]
        result = self.parse(page(rows=rows))
        self.assertEqual(len(result['stocks']), 25)
        self.assertEqual(result['date'], '20261104')
        self.assertEqual(result['source_kind'], 'backup')
        self.assertEqual(result['stocks'][1]['股數'], '1000')
        self.assertIn('etfinfo.tw', result['source_url'])

    def test_non_share_units_and_unknown_quantities_never_become_stock_shares(self):
        rows = [{'code': 'US12345', 'name': '債券', 'shares': 12345, 'unit': '元', 'weight': 10},
                {'code': '2330', 'name': '未知股數', 'shares': None, 'unit': '股', 'weight': 10},
                {'code': 'C_NTD', 'name': 'Cash', 'shares': 500000, 'unit': '元', 'weight': 10}]
        result = self.parse(page(rows=rows))
        self.assertEqual(len(result['stocks']), 2)
        self.assertTrue(all(row['股數'] is None for row in result['stocks']))
        self.assertEqual(result['stocks'][0]['原始數量'], 12345)

    def test_wrong_identity_future_invalid_and_empty_data_are_rejected(self):
        for html in [page(code='00999A'), page(identity='00999A'), page(date='2026-12-01'),
                     page(date='invalid'), page(rows=[]), '<html>No holdings</html>']:
            with self.subTest(html=html[:80]):
                with self.assertRaises((ValueError, KeyError)):
                    self.parse(html)

    def test_duplicate_security_codes_do_not_double_quantities(self):
        row = {'code': '2330', 'name': '台積電', 'shares': 1000, 'unit': '股', 'weight': 10}
        result = self.parse(page(rows=[row, row]))
        self.assertEqual(len(result['stocks']), 1)
