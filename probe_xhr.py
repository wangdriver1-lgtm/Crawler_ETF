"""偵察 SPA 網頁背後的 XHR/fetch 端點，輸出 JSON 候選清單。"""
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TARGETS = [
    ("00995A", "https://www.ctbcinvestments.com/Etf/00653201/Combination"),
    ("00400A", "https://www.cathaysite.com.tw/ETF/detail/EEA?tab=etf3"),
    ("00401A", "https://am.jpmorgan.com/tw/zh/asset-management/twetf/products/jpmorgan-taiwan-taiwan-equity-high-income-active-etf-tw00000401a1#/portfolio"),
]


def make_driver():
    opts = Options()
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def probe(code: str, url: str):
    print(f"\n=== {code}  {url} ===")
    driver = make_driver()
    try:
        driver.get(url)
        # 等 30 秒讓 SPA 跑完所有 XHR
        for _ in range(6):
            time.sleep(5)
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
        logs = driver.get_log("performance")
        seen = set()
        api_candidates = []
        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
            except Exception:
                continue
            method = msg.get("method", "")
            if method not in ("Network.responseReceived", "Network.requestWillBeSent"):
                continue
            params = msg.get("params", {})
            req = params.get("response") or params.get("request") or {}
            req_url = req.get("url", "")
            if not req_url or req_url in seen:
                continue
            seen.add(req_url)
            mime = (req.get("mimeType") or "").lower()
            # 只關注 JSON/XHR
            req_type = params.get("type", "")
            if "json" in mime or req_type in ("XHR", "Fetch"):
                api_candidates.append((req_type, mime, req_url))

        # 過濾顯然不相關的（埋點、字型、google）
        skip = ("googletagmanager", "google-analytics", "gstatic", "doubleclick",
                "facebook", "hotjar", "cookielaw", "onetrust", "newrelic",
                "/i18n/", ".woff", ".png", ".jpg", ".svg", ".css", ".js?")
        for t, m, u in api_candidates:
            if any(s in u for s in skip):
                continue
            print(f"  [{t}] {m}\n      {u}")
    finally:
        driver.quit()


if __name__ == "__main__":
    for code, url in TARGETS:
        probe(code, url)
