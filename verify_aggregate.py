"""快速驗證 stock_shares_summary 匯總邏輯（不重新爬取，直接讀 all_stocks.json）。"""
import json
import datetime

all_data = json.load(open("all_stocks.json", encoding="utf-8"))
agg = {}
for etf_code, data in all_data["etfs"].items():
    for s in data["stocks"]:
        code = (s.get("股票代號") or "").strip()
        if not code:
            continue
        raw = str(s.get("股數") or "").replace(",", "").strip()
        try:
            shares = int(float(raw)) if raw else 0
        except ValueError:
            shares = 0
        e = agg.setdefault(code, {
            "股票代號": code,
            "股票名稱": s.get("股票名稱") or "",
            "總股數": 0,
            "持有 ETF 數": 0,
            "ETF明細": [],
        })
        if not e["股票名稱"] and s.get("股票名稱"):
            e["股票名稱"] = s["股票名稱"]
        e["總股數"] += shares
        e["持有 ETF 數"] += 1
        e["ETF明細"].append({
            "ETF股票代號": etf_code,
            "股數": shares,
            "持股比例": s.get("持股比例") or "",
        })

out = sorted(agg.values(), key=lambda x: x["總股數"], reverse=True)
print(f"unique stocks: {len(out)}")
print("總股數 Top 10:")
for x in out[:10]:
    print(f"  {x['股票代號']:<8} {x['股票名稱'][:12]:<14} 總股數={x['總股數']:>15,}  ETF數={x['持有 ETF 數']}")

print("---")
print("被持有最多 ETF 數的前 5:")
for x in sorted(out, key=lambda y: y["持有 ETF 數"], reverse=True)[:5]:
    print(f"  {x['股票代號']:<8} {x['股票名稱'][:12]:<14} ETF數={x['持有 ETF 數']}  總股數={x['總股數']:,}")

# 寫出實際檔案
today = all_data.get("date") or datetime.date.today().strftime("%Y%m%d")
agg_summary = {
    "date": today,
    "total_unique_stocks": len(out),
    "stocks": out,
}
with open(f"stock_shares_summary_{today}.json", "w", encoding="utf-8") as f:
    json.dump(agg_summary, f, ensure_ascii=False, indent=4)
with open("stock_shares_summary.json", "w", encoding="utf-8") as f:
    json.dump(agg_summary, f, ensure_ascii=False, indent=4)
print(f"\n已寫出 stock_shares_summary_{today}.json 與 stock_shares_summary.json")
