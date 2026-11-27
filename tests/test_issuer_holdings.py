import datetime
import unittest
from unittest.mock import patch

from issuer_holdings import (ab_url, parse_ab_holdings, taiwan_isin, parse_capital_holdings,
                            fetch_capital_holdings, parse_schroders_holdings)


class IssuerTests(unittest.TestCase):
    def capital(self):
        return {'code': 200, 'data': {'pcf': {'date1': '2026-11-30', 'date2': '2026-11-27'},
                                    'stocks': [{'stocNo': '2330', 'stocName': '台積電', 'share': 1234000,
                                                'weight': 9.1234}]}}

    def schroders(self):
        return {'fxPcfSubscriptionRedemptionSection': {
            'subscriptionRedemption': {'heading': '申購買回清單公告日: 30.11.2026', 'items': [
                {'attribute': 'netAssets', 'asOfDate': '27.11.2026'}]},
            'holdings': {'groups': [{'title': '&#32929;&#31080;',
                                    'columns': ['股票代號', '股票名稱', '股數', '總金額', '權重 (%)'],
                                    'rows': [['6223.TWO', '&#26106;&#30717;', '<span>2,000</span>', '50000', '<span>3.07%</span>']]}]}}}

    def test_capital_uses_actual_valuation_date_instead_of_next_dealing_day(self):
        result = parse_capital_holdings(self.capital(), '00982A', datetime.date(2026, 11, 28))
        self.assertEqual(result['date'], '20261127')
        self.assertEqual(result['stocks'][0]['股數'], '1234000')
        self.assertEqual(result['stocks'][0]['持股比例'], '9.1234%')

    def test_capital_checks_fund_identity_and_rejects_empty_or_invalid_quantities(self):
        with patch('issuer_holdings.request_json', return_value={'code': 200, 'data': {'stockCode': '00992A'}}):
            with self.assertRaises(ValueError):
                fetch_capital_holdings('00982A', 'https://www.capitalfund.com.tw/etf/product/detail/399/portfolio')
        payload = self.capital()
        payload['data']['stocks'] = []
        with self.assertRaises(ValueError):
            parse_capital_holdings(payload, '00982A')

    def test_capital_ignores_publisher_trailing_whitespace_in_fund_identity(self):
        with patch('issuer_holdings.request_json', side_effect=[
            {'code': 200, 'data': {'stockCode': '00992A '}}, self.capital()]):
            result = fetch_capital_holdings('00992A', 'https://www.capitalfund.com.tw/etf/product/detail/500/portfolio')
        self.assertEqual(result['stocks'][0]['ETF股票代號'], '00992A')
        payload = self.capital()
        payload['data']['stocks'][0]['share'] = -1
        with self.assertRaises(ValueError):
            parse_capital_holdings(payload, '00982A')

    def test_schroders_decodes_html_and_normalizes_taiwan_stock_identifiers(self):
        result = parse_schroders_holdings(self.schroders(), '00419A', datetime.date(2026, 11, 28))
        self.assertEqual(result['date'], '20261127')
        self.assertEqual(result['stocks'][0]['股票代號'], '6223')
        self.assertEqual(result['stocks'][0]['股票名稱'], '旺矽')
        self.assertEqual(result['stocks'][0]['股數'], '2000')

    def test_schroders_rejects_missing_future_or_changed_schema(self):
        with self.assertRaises(ValueError):
            parse_schroders_holdings(self.schroders(), '00419A', datetime.date(2026, 11, 26))
        payload = self.schroders()
        payload['fxPcfSubscriptionRedemptionSection']['holdings']['groups'][0]['columns'].reverse()
        with self.assertRaises(ValueError):
            parse_schroders_holdings(payload, '00419A')
        with self.assertRaises(ValueError):
            parse_schroders_holdings({}, '00419A')

    def section(self, category, quantity, date='11/04/2026'):
        return {'asOfDate': date, 'holdingCategory': category, 'holdings': [
            {'holdingCode': 'US12345' if category.endswith('bond') else '2330', 'holding': '測試標的',
             'holdingShares': quantity, 'holdingPerc': '-0.5' if quantity < 0 else '2.5'}]}

    def test_isin_check_digit_matches_official_funds(self):
        self.assertEqual(taiwan_isin('00984D'), 'TW00000984D0')
        self.assertEqual(taiwan_isin('00404A'), 'TW00000404A5')
        self.assertIn('pcf.TW00000984D0.html', ab_url('00984D'))
        with self.assertRaises(ValueError):
            taiwan_isin('../00984D')

    def test_bonds_and_derivatives_keep_their_published_units_and_date(self):
        result = parse_ab_holdings({'domesticHoldings': [self.section('holdings-section-bond', 510000),
                                  self.section('holdings-section-futures', -7)]}, '00984D', datetime.date(2026, 11, 5))
        self.assertEqual(result['date'], '20261104')
        self.assertEqual(result['source_kind'], 'official')
        self.assertEqual(result['stocks'][0]['數量單位'], '面額')
        self.assertIsNone(result['stocks'][0]['股數'])
        self.assertEqual(result['stocks'][1]['原始數量'], -7)

    def test_equities_use_actual_share_count(self):
        result = parse_ab_holdings({'domesticHoldings': [self.section('holdings-section-equity', 1000)]}, '00404A')
        self.assertEqual(result['stocks'][0]['股數'], '1000')

    def test_empty_future_or_mixed_dates_are_rejected(self):
        for sections in [[], [self.section('holdings-section-bond', 10, '11/06/2026')],
                         [self.section('holdings-section-bond', 10), self.section('holdings-section-futures', -1, '11/03/2026')]]:
            with self.assertRaises(ValueError):
                parse_ab_holdings({'domesticHoldings': sections}, '00984D', datetime.date(2026, 11, 5))
