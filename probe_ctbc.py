import json, ssl, urllib.request

ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT@SECLEVEL=1")

# 用 selenium 重抓一次 token
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

opts = Options()
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
d = webdriver.Chrome(options=opts)
d.get("https://www.ctbcinvestments.com.tw/Etf/00653201/Combination")
api = None
api_request_id = None
deadline = time.time() + 40
all_logs = []
while time.time() < deadline and api is None:
    for entry in d.get_log("performance"):
        all_logs.append(entry)
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        params = msg.get("params", {})
        url = (params.get("response") or params.get("request") or {}).get("url", "")
        if "ETFHoldingWeight" in url and msg.get("method") == "Network.requestWillBeSent":
            api = url
            api_request_id = params.get("requestId")
            req = params.get("request", {})
            print("method:", req.get("method"))
            print("headers:", json.dumps(req.get("headers", {}), ensure_ascii=False, indent=2))
            print("postData:", req.get("postData"))
            break
    if not api:
        time.sleep(1.5)
cookies = "; ".join(f"{c['name']}={c['value']}" for c in d.get_cookies())
d.quit()
print("\nAPI:", api)

for method in ("POST", "GET"):
    print(f"\n--- {method} ---")
    try:
        req = urllib.request.Request(
            api,
            data=b"" if method == "POST" else None,
            method=method,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "Cookie": cookies,
                "Referer": "https://www.ctbcinvestments.com/",
                "Origin": "https://www.ctbcinvestments.com",
            },
        )
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            body = r.read()
            print("status:", r.status, "len:", len(body))
            print("body[:1500]:", body.decode("utf-8", errors="replace")[:1500])
            with open(f"sample_ctbc_{method}.json", "wb") as f:
                f.write(body)
    except Exception as e:
        print("ERR:", e)
