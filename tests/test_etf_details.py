import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import etf_details as details


class EtfDetailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "Crawler_ETF.py").write_text('ETF_CONFIG = [{"code":"00980A","name":"測試基金","url":"https://example.com/holdings"}]', encoding="utf-8")
        self.write("etf/all_stocks.json", {"date":"20260601", "etfs":{"00980A":{
            "name":"測試基金", "stocks":[self.row("2330", "2500"), self.row("2308", "1000")]}}})
        self.write("stocks/stocks_00980A_20260528.json", [self.row("2330", "1000"), self.row("2454", "500")])
        self.write("stocks/stocks_00980A_20260602.json", [self.row("2330", "999999")])

    def row(self, code, shares):
        return {"股票代號":code,"股票名稱":"測試股","股數":shares,"持股比例":"5%"}

    def write(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_dated_delta_includes_new_and_removed_holdings_and_lots(self):
        result = details.get_etf_details("00980A", self.root)
        self.assertEqual(result["asof"], "20260601")
        self.assertEqual(result["previous_date"], "20260528")
        self.assertTrue(result["comparable"])
        changes = {row["code"]: row for row in result["changes"]}
        self.assertEqual(changes["2330"]["delta_lots"], 1.5)
        self.assertEqual(changes["2454"]["delta_shares"], -500)
        self.assertEqual(changes["2308"]["previous_shares"], 0)
        self.assertEqual(result["added_shares"], 2500)
        self.assertEqual(result["reduced_shares"], 500)

    def test_missing_shares_does_not_become_zero_trading(self):
        self.write("stocks/stocks_00980A_20260528.json", [self.row("2330", None)])
        result = details.get_etf_details("00980A", self.root)
        self.assertFalse(result["comparable"])
        self.assertIsNone(result["added_shares"])
        self.assertEqual(result["changes"], [])

    def test_foreign_holdings_do_not_use_taiwan_lots(self):
        result = details.normalize_holdings([self.row("AAPL", "1000"), self.row("6981 JP", "1000"), self.row("2330 TT", "1000")])
        self.assertIsNone(result["AAPL"]["lot_size"])
        self.assertIsNone(result["6981 JP"]["lot_size"])
        self.assertEqual(result["2330 TT"]["lot_size"], 1000)

    def test_invalid_and_unknown_codes(self):
        with self.assertRaises(ValueError):
            details.get_etf_details("../../x", self.root)
        with self.assertRaises(KeyError):
            details.get_etf_details("99999A", self.root)

    def test_static_export_is_independent_of_live_services(self):
        with patch.object(details, "fetch_json", side_effect=AssertionError("No network")):
            details.export_details(self.root / "export", self.root)
        self.assertEqual(json.loads((self.root / "export/00980A.json").read_text(encoding="utf-8"))["code"], "00980A")

    def test_official_quote_and_distribution_fields(self):
        def fetch(url):
            if url == details.QUOTE_URL:
                return [{"Code":"00980A", "Date":"1151027", "ClosingPrice":"23.50", "Change":"-0.25", "TradeVolume":"7581399"}]
            return {"status":"ok", "data":[["00980A","測試基金","115年08月18日","115年08月24日","115年09月11日","0.638","policy",115],
                                             ["00981A","其他基金","x","x","x","9"]]}
        with patch.object(details, "fetch_json", side_effect=fetch):
            result = details.market_details("00980A")
        self.assertEqual(result["quote"]["date"], "20261027")
        self.assertEqual(result["quote"]["close"], 23.5)
        self.assertEqual(result["dividends"][0]["cash_per_unit"], 0.638)
        self.assertEqual(len(result["dividends"]), 1)
        self.assertEqual(result["dividend_status"], "ok")

    def test_official_failure_is_not_no_dividend_or_zero_price(self):
        with patch.object(details, "fetch_json", side_effect=OSError("offline")):
            result = details.market_details("00980A")
        self.assertIsNone(result["quote"])
        self.assertEqual(result["quote_status"], "unavailable")
        self.assertEqual(result["dividend_status"], "unavailable")

    def test_empty_official_dividends_are_distinct_from_failure(self):
        with patch.object(details, "fetch_json", side_effect=lambda url: [] if url == details.QUOTE_URL else {"status":"ok","data":[]}):
            result = details.market_details("00980A")
        self.assertEqual(result["dividend_status"], "ok")
        self.assertEqual(result["dividends"], [])


if __name__ == "__main__":
    unittest.main()
