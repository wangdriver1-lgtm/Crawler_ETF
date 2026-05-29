import json
import ssl
import urllib.request

ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT@SECLEVEL=1")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

def show(label, url):
    print(f"\n=== {label} ===\n{url}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            ct = r.headers.get("Content-Type", "")
            body = r.read()
            print("status:", r.status, "ct:", ct, "len:", len(body))
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                print("body[:500]:", body[:500])
                return
        if isinstance(data, dict):
            print("keys:", list(data.keys())[:30])
        elif isinstance(data, list):
            print("list len:", len(data), "first:", data[0] if data else None)
        with open(f"sample_{label}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"saved sample_{label}.json")
    except Exception as e:
        print("ERR:", e)


show("cathay_EA", "https://cwapi.cathaysite.com.tw/api/ETF/GetIndexStockWeights?FundCode=EA")
show("jpm_401A", "https://am.jpmorgan.com/FundsMarketingHandler/product-data?cusip=TW00000401A1&country=tw&role=twetf&language=zh&userLoggedIn=false&version=9.7.1_1776467615")