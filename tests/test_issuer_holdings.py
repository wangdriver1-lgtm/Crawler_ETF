import datetime
import unittest

from issuer_holdings import ab_url, parse_ab_holdings, taiwan_isin


class IssuerTests(unittest.TestCase):
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
