"""ETF snapshot details and dated official market/distribution data."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import threading
import time
import urllib.request
from urllib.parse import urlencode
from etf_registry import cached_registry, merge_config

ROOT = Path(__file__).resolve().parent
QUOTE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
DIVIDEND_URL = "https://www.twse.com.tw/zh/products/securities/etf/products/div.html"
_CACHE = {}
_LOCK = threading.Lock()


def number(value):
    try:
        value = Decimal(str(value).replace(",", "").strip())
        return float(value) if value.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def shares(value):
    value = number(value)
    return int(value) if value is not None and value >= 0 and value.is_integer() else None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def etf_config(root=ROOT):
    tree = ast.parse((root / "Crawler_ETF.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ETF_CONFIG" for t in node.targets):
            return {item["code"]: item for item in merge_config(ast.literal_eval(node.value), cached_registry(root))}
    return {}


def normalize_holdings(rows):
    result = {}
    for row in rows:
        code = str(row.get("股票代號") or "").strip()
        if not code:
            continue
        quantity = shares(row.get("股數"))
        if code in result:
            previous = result[code]["shares"]
            result[code]["shares"] = previous + quantity if previous is not None and quantity is not None else None
            continue
        # Only Taiwan stock identifiers use the 1,000-share lot convention here.
        lot_size = 1000 if re.fullmatch(r"\d{4,6}(?: TT)?", code) else None
        result[code] = {"code": code, "name": str(row.get("股票名稱") or ""),
                        "shares": quantity, "weight": str(row.get("持股比例") or ""), "lot_size": lot_size}
    return result


def snapshot_signature(rows):
    """Compare normalized content independent of ordering/number formatting."""
    holdings = normalize_holdings(rows)
    return tuple((code, row['name'], row['shares'], str(number(row['weight'].replace('%', ''))))
                 for code, row in sorted(holdings.items()))


def compare_holdings(current, previous):
    comparable = bool(current) and previous is not None and all(
        row['shares'] is not None for row in [*current.values(), *previous.values()])
    changes = []
    if comparable:
        for stock in sorted(set(current) | set(previous)):
            before, after = previous.get(stock, {}).get('shares', 0), current.get(stock, {}).get('shares', 0)
            if after != before:
                row = current.get(stock) or previous[stock]
                changes.append({**row, 'previous_shares': before, 'shares': after, 'delta_shares': after - before,
                                'delta_lots': (after - before) / row['lot_size'] if row['lot_size'] else None})
    changes.sort(key=lambda row: abs(row['delta_shares']), reverse=True)
    return comparable, changes


def get_etf_details(code, root=ROOT):
    if not re.fullmatch(r"\d{4,5}[A-Z]?", code):
        raise ValueError("ETF 代碼格式不正確。")
    payload = read_json(root / "etf/all_stocks.json")
    info = payload.get("etfs", {}).get(code)
    if not info:
        raise KeyError("找不到此 ETF 的持股快照。")
    asof = info.get("date", payload.get("date"))
    if not re.fullmatch(r"\d{8}", str(asof or "")) and info.get("stocks"):
        raise ValueError("持股快照缺少有效資料日期。")
    current = normalize_holdings(info.get("stocks", []))
    candidates = []
    for path in (root / "stocks").glob(f"stocks_{code}_*.json"):
        match = re.fullmatch(rf"stocks_{re.escape(code)}_(\d{{8}})\.json", path.name)
        if match and asof and match[1] < asof:
            candidates.append((match[1], path))
    snapshots = [(asof, current, snapshot_signature(info.get('stocks', [])))] if current else []
    for date, path in sorted(candidates, reverse=True):
        try:
            rows = read_json(path)
            if isinstance(rows, list) and rows:
                snapshots.append((date, normalize_holdings(rows), snapshot_signature(rows)))
        except (OSError, ValueError):
            continue
    previous_date = snapshots[1][0] if len(snapshots) > 1 else None
    history = []
    for index, (date, holdings, signature) in enumerate(snapshots[:10]):
        baseline = snapshots[index + 1] if index + 1 < len(snapshots) else None
        unchanged = baseline is not None and signature == baseline[2]
        if unchanged:
            comparable, changes = False, []
        else:
            comparable, changes = compare_holdings(holdings, baseline[1] if baseline else None)
        history.append({'date': date, 'previous_date': baseline[0] if baseline else None,
                        'status': 'unchanged' if unchanged else 'changed' if comparable else 'unavailable',
                        'comparable': comparable, 'changes': changes})
    latest = history[0] if history else {}
    comparable, changes = latest.get('comparable', False), latest.get('changes', [])
    config = etf_config(root).get(code, {})
    return {"code": code, "name": info.get("name", config.get("name", code)), "asof": asof,
            "data_status": info.get("status", "fresh"),
            "unchanged": latest.get('status') == 'unchanged', "history": history,
            "previous_date": previous_date, "official_url": config.get("url") or config.get('source'),
            "holdings": list(current.values()), "changes": changes, "comparable": comparable,
            "added_shares": sum(max(row["delta_shares"], 0) for row in changes) if comparable else None,
            "reduced_shares": sum(max(-row["delta_shares"], 0) for row in changes) if comparable else None,
            "comparison_note": "持股快照差異不是實際成交紀錄，可能包含申贖、分割或資料修正；海外持股不換算台股張數。",
            "profit_note": "基金及成分股實際買進成本未提供，無法由持股快照計算基金目前獲利。可另外輸入個人持倉成本試算。"}


def fetch_json(url):
    with _LOCK:
        cached = _CACHE.get(url)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        result = json.load(response)
    with _LOCK:
        _CACHE[url] = (time.monotonic(), result)
    return result


def normalize_date(raw):
    raw = str(raw or "")
    if re.fullmatch(r"\d{7}", raw):
        return str(int(raw[:3]) + 1911) + raw[3:]
    return raw


def market_details(code):
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    div_api = "https://www.twse.com.tw/rwd/zh/ETF/etfDiv?" + urlencode({
        "response": "json", "stkNo": code, "startDate": f"{today.year-1}0101", "endDate": f"{today.year}1231"})
    result = {"code": code, "quote": None, "quote_status": "unavailable", "dividends": [],
              "dividend_status": "unavailable", "dividend_source": DIVIDEND_URL,
              "dividend_period": f"{today.year-1}/01/01–{today.year}/12/31",
              "retrieved_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        quote_task, div_task = pool.submit(fetch_json, QUOTE_URL), pool.submit(fetch_json, div_api)
        try:
            data = quote_task.result()
            if not isinstance(data, list):
                raise ValueError("Unexpected quote response")
            quote = next((row for row in data if row.get("Code") == code), None)
            if quote and number(quote.get("ClosingPrice")) is not None:
                result["quote"] = {"date": normalize_date(quote.get("Date")), "close": number(quote.get("ClosingPrice")),
                                   "change": number(quote.get("Change")), "volume": shares(quote.get("TradeVolume")),
                                   "currency": "TWD", "source": QUOTE_URL}
                result["quote_status"] = "ok"
        except Exception:
            pass
        try:
            data = div_task.result()
            if data.get("status") != "ok" or not isinstance(data.get("data"), list):
                raise ValueError("Unexpected distribution response")
            # Official fields: code, name, ex-date, record date, pay date, cash/unit, policy, year.
            for row in data["data"]:
                if len(row) >= 6 and str(row[0]) == code:
                    result["dividends"].append({"ex_date": row[2], "record_date": row[3], "pay_date": row[4],
                                                 "cash_per_unit": number(row[5])})
            result["dividend_status"] = "ok"
        except Exception:
            pass
    return result


def export_details(directory, root=ROOT, with_market=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for code in read_json(root / "etf/all_stocks.json").get("etfs", {}):
        payload = get_etf_details(code, root)
        (directory / f"{code}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if with_market:
            market = market_details(code)
            (directory / f"{code}.market.json").write_text(json.dumps(market, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", required=True)
    parser.add_argument("--market", action="store_true", help="Also export dated official quote and distribution data for Pages")
    args = parser.parse_args()
    export_details(args.export, with_market=args.market)
