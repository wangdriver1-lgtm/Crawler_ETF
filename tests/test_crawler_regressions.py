import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch

import Crawler_ETF as crawler


ROOT = Path(__file__).resolve().parents[1]
GENERATE_REPORT = crawler.generate_diff_html_report


class CrawlerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="etf-regression-")
        self.addCleanup(self.temp.cleanup)
        original_cwd = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, original_cwd)
        for name, value in {
            "is_tw_trading_day": lambda _: True,
            "_taipei_today": lambda: datetime.date(2026, 6, 1),
            "enrich_diff_with_market_values": lambda data, *a, **kw: data,
            "generate_diff_html_report": lambda *a, **kw: None,
            "generate_weekly_inventory_charts": lambda *a, **kw: None,
        }.items():
            p = patch.object(crawler, name, value)
            p.start()
            self.addCleanup(p.stop)

    def config(self, *codes):
        p = patch.object(crawler, "ETF_CONFIG", [
            {"code": c, "name": c, "url": "https://example.test"} for c in codes
        ])
        p.start()
        self.addCleanup(p.stop)

    def write(self, path, data):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def stock(self, shares="1000"):
        return {"股票代號": "2330", "股票名稱": "台積電", "股數": shares}

    def previous(self, date, scope=("AAA",)):
        self.write(f"stock_shares/stock_shares_summary_{date}.json", {
            "date": date, "included_etfs": list(scope), "stocks": [{
                "股票代號": "2330", "股票名稱": "台積電", "總股數": 500,
                "ETF明細": [{"ETF股票代號": "AAA", "股數": 500}],
            }],
        })

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return crawler.main()

    def test_browser_start_failure_is_caught_and_headless(self):
        with patch.object(crawler.webdriver, "Chrome", side_effect=RuntimeError("no display")) as chrome:
            with contextlib.redirect_stdout(io.StringIO()):
                result = crawler.scrape_etf({"code": "AAA", "name": "A", "url": "https://example.test"})
        self.assertIsNone(result)
        self.assertIn("--headless=new", chrome.call_args.kwargs["options"].arguments)

    def test_tsit_waits_for_holdings_rows_instead_of_static_headings(self):
        empty = '<table><thead><tr><th>代號</th><th>名稱</th><th>股數</th></tr></thead><tbody></tbody></table>'
        loaded = empty.replace('<tbody></tbody>', '<tbody><tr><td>2330</td><td>台積電</td><td>1000</td></tr></tbody>')
        class Driver:
            def __init__(self):
                self.reads = 0
            @property
            def page_source(self):
                self.reads += 1
                return empty if self.reads == 1 else loaded
        driver = Driver()
        with patch.object(crawler.time, "sleep"):
            crawler.wait_for_dynamic_content(driver, "tsit")
        self.assertEqual(driver.reads, 2)

    def test_browser_is_closed_after_navigation_failure(self):
        driver = Mock()
        driver.get.side_effect = RuntimeError("navigation failed")
        with patch.object(crawler.webdriver, "Chrome", return_value=driver):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(crawler.scrape_etf({"code": "AAA", "name": "A", "url": "https://example.test"}))
        driver.quit.assert_called_once()

    def test_identical_holdings_keep_previous_change_report(self):
        self.config('AAA')
        self.previous('20260528')
        self.write('etf/all_stocks.json', {'date': '20260528', 'etfs': {
            'AAA': {'name': 'AAA', 'stocks': [self.stock()]}}})
        self.write('stock_shares/stock_shares_diff.json', {'sentinel': 'prior changes'})
        with patch.object(crawler, 'scrape_etf', return_value=[self.stock()]):
            self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.read('stock_shares/stock_shares_diff.json'), {'sentinel': 'prior changes'})
        self.assertEqual(self.read('etf/all_stocks.json')['unchanged_etfs'], ['AAA'])
        self.assertFalse(Path('stock_shares/stock_shares_diff_20260601.json').exists())

    def test_partial_failure_preserves_all_previous_outputs(self):
        self.config("AAA", "BBB")
        paths = ["etf/all_stocks.json", "stocks/stocks_AAA_20260601.json",
                 "stock_shares/stock_shares_summary.json", "stock_shares/stock_shares_diff.json",
                 "stock_shares/web_reports/stock_changes_report_latest.html"]
        for path in paths:
            self.write(path, {"sentinel": True})
        with patch.object(crawler, "scrape_etf", side_effect=[[self.stock()], None]):
            self.assertEqual(self.run_main(), 1)
        for path in paths:
            self.assertEqual(self.read(path), {"sentinel": True})
        self.assertFalse(Path("stock_shares/stock_shares_summary_20260601.json").exists())

    def test_cloud_partial_update_keeps_failed_etf_original_date_and_excludes_it_from_deltas(self):
        self.config("AAA", "BBB")
        self.previous("20260528", scope=("AAA",))
        self.write("etf/all_stocks.json", {"date":"20260528", "etfs":{
            "BBB":{"name":"B", "stocks":[self.stock("2000")]}}})
        with patch.dict(os.environ, {"CRAWLER_ALLOW_PARTIAL":"1"}), \
                patch.object(crawler, "scrape_etf", side_effect=[[self.stock()], None]):
            self.assertEqual(self.run_main(), 0)
        result = self.read("etf/all_stocks.json")
        self.assertEqual(result["successful_etfs"], 1)
        self.assertEqual(result["failed_etfs"], ["BBB"])
        self.assertEqual(result["etfs"]["BBB"]["date"], "20260528")
        self.assertEqual(result["etfs"]["BBB"]["status"], "stale")
        self.assertEqual(result["etfs"]["AAA"]["date"], "20260601")
        self.assertFalse(Path("stocks/stocks_BBB_20260601.json").exists())
        summary = self.read("stock_shares/stock_shares_summary.json")
        self.assertEqual(summary["included_etfs"], ["AAA"])
        self.assertEqual(summary["stocks"][0]["總股數"], 1000)
        diff = self.read("stock_shares/stock_shares_diff_20260601.json")
        self.assertEqual(diff["持股異動"][0]["總股數差異"], 500)
        self.assertEqual(diff["持股異動"][0]["ETF移除"], [])

    def test_all_sources_failed_never_publish_a_new_snapshot_even_in_partial_mode(self):
        self.config("AAA")
        sentinel = {"date":"20260528","etfs":{}}
        self.write("etf/all_stocks.json", sentinel)
        with patch.dict(os.environ, {"CRAWLER_ALLOW_PARTIAL":"1"}), patch.object(crawler,"scrape_etf",return_value=None):
            self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.read("etf/all_stocks.json"), sentinel)

    def test_scraper_exception_is_also_a_failed_batch(self):
        self.config("AAA")
        with patch.object(crawler, "scrape_etf", side_effect=ValueError("bad API schema")):
            self.assertEqual(self.run_main(), 1)
        self.assertFalse(Path("etf/all_stocks.json").exists())

    def test_cathay_missing_shares_remains_unknown(self):
        # 權重 API 的實際資料結構；測試不依賴本機保存的樣本或連網。
        payload = {"result": {"date": "2026/04/27", "stockWeights": [
            {"stockCode": "2330", "stockName": "台積電", "weights": "9.33"},
        ]}}
        with patch.object(crawler, "_http_get_json", return_value=payload):
            stocks = crawler.scrape_cathaysite_api("00400A", "https://www.cathaysite.com.tw/ETF/detail/EEA")
        self.assertTrue(stocks)
        self.assertTrue(all(s["股數"] is None for s in stocks))

    def test_unknown_shares_excludes_whole_etf_from_totals(self):
        self.config("AAA", "00400A")
        with patch.object(crawler, "scrape_etf", side_effect=[
            [self.stock("1000")], [self.stock(None), self.stock("500")]
        ]):
            self.assertEqual(self.run_main(), 0)
        data = self.read("stock_shares/stock_shares_summary.json")
        self.assertEqual(data["included_etfs"], ["AAA"])
        self.assertEqual(data["missing_share_etfs"], ["00400A"])
        self.assertEqual(data["stocks"][0]["總股數"], 1000)
        self.assertEqual(data["stocks"][0]["持有 ETF 數"], 1)
        self.assertEqual(len(self.read("etf/all_stocks.json")["etfs"]), 2)

    def test_share_parser_distinguishes_zero_from_unknown(self):
        for value in (None, "", "N/A", "NaN", "inf", "-1", "1.5"):
            self.assertIsNone(crawler._parse_shares(value))
        self.assertEqual(crawler._parse_shares(0), 0)
        self.assertEqual(crawler._parse_shares("1,200.0"), 1200)

    def test_future_and_non_date_files_are_not_previous_snapshots(self):
        self.config("AAA")
        self.previous("20260528")
        self.previous("20260601")
        self.previous("20260602")
        self.write("stock_shares/stock_shares_summary_zzz.json", {"date": "invalid"})
        with patch.object(crawler, "scrape_etf", return_value=[self.stock()]):
            self.assertEqual(self.run_main(), 0)
        data = self.read("stock_shares/stock_shares_diff_20260601.json")
        self.assertEqual(data["previous_date"], "20260528")
        self.assertEqual(data["持股異動"][0]["總股數差異"], 500)

    def test_scope_change_skips_fake_trade_comparison(self):
        self.config("AAA")
        self.previous("20260528", scope=("AAA", "00400A"))
        with patch.object(crawler, "scrape_etf", return_value=[self.stock()]):
            self.assertEqual(self.run_main(), 0)
        self.assertFalse(Path("stock_shares/stock_shares_diff_20260601.json").exists())

    def test_cost_per_thousand_and_missing_price(self):
        cost, per_k = crawler._compute_cumulative_cost([{"總股數": 1000, "收盤價": 100}])
        self.assertEqual((cost, per_k), (100000, 100000))
        self.assertEqual(crawler._compute_cumulative_cost([
            {"總股數": 2000, "收盤價": 100}, {"總股數": 1000, "收盤價": None}
        ]), (None, None))

    def test_cost_history_stops_at_scope_change(self):
        self.previous("20260528", scope=("AAA", "00400A"))
        self.previous("20260601")
        with patch.object(crawler, "get_tw_closing_prices", return_value={"2330": 100}):
            history = crawler.build_stock_5d_history("stock_shares", ["2330"], "20260601")
        self.assertEqual([h["date"] for h in history["2330"]], ["20260601"])

    def test_workflow_exports_source_date_and_unknown_share_metadata(self):
        workflow = (ROOT / ".github/workflows/crawler.yml").read_text(encoding="utf-8")
        script = textwrap.dedent(workflow.split("python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        self.write("etf/all_stocks.json", {
            "date": "20260601", "updated_at": "2026-06-01T21:00:00+08:00",
            "missing_share_etfs": ["00400A"], "etfs": {"AAA": {"name": "A"}},
        })
        exec(compile(script, "workflow-site-export", "exec"), {})
        data = self.read("docs/data/active_etf_summary.json")
        self.assertEqual(data["date"], "20260601")
        self.assertEqual(data["updated_at"], "2026-06-01T21:00:00+08:00")
        self.assertEqual(data["missing_share_etfs"], ["00400A"])
        self.assertEqual(data["etfs"]["AAA"]["name"], "A")

    def test_frontend_dates_and_generated_report_costs(self):
        node = os.environ.get("CRAWLER_TEST_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for frontend regression checks")
        self.previous("20260601")
        diff = {"date": "20260601", "previous_date": "20260528",
                "missing_share_etfs": ["00400A"], "新增個股": [], "持股異動": []}
        with patch.object(crawler, "get_tw_closing_prices", return_value={"2330": 100}):
            report = GENERATE_REPORT("stock_shares", diff, "20260601")
        self.assertIn("00400A", Path(report).read_text(encoding="utf-8"))
        result = subprocess.run([node, str(ROOT / "tests/test_frontend.js"), str(Path(report).resolve())],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
