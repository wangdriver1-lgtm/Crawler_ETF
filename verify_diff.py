"""驗證 diff 邏輯：用 stock_shares_summary.json 製作假昨日資料，與今日做 diff。"""
import json
import copy
import os
import glob

today_data = json.load(open("stock_shares_summary.json", encoding="utf-8"))
today_data = copy.deepcopy(today_data)
today_data["date"] = "20260428"

prev = copy.deepcopy(today_data)
prev["date"] = "20260427"

# 模擬變化：
#  - 移除前 5 檔中的最後 1 檔（讓「移除個股」非空）
#  - 改某幾檔股數
#  - 移除某檔的某個 ETF 持有
#  - 模擬新個股：在 prev 內刪一檔讓 today 變「新增」
prev_stocks = prev["stocks"]
# 1) today 比 prev 多一檔：刪 prev 最後一筆
removed_for_today_to_have_new = prev_stocks.pop()
# 2) prev 比 today 多一檔：在 prev 加一筆假的代號
prev_stocks.append({
    "股票代號": "9999X",
    "股票名稱": "測試移除股",
    "總股數": 5000,
    "持有 ETF 數": 1,
    "ETF明細": [{"ETF股票代號": "00980A", "股數": 5000, "持股比例": "0.10%"}],
})
# 3) 改 2330 的股數（today 多 1,000,000）
for s in prev_stocks:
    if s["股票代號"] == "2330":
        s["總股數"] -= 1_000_000
        for d in s["ETF明細"]:
            if d["ETF股票代號"] == "00400A":
                d["股數"] -= 500_000
        break
# 4) prev 中讓 2308 的 00984A 不存在 → today 出現 ETF 新增
for s in prev_stocks:
    if s["股票代號"] == "2308":
        s["ETF明細"] = [d for d in s["ETF明細"] if d["ETF股票代號"] != "00984A"]
        s["持有 ETF 數"] = len(s["ETF明細"])
        break

# 寫出假的昨日檔
with open("stock_shares_summary_20260427.json", "w", encoding="utf-8") as f:
    json.dump(prev, f, ensure_ascii=False, indent=4)
with open("stock_shares_summary_20260428.json", "w", encoding="utf-8") as f:
    json.dump(today_data, f, ensure_ascii=False, indent=4)

# 接著套用與 main() 一樣的 diff 邏輯
today = "20260428"
agg_filename = f"stock_shares_summary_{today}.json"
aggregated_list = today_data["stocks"]

prev_files = sorted(
    f for f in glob.glob("stock_shares_summary_*.json")
    if os.path.basename(f) != agg_filename
)
prev_path = prev_files[-1]
prev_summary = json.load(open(prev_path, encoding="utf-8"))
prev_map = {x["股票代號"]: x for x in prev_summary.get("stocks", [])}
today_map = {x["股票代號"]: x for x in aggregated_list}

new_codes = sorted(set(today_map) - set(prev_map))
removed_codes = sorted(set(prev_map) - set(today_map))
common_codes = set(today_map) & set(prev_map)

print(f"prev_path: {prev_path}")
print(f"新增: {new_codes}")
print(f"移除: {removed_codes}")

diff_2330 = today_map["2330"]["總股數"] - prev_map["2330"]["總股數"]
print(f"2330 總股數差異: {diff_2330:+,}")

t_2308 = {d["ETF股票代號"] for d in today_map["2308"]["ETF明細"]}
p_2308 = {d["ETF股票代號"] for d in prev_map["2308"]["ETF明細"]}
print(f"2308 新增 ETF: {sorted(t_2308 - p_2308)}")
print(f"2308 移除 ETF: {sorted(p_2308 - t_2308)}")
