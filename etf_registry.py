"""Discover listed active ETFs from the TWSE catalogue; retain cache on outages."""
import datetime
import json
from pathlib import Path
import re
import urllib.request

ACTIVE_URL = "https://www.twse.com.tw/rwd/zh/ETF/activeList?response=json"
LIST_URL = "https://www.twse.com.tw/rwd/zh/ETF/list?response=json"
SOURCE_URL = "https://www.twse.com.tw/zh/products/securities/etf/products/active-list.html"


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def cached_registry(root=Path(".")):
    try:
        return json.loads((root / "etf/active_etf_registry.json").read_text(encoding="utf-8"))["etfs"]
    except (OSError, ValueError, KeyError):
        return {}


def discover(root=Path("."), today=None):
    today = today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y%m%d")
    active, products = fetch_json(ACTIVE_URL), fetch_json(LIST_URL)
    if active.get("status") != "ok" or products.get("stat") != "OK" or not active.get("data") or not products.get("data"):
        raise ValueError("證交所清單格式異常，保留原有清單")
    listed = {row[1]: row for row in products["data"] if len(row) >= 4}
    registry = cached_registry(root)
    found = 0
    for row in active["data"]:
        if len(row) < 4 or not re.fullmatch(r"\d{5}[AD]", str(row[0])):
            continue
        code, name = row[:2]
        product = listed.get(code)
        if not product:
            continue
        listed_date = str(product[0]).replace(".", "")
        if not re.fullmatch(r"\d{8}", listed_date) or listed_date > today:
            continue
        item = {**registry.get(code, {}), "code": code, "name": name,
                "company": product[3], "category": row[3], "listed_date": listed_date,
                "discovered_at": registry.get(code, {}).get("discovered_at", today), "source": SOURCE_URL}
        # These issuers use the exchange code directly, so future products need no new mapping.
        if "野村" in name:
            item["url"] = f"https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo={code}&tab=Shareholding"
        elif "台新" in name:
            item["url"] = f"https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/{code}"
        registry[code] = item
        found += 1
    if not found:
        raise ValueError("官方清單沒有有效的已上市主動式 ETF，保留原有清單")
    path = root / "etf/active_etf_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checked_at": today, "source": SOURCE_URL, "etfs": registry}, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry


def merge_config(configs, registry):
    result = {item["code"]: dict(item) for item in configs}
    for code, item in registry.items():
        result[code] = {**item, **result.get(code, {})}
        result[code].setdefault("url", "")
    return list(result.values())


if __name__ == "__main__":
    try:
        print(f"官方主動式 ETF 清單：{len(discover())} 檔")
    except Exception as error:
        print(f"清單更新失敗，沿用快取：{error}")
        if not cached_registry():
            raise SystemExit(1)
