import http.client
from http.server import ThreadingHTTPServer
import json
import os
import threading
import unittest
from unittest.mock import patch, MagicMock

import dashboard_server as dashboard


def response_fixture():
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "台積電來源及趨勢"}]},
        "groundingMetadata": {"webSearchQueries": ["台積電最新公告"],
            "groundingChunks": [{"web": {"uri": "https://www.twse.com.tw/", "title": "證交所"}}],
            "groundingSupports": [{"segment": {"startIndex": 9, "endIndex": 15}, "groundingChunkIndices": [0]}],
            "searchEntryPoint": {"renderedContent": "<div>Google 搜尋建議</div>"}}}]}


class AnalysisTests(unittest.TestCase):
    def test_query_validation(self):
        self.assertEqual(dashboard.validate_query({"stock": " 台積電 ", "horizon": "3m"}), ("台積電", "3m"))
        self.assertEqual(dashboard.validate_query({"stock": "AAPL NASDAQ"}), ("AAPL NASDAQ", "3m"))
        for payload in ([], {}, {"stock": "<script>"}, {"stock": "x" * 61},
                        {"stock": "2330", "horizon": []}, {"stock": "2330", "horizon": "1d"}):
            with self.subTest(payload=payload), self.assertRaises(dashboard.AnalysisError):
                dashboard.validate_query(payload)

    def test_missing_key_never_calls_provider(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), patch.object(dashboard.urllib.request, "urlopen") as request:
            with self.assertRaises(dashboard.AnalysisError) as result:
                dashboard.analyze_stock({"stock": "2330"})
            self.assertEqual(result.exception.status, 503)
            request.assert_not_called()

    def test_provider_request_requires_search_and_keeps_secret_server_side(self):
        upstream = MagicMock()
        upstream.__enter__.return_value.read.return_value = json.dumps(response_fixture()).encode()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret", "GEMINI_MODEL": "test-model"}), \
                patch.object(dashboard.urllib.request, "urlopen", return_value=upstream) as request:
            result = dashboard.analyze_stock({"stock": "2330", "horizon": "3m"})
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["tools"], [{"google_search": {}}])
        self.assertIn("systemInstruction", payload)
        self.assertEqual(request.call_args.args[0].get_header("X-goog-api-key"), "test-secret")
        self.assertTrue(request.call_args.args[0].full_url.startswith("https://generativelanguage.googleapis.com/"))
        self.assertNotIn("test-secret", request.call_args.args[0].full_url)
        self.assertNotIn("Authorization", request.call_args.args[0].headers)
        self.assertNotIn("test-secret", json.dumps(result))
        segments = result["blocks"][0]["segments"]
        self.assertEqual("".join(segment["text"] for segment in segments), "台積電來源及趨勢")
        self.assertEqual(segments[1]["text"], "來源")
        self.assertEqual(segments[1]["url"], "https://www.twse.com.tw/")
        self.assertIn("Google 搜尋建議", result["search_suggestions"])

    def test_uncited_or_unsearched_output_is_rejected(self):
        for mode in ("no-search", "unsafe-source", "incomplete"):
            response = response_fixture()
            if mode == "no-search":
                response["candidates"][0]["groundingMetadata"]["webSearchQueries"] = []
            elif mode == "unsafe-source":
                response["candidates"][0]["groundingMetadata"]["groundingChunks"][0]["web"]["uri"] = "javascript:alert(1)"
            else:
                response["candidates"][0]["finishReason"] = "MAX_TOKENS"
            with self.subTest(mode=mode), self.assertRaises(dashboard.AnalysisError):
                dashboard.extract_analysis(response)

    def test_etf_analysis_includes_dated_snapshot_and_specific_research_instructions(self):
        fixture = {"code":"00980A", "name":"測試基金", "asof":"20260601", "previous_date":"20260528",
                   "comparable":True,"holdings":[],"changes":[]}
        upstream = MagicMock()
        upstream.__enter__.return_value.read.return_value = json.dumps(response_fixture()).encode()
        with patch.dict(os.environ, {"GEMINI_API_KEY":"test-secret"}), \
                patch.object(dashboard, "get_etf_details", return_value=fixture), \
                patch.object(dashboard.urllib.request, "urlopen", return_value=upstream) as request:
            dashboard.analyze_stock({"stock":"00980A","kind":"etf","horizon":"3m"})
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(json.loads(payload["contents"][0]["parts"][0]["text"])["etf_snapshot"]["asof"], "20260601")
        self.assertIn("配息不等於總報酬", payload["systemInstruction"]["parts"][0]["text"])

    def test_gemini_multiple_parts_unicode_and_multiple_sources(self):
        response = response_fixture()
        candidate = response["candidates"][0]
        candidate["content"]["parts"] = [{"text":"內部思考", "thought":True}, {"text":"📈台積電來源"}]
        metadata = candidate["groundingMetadata"]
        metadata["groundingChunks"].append({"web":{"uri":"https://example.com/", "title":"其他來源"}})
        metadata["groundingSupports"] = [{"segment":{"partIndex":1,"startIndex":13,"endIndex":19},"groundingChunkIndices":[0,1]}]
        blocks, sources = dashboard.extract_analysis(response)
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0]["segments"][1]["text"], "來源")
        self.assertEqual(len(sources),2)
        self.assertNotIn("內部思考", json.dumps(blocks,ensure_ascii=False))

    def test_google_chunks_without_citation_support_are_rejected(self):
        response = response_fixture()
        response["candidates"][0]["groundingMetadata"]["groundingSupports"] = []
        with self.assertRaises(dashboard.AnalysisError):
            dashboard.extract_analysis(response)

    def test_errors_do_not_return_provider_body(self):
        error = dashboard.urllib.error.HTTPError("https://generativelanguage.googleapis.com", 401, "test-secret", {}, None)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}), \
                patch.object(dashboard.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(dashboard.AnalysisError) as result:
                dashboard.analyze_stock({"stock": "2330"})
            self.assertNotIn("test-secret", result.exception.message)


class DashboardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")

    def test_dashboard_and_status(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('id="ai-analysis"', html)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}):
            status, body = self.request("GET", "/api/ai-status")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["configured"])
        self.assertNotIn("test-secret", body)

    def test_missing_key_has_actionable_error(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            status, body = self.request("POST", "/api/analyze-stock", '{"stock":"2330"}', {"Content-Type": "application/json"})
        self.assertEqual(status, 503)
        self.assertIn("GEMINI_API_KEY", json.loads(body)["error"])

    def test_cross_origin_and_non_json_requests_are_rejected(self):
        status, _ = self.request("POST", "/api/analyze-stock", "{}", {
            "Content-Type": "application/json", "Origin": "https://example.com"})
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/analyze-stock", "{}")
        self.assertEqual(status, 415)
        status, _ = self.request("GET", "/api/ai-status", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_malformed_body_is_rejected(self):
        status, _ = self.request("POST", "/api/analyze-stock", "bad-json", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_etf_snapshot_and_market_routes(self):
        with patch.object(dashboard, "get_etf_details", return_value={"code":"00980A","holdings":[]}), \
                patch.object(dashboard, "market_details", return_value={"quote":None,"dividend_status":"unavailable"}):
            status, body = self.request("GET", "/api/etf/00980A")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["code"], "00980A")
            status, body = self.request("GET", "/api/etf/00980A/market")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["dividend_status"], "unavailable")
        with patch.object(dashboard, "get_etf_details", side_effect=KeyError("unknown")):
            status, _ = self.request("GET", "/api/etf/99999A")
            self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
