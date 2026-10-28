from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import json
import re
import ssl
import time
import datetime
import glob
import os
import sys
import html
import urllib.request
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, InvalidOperation


def _parse_shares(value) -> Optional[int]:
    """缺少或無效的股數是未知值，不能當成零持股。"""
    try:
        number = Decimal(str(value).replace(",", "").strip())
        if number.is_finite() and number >= 0 and number == number.to_integral_value():
            return int(number)
    except (InvalidOperation, ValueError, TypeError):
        pass
    return None


def _taipei_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()


def _summary_etf_scope(summary: Dict) -> List[str]:
    if "included_etfs" in summary:
        return sorted(summary["included_etfs"])
    return sorted({
        d["ETF股票代號"] for s in summary.get("stocks", [])
        for d in s.get("ETF明細", [])
    })

# SSL Context：本機環境憑證偏弱，將 SECLEVEL 降到 1 以便對部分站台直連 API
_SSL_CTX = ssl.create_default_context()
try:
    _SSL_CTX.set_ciphers("DEFAULT@SECLEVEL=1")
except Exception:
    pass

# stdlib urllib 預設 User-Agent 易被擋，這裡改用瀏覽器標頭
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20):
    """以 stdlib urllib 直接打 GET 並把回應解成 JSON。"""
    req = urllib.request.Request(url, headers=headers or _DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_twse_holidays(ad_year: int) -> set:
    """取得台股某年度休市日集合（YYYY-MM-DD）。"""
    roc_year = ad_year - 1911
    url = f"https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=json&queryYear={roc_year}"
    data = _http_get_json(url, timeout=20)
    out = set()
    for row in data.get("data", []):
        if not row:
            continue
        day = str(row[0]).strip()
        # TWSE 回傳日期通常是 YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            out.add(day)
    return out


def is_tw_trading_day(target_date: datetime.date) -> bool:
    """判斷是否為台股交易日。週末或休市日回傳 False。"""
    # 週六/週日一定非交易日
    if target_date.weekday() >= 5:
        return False

    # 平日再查休市表（若 API 暫時失敗，保守地視為交易日，避免誤停排程）
    try:
        holidays = _get_twse_holidays(target_date.year)
    except Exception as e:
        print(f"[trade-day] 休市表查詢失敗，改採平日執行: {e}")
        return True

    return target_date.strftime("%Y-%m-%d") not in holidays


# 所有要爬取的 ETF：code 為股票代號、url 為持股頁面網址
# detect_site_type() 會依 url 的 domain 自動分派到對應的 parser
ETF_CONFIG = [
    {"code": "00980A", "name": "主動野村臺灣優選", "url": "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding"},
    {"code": "00982A", "name": "主動群益台灣強棒", "url": "https://www.capitalfund.com.tw/etf/product/detail/399/portfolio"},
    {"code": "00981A", "name": "主動統一台股增長", "url": "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"},
    {"code": "00984A", "name": "主動安聯台灣高息", "url": "https://etf.allianzgi.com.tw/etf-info/E0001?tab=4"},
    {"code": "00985A", "name": "主動野村台灣50", "url": "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00985A&tab=Shareholding"},
    {"code": "00986A", "name": "主動台新龍頭成長", "url": "https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/00986A"},
    {"code": "00991A", "name": "主動復華未來50", "url": "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"},
    {"code": "00987A", "name": "主動台新優勢成長", "url": "https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/00987A"},
    {"code": "00992A", "name": "主動群益科技創新", "url": "https://www.capitalfund.com.tw/etf/product/detail/500/portfolio"},
    {"code": "00994A", "name": "主動第一金台股優", "url": "https://www.fsitc.com.tw/FundDetail.aspx?ID=182#TabLinkdivEditTab3"},
    {"code": "00995A", "name": "主動中信台灣卓越", "url": "https://www.ctbcinvestments.com/Etf/00653201/Combination"},
    {"code": "00993A", "name": "主動安聯台灣", "url": "https://etf.allianzgi.com.tw/etf-info/E0002?tab=4"},
    {"code": "00996A", "name": "主動兆豐台灣豐收", "url": "https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id=23"},
    {"code": "00400A", "name": "主動國泰動能高息", "url": "https://www.cathaysite.com.tw/ETF/detail/EEA?tab=etf3"},
    {"code": "00401A", "name": "主動摩根台灣鑫收", "url": "https://am.jpmorgan.com/tw/zh/asset-management/twetf/products/jpmorgan-taiwan-taiwan-equity-high-income-active-etf-tw00000401a1#/portfolio"},
    {"code": "00997A", "name": "主動群益美國增長", "url": "https://www.capitalfund.com.tw/etf/product/detail/502/portfolio"},
]


def detect_etf_stock_code(soup, page_url):
    # 優先從頁面標題與 og:title 抓像 00991A 的代號
    title_candidates = []
    if soup.title and soup.title.get_text(strip=True):
        title_candidates.append(soup.title.get_text(strip=True))

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content"):
        title_candidates.append(og_title.get("content"))

    for text in title_candidates:
        # 允許代號後面直接接中文名稱，例如「00991A主動復華...」
        match = re.search(r"(\d{4,5}[A-Z])", text)
        if match:
            return match.group(1)

    # 次優先：抓 4 碼純數字 ETF 代號（例如 0050）
    for text in title_candidates:
        match = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
        if match:
            return match.group(1)

    # 退回網址 query 參數（例如 fundCode=49YTW）
    parsed = urlparse(page_url)
    query = parse_qs(parsed.query)
    for key in ("fundCode", "code", "etfCode", "fundNo"):
        if key in query and query[key]:
            return query[key][0]

    return "UNKNOWN"


def detect_site_type(url: str) -> str:
    """根據 URL 判斷網站類型"""
    domain = urlparse(url).netloc.lower()
    
    if "fhtrust" in domain:
        return "fhtrust"
    elif "capitalfund" in domain:
        return "capitalfund"
    elif "ezmoney" in domain:
        return "ezmoney"
    elif "nomurafunds" in domain:
        return "nomurafunds"
    elif "ctbcinvestments" in domain:
        return "ctbcinvestments"
    elif "allianzgi" in domain:
        return "allianzgi"
    elif "tsit" in domain:
        return "tsit"
    elif "fsitc" in domain:
        return "fsitc"
    elif "megafunds" in domain:
        return "megafunds"
    elif "cathaysite" in domain:
        return "cathaysite"
    elif "jpmorgan" in domain:
        return "jpmorgan"
    else:
        return "unknown"


def scrape_fhtrust(driver, soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """復華 ETF 站：table.etfStockTable"""
    stocks = []

    row_sel = "table.etfStockTable tbody tr"

    # 防線：若頁面尚未渲染股票表，再等最多 20 秒
    try:
        WebDriverWait(driver, 20).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, row_sel)) > 0
        )
    except Exception:
        print("  [fhtrust] etfStockTable 仍未出現（將以目前 DOM 嘗試）", flush=True)

    def _row_count() -> int:
        try:
            return len(driver.find_elements(By.CSS_SELECTOR, row_sel))
        except Exception:
            return 0

    # 嘗試點擊「展開更多」按鈕，把所有持股展開
    # 改善：今日測試 00991A 失敗，原因是 wait 5s 太短、且點擊後 button 仍可見
    # 會在「row 數還沒增加」時就反覆嘗試。新策略：
    #   1) 點擊後最長等 15s 等 row 數成長
    #   2) 若 row 數已穩定（連兩輪相同）即視為展開完成
    #   3) 偵測網路尚未回應時，多滾動觸發 lazy load
    try:
        last_count = _row_count()
        stable_rounds = 0
        for _ in range(25):
            buttons = [
                b for b in driver.find_elements(By.CSS_SELECTOR, "button.fundTable-toggle")
                if b.is_displayed()
            ]
            if not buttons:
                break
            btn = buttons[0]
            btn_text = (btn.text or "").strip()
            # 「展開更多」才點；若按鈕變成「收合」就停
            if btn_text and ("收" in btn_text or "less" in btn_text.lower() or "hide" in btn_text.lower()):
                break

            prev_count = _row_count()
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", btn)
            except Exception as e:
                print(f"  [fhtrust] 點擊失敗: {e}", flush=True)
                break

            # 等 row 數成長（最多 15 秒）
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, row_sel)) > prev_count
                )
            except Exception:
                # 沒成長：滾動再試一次，仍沒變就計入穩定計數
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2.0)

            cur = _row_count()
            if cur == last_count:
                stable_rounds += 1
                if stable_rounds >= 2:
                    break
            else:
                stable_rounds = 0
                last_count = cur
        print(f"  [fhtrust] 展開後 row={_row_count()}", flush=True)
    except Exception as e:
        print(f"  展開按鈕失敗（略過）: {e}")

    # 重新解析已展開的頁面
    soup = BeautifulSoup(driver.page_source, "html.parser")
    fh_table = soup.select_one("table.etfStockTable")

    if fh_table:
        for row in fh_table.select("tbody tr"):
            cols = row.find_all("td")
            if len(cols) >= 5:
                stock = {
                    "股票代號": cols[0].get_text(strip=True),
                    "股票名稱": cols[1].get_text(strip=True),
                    "股數": cols[2].get_text(strip=True),
                    "金額": cols[3].get_text(strip=True),
                    "持股比例": cols[4].get_text(strip=True),
                    "ETF股票代號": etf_stock_code,
                }
                if stock["股票代號"]:
                    stocks.append(stock)

    return stocks


def scrape_capitalfund(soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """群益站：div 表格"""
    stocks = []
    stock_body = soup.select_one(".pct-stock-table-tbody")
    
    if stock_body:
        rows = stock_body.select(".tr.show-for-medium")
        for row in rows:
            cols = row.find_all("div", recursive=False)
            if len(cols) >= 4:
                stock = {
                    "股票代號": cols[0].get_text(strip=True),
                    "股票名稱": cols[1].get_text(strip=True),
                    "持股比例": cols[2].get_text(strip=True),
                    "股數": cols[3].get_text(strip=True),
                    "ETF股票代號": etf_stock_code
                }
                if stock["股票代號"] and stock["股票名稱"]:
                    stocks.append(stock)
    
    return stocks


def _extract_ymd_from_filename(path: str, prefix: str) -> Optional[str]:
    """從檔名抓 YYYYMMDD，例如 stock_shares_diff_20260514.json。"""
    name = os.path.basename(path)
    m = re.match(rf"^{re.escape(prefix)}_(\d{{8}})\.json$", name)
    return m.group(1) if m else None


def _build_weekly_inventory_series_from_diff(stock_shares_dir: str, window_days: int = 7):
    """用 diff 檔回推出近 N 個交易日各股票總庫存。

    回傳：
        dates: 依時間升冪的 YYYYMMDD 陣列
        series: {股票代號: [day1_qty, day2_qty, ...]}
        name_map: {股票代號: 股票名稱}
    """
    latest_summary_path = os.path.join(stock_shares_dir, "stock_shares_summary.json")
    if not os.path.exists(latest_summary_path):
        return [], {}, {}

    with open(latest_summary_path, "r", encoding="utf-8") as f:
        latest_summary = json.load(f)

    latest_stocks = latest_summary.get("stocks", [])
    if not latest_stocks:
        return [], {}, {}

    current_map: Dict[str, int] = {}
    name_map: Dict[str, str] = {}
    for row in latest_stocks:
        code = str(row.get("股票代號") or "").strip()
        if not code:
            continue
        current_map[code] = int(row.get("總股數") or 0)
        name_map[code] = str(row.get("股票名稱") or "").strip()

    diff_files_all = []
    for p in glob.glob(os.path.join(stock_shares_dir, "stock_shares_diff_*.json")):
        d = _extract_ymd_from_filename(p, "stock_shares_diff")
        if d:
            diff_files_all.append((d, p))

    if not diff_files_all:
        return [], {}, {}

    diff_files_all.sort(key=lambda x: x[0])
    selected = diff_files_all[-window_days:]
    dates = [d for d, _ in selected]
    if len(dates) < 2:
        return [], {}, {}

    diff_by_date = {}
    for d, p in selected:
        try:
            with open(p, "r", encoding="utf-8") as f:
                diff_by_date[d] = json.load(f)
        except Exception as e:
            print(f"  讀取 diff 失敗 {p}: {e}")
            return [], {}, {}

    if "included_etfs" in latest_summary:
        scope = _summary_etf_scope(latest_summary)
        dates = [d for d in dates if diff_by_date[d].get("included_etfs") == scope]
        if len(dates) < 2:
            return [], {}, {}

    qty_map_by_date: Dict[str, Dict[str, int]] = {}

    # 以最新日庫存做基準，逐日往前回推
    last_date = dates[-1]
    qty_map_by_date[last_date] = dict(current_map)

    for i in range(len(dates) - 1, 0, -1):
        d_cur = dates[i]
        d_prev = dates[i - 1]
        payload = diff_by_date.get(d_cur, {})
        cur_map = qty_map_by_date[d_cur]
        prev_map = dict(cur_map)

        # 一般持股異動：prev = cur - delta
        for row in payload.get("持股異動", []):
            code = str(row.get("股票代號") or "").strip()
            if not code:
                continue
            delta = int(row.get("總股數差異") or 0)
            prev_map[code] = int(cur_map.get(code, 0)) - delta
            if not name_map.get(code):
                name_map[code] = str(row.get("股票名稱") or "").strip()

        # 新增個股：前一日應為 0
        for row in payload.get("新增個股", []):
            code = str(row.get("股票代號") or "").strip()
            if not code:
                continue
            prev_map[code] = 0
            if not name_map.get(code):
                name_map[code] = str(row.get("股票名稱") or "").strip()

        # 移除個股：前一日為前次總股數
        for row in payload.get("移除個股", []):
            code = str(row.get("股票代號") or "").strip()
            if not code:
                continue
            prev_map[code] = int(row.get("前次總股數") or 0)
            if not name_map.get(code):
                name_map[code] = str(row.get("股票名稱") or "").strip()

        qty_map_by_date[d_prev] = prev_map

    # 日期順序序列化成每檔股票 list
    all_codes = set()
    for d in dates:
        all_codes.update(qty_map_by_date.get(d, {}).keys())

    series: Dict[str, List[int]] = {}
    for code in all_codes:
        series[code] = [int(qty_map_by_date.get(d, {}).get(code, 0)) for d in dates]

    return dates, series, name_map


def _calc_axis_range(values: List[int]) -> Tuple[int, int, int]:
    """計算圖表 Y 軸區間與主刻度，避免科學記號並提高可讀性。"""
    if not values:
        return 0, 1, 1

    import math

    v_min = min(values)
    v_max = max(values)

    if v_min == v_max:
        pad = max(1, int(abs(v_max) * 0.1))
        v_min -= pad
        v_max += pad

    span = max(1, v_max - v_min)
    raw_major = max(1, int(math.ceil(span / 6)))

    # 使用 1/2/5 * 10^n 的漂亮刻度
    base = 10 ** int(math.floor(math.log10(raw_major))) if raw_major > 0 else 1
    major = base
    for m in (1, 2, 5, 10):
        major = m * base
        if major >= raw_major:
            break

    y_min = int(math.floor(v_min / major) * major)
    y_max = int(math.ceil(v_max / major) * major)
    if y_min == y_max:
        y_max = y_min + major

    return y_min, y_max, major


def generate_weekly_inventory_charts(
    stock_shares_dir: str,
    window_days: int = 7,
    top_n: int = 20,
    include_all_changed: bool = True,
) -> None:
    """利用 diff 產生近一週個股每日庫存折線圖。"""
    try:
        import importlib

        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        plt = importlib.import_module("matplotlib.pyplot")
        mticker = importlib.import_module("matplotlib.ticker")

        openpyxl = importlib.import_module("openpyxl")
        Workbook = openpyxl.Workbook
        LineChart = importlib.import_module("openpyxl.chart").LineChart
        Reference = importlib.import_module("openpyxl.chart").Reference
        Font = importlib.import_module("openpyxl.styles").Font
        Alignment = importlib.import_module("openpyxl.styles").Alignment
    except Exception as e:
        print(f"  略過折線圖輸出：matplotlib 無法使用 ({e})")
        return

    dates, series, name_map = _build_weekly_inventory_series_from_diff(stock_shares_dir, window_days=window_days)
    if len(dates) < 2 or not series:
        print("  略過折線圖輸出：diff 資料不足（至少需 2 個交易日）")
        return

    # 中文字型與負號設定
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # 挑選近一週有異動的個股（可選擇是否只取前 N 檔）
    ranked = []
    for code, arr in series.items():
        if not arr:
            continue
        weekly_change = abs(arr[-1] - arr[0])
        max_qty = max(arr)
        ranked.append((weekly_change, max_qty, code))
    ranked.sort(reverse=True)

    changed_codes = [x[2] for x in ranked if x[0] != 0]
    if include_all_changed:
        selected_codes = changed_codes
    else:
        selected_codes = changed_codes[:top_n]
    if not selected_codes:
        print("  略過折線圖輸出：近一週無異動個股資料")
        return

    chart_dir = os.path.join(stock_shares_dir, "charts_weekly")
    os.makedirs(chart_dir, exist_ok=True)

    x_labels = [f"{d[4:6]}/{d[6:8]}" for d in dates]
    date_tag = dates[-1]
    range_tag = f"{dates[0]}_{dates[-1]}"

    net_change_map = {code: (series[code][-1] - series[code][0]) for code in selected_codes}
    increase_codes = [code for code in selected_codes if net_change_map.get(code, 0) > 0]
    decrease_codes = [code for code in selected_codes if net_change_map.get(code, 0) < 0]

    def _save_overview_png(codes: List[str], title: str, out_path: str, line_color: Optional[str] = None) -> bool:
        if not codes:
            return False
        plt.figure(figsize=(16, 9))
        all_values: List[int] = []
        for code in codes:
            name = name_map.get(code) or code
            if line_color:
                plt.plot(x_labels, series[code], marker="o", linewidth=1.8, color=line_color, alpha=0.85, label=f"{code} {name}")
            else:
                plt.plot(x_labels, series[code], marker="o", linewidth=1.8, alpha=0.85, label=f"{code} {name}")
            all_values.extend(series[code])
        y_min, y_max, y_major = _calc_axis_range(all_values)
        ax = plt.gca()
        ax.set_ylim(y_min, y_max)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(y_major))
        ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
        plt.title(title)
        plt.xlabel("日期")
        plt.ylabel("總庫存股數")
        plt.grid(True, linestyle="--", alpha=0.35)
        plt.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
        plt.tight_layout(rect=[0, 0, 0.82, 1])
        plt.savefig(out_path, dpi=180)
        plt.close()
        return True

    # 1) 產出總覽圖：增加/減少各每 5 個一張
    BATCH = 5
    inc_png_paths: List[str] = []
    for batch_idx, i in enumerate(range(0, len(increase_codes), BATCH), start=1):
        batch = increase_codes[i : i + BATCH]
        path = os.path.join(chart_dir, f"weekly_inventory_overview_increase_{batch_idx:02d}_{date_tag}.png")
        _save_overview_png(
            batch,
            f"近 {len(dates)} 個交易日庫存量趨勢（股數增加 第{batch_idx}組/{-(-len(increase_codes)//BATCH)}組）",
            path,
            line_color="#1f77b4",
        )
        inc_png_paths.append(path)

    dec_png_paths: List[str] = []
    for batch_idx, i in enumerate(range(0, len(decrease_codes), BATCH), start=1):
        batch = decrease_codes[i : i + BATCH]
        path = os.path.join(chart_dir, f"weekly_inventory_overview_decrease_{batch_idx:02d}_{date_tag}.png")
        _save_overview_png(
            batch,
            f"近 {len(dates)} 個交易日庫存量趨勢（股數減少 第{batch_idx}組/{-(-len(decrease_codes)//BATCH)}組）",
            path,
            line_color="#d62728",
        )
        dec_png_paths.append(path)

    # 2) 產出個股單圖（全部異動檔）
    for code in selected_codes:
        name = name_map.get(code) or code
        safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", name)[:40]
        plt.figure(figsize=(11, 5))
        plt.plot(x_labels, series[code], marker="o", linewidth=2.3, color="#1f77b4")
        y_min, y_max, y_major = _calc_axis_range(series[code])
        ax = plt.gca()
        ax.set_ylim(y_min, y_max)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(y_major))
        ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
        plt.title(f"{code} {name} - 近 {len(dates)} 個交易日庫存量")
        plt.xlabel("日期")
        plt.ylabel("總庫存股數")
        plt.grid(True, linestyle="--", alpha=0.4)
        plt.tight_layout()
        single_path = os.path.join(chart_dir, f"weekly_inventory_{code}_{safe_name}_{date_tag}.png")
        plt.savefig(single_path, dpi=180)
        plt.close()

    # 3) 匯出時序資料（全部異動檔）
    lines = ["股票代號,股票名稱," + ",".join(dates)]
    for code in selected_codes:
        name = (name_map.get(code) or "").replace(",", " ")
        values = ",".join(str(v) for v in series[code])
        lines.append(f"{code},{name},{values}")
    csv_path = os.path.join(chart_dir, f"weekly_inventory_top_stocks_{date_tag}.csv")
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    # 4) 匯出 Excel（含資料與折線圖）
    wb = Workbook()
    wb.remove(wb.active)

    def _add_overview_sheet(sheet_title: str, codes: List[str], chart_title: str):
        ws = wb.create_sheet(sheet_title)
        header = ["股票代號", "圖例名稱"] + dates
        ws.append(header)
        for c in range(1, len(header) + 1):
            ws.cell(row=1, column=c).font = Font(bold=True)
            ws.cell(row=1, column=c).alignment = Alignment(horizontal="center")

        for code in codes:
            name = name_map.get(code) or ""
            legend_name = f"{code} {name}".strip()
            ws.append([code, legend_name] + series[code])

        for row in ws.iter_rows(min_row=2, max_row=1 + len(codes), min_col=3, max_col=2 + len(dates)):
            for cell in row:
                cell.number_format = "#,##0"
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 30
        for i in range(len(dates)):
            col_letter = ws.cell(row=1, column=3 + i).column_letter
            ws.column_dimensions[col_letter].width = 11

        if not codes:
            ws["A3"] = "近一週沒有符合條件的個股"
            return

        chart = LineChart()
        chart.title = chart_title
        chart.y_axis.title = "總庫存股數"
        chart.x_axis.title = "日期"
        chart.y_axis.number_format = "#,##0"
        ov_values: List[int] = []
        for r in range(2, 2 + len(codes)):
            data = Reference(ws, min_col=2, min_row=r, max_col=2 + len(dates), max_row=r)
            chart.add_data(data, from_rows=True, titles_from_data=True)
            ov_values.extend(series.get(str(ws.cell(row=r, column=1).value), []))

        cats = Reference(ws, min_col=3, min_row=1, max_col=2 + len(dates), max_row=1)
        chart.set_categories(cats)
        y_min, y_max, y_major = _calc_axis_range(ov_values)
        chart.y_axis.scaling.min = y_min
        chart.y_axis.scaling.max = y_max
        chart.y_axis.majorUnit = y_major
        chart.height = 11
        chart.width = 20
        ws.add_chart(chart, "A25")

    if increase_codes:
        for batch_idx, i in enumerate(range(0, len(increase_codes), BATCH), start=1):
            batch = increase_codes[i : i + BATCH]
            _add_overview_sheet(
                f"新增_{batch_idx:02d}"[:31],
                batch,
                f"近 {len(dates)} 個交易日庫存量趨勢（股數增加 第{batch_idx}組）",
            )

    if decrease_codes:
        for batch_idx, i in enumerate(range(0, len(decrease_codes), BATCH), start=1):
            batch = decrease_codes[i : i + BATCH]
            _add_overview_sheet(
                f"減少_{batch_idx:02d}"[:31],
                batch,
                f"近 {len(dates)} 個交易日庫存量趨勢（股數減少 第{batch_idx}組）",
            )

    # 個股分頁與圖表
    for code in selected_codes:
        name = name_map.get(code) or ""
        clean_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", name)[:20]
        sheet_name = f"{code}_{clean_name}"
        if not sheet_name:
            sheet_name = code
        sheet_name = sheet_name[:31]
        if sheet_name in wb.sheetnames:
            sheet_name = f"{code}_{len(wb.sheetnames)}"[:31]

        ws_s = wb.create_sheet(sheet_name)
        ws_s.append(["日期", "庫存量"])
        ws_s["A1"].font = Font(bold=True)
        ws_s["B1"].font = Font(bold=True)

        values = series[code]
        for idx, d in enumerate(dates):
            ws_s.append([d, values[idx]])

        for cell in ws_s["B"][1:]:
            cell.number_format = "#,##0"
        ws_s.column_dimensions["A"].width = 12
        ws_s.column_dimensions["B"].width = 14

        c = LineChart()
        c.title = f"{code} {name} - 近 {len(dates)} 日庫存"
        c.y_axis.title = "總庫存股數"
        c.x_axis.title = "日期"
        c.y_axis.number_format = "#,##0"
        dref = Reference(ws_s, min_col=2, min_row=1, max_col=2, max_row=1 + len(dates))
        cref = Reference(ws_s, min_col=1, min_row=2, max_col=1, max_row=1 + len(dates))
        c.add_data(dref, titles_from_data=True)
        c.set_categories(cref)
        y_min, y_max, y_major = _calc_axis_range(values)
        c.y_axis.scaling.min = y_min
        c.y_axis.scaling.max = y_max
        c.y_axis.majorUnit = y_major
        c.height = 8
        c.width = 14
        ws_s.add_chart(c, "D2")

    excel_path = os.path.join(chart_dir, f"weekly_inventory_report_{range_tag}_{date_tag}.xlsx")
    try:
        wb.save(excel_path)
    except PermissionError:
        alt_tag = datetime.datetime.now().strftime("%H%M%S")
        excel_path = os.path.join(chart_dir, f"weekly_inventory_report_{range_tag}_{date_tag}_{alt_tag}.xlsx")
        wb.save(excel_path)

    print(f"✓ 已輸出近一週庫存折線圖到 {chart_dir}")
    print(f"  - 總覽圖(新增): {len(inc_png_paths)} 張（{len(increase_codes)} 檔，每 {BATCH} 個一張）")
    print(f"  - 總覽圖(減少): {len(dec_png_paths)} 張（{len(decrease_codes)} 檔，每 {BATCH} 個一張）")
    print(f"  - 異動個股圖數: {len(selected_codes)}")
    print(f"  - 時序資料(全異動): {os.path.basename(csv_path)}")
    print(f"  - Excel 報表: {os.path.basename(excel_path)}")


# 程式生命週期內快取（避免同一日多次抓 API）
_PRICE_CACHE: Dict[str, Dict[str, float]] = {}
# TPEX 個股月度歷史快取：key = (code, "YYYYMM") -> {YYYYMMDD: close}
_TPEX_STOCK_MONTH_CACHE: Dict[Tuple[str, str], Dict[str, float]] = {}


def _fetch_twse_closes(date_yyyymmdd: str) -> Dict[str, float]:
    """抓 TWSE 上市某日收盤價（key 為股票代號）。"""
    out: Dict[str, float] = {}
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_yyyymmdd}&type=ALL&response=json"
    try:
        data = _http_get_json(url, timeout=30)
    except Exception as e:
        print(f"  TWSE 收盤價查詢失敗 ({date_yyyymmdd}): {e}")
        return out

    # 兩種版本：data["tables"] 或舊式單 table
    tables = data.get("tables") or []
    if not tables and "fields" in data:
        tables = [data]
    for tbl in tables:
        fields = tbl.get("fields") or []
        if "證券代號" in fields and "收盤價" in fields:
            ci = fields.index("證券代號")
            pi = fields.index("收盤價")
            for row in tbl.get("data", []):
                if len(row) <= max(ci, pi):
                    continue
                code = str(row[ci]).strip()
                raw = str(row[pi]).replace(",", "").strip()
                try:
                    out[code] = float(raw)
                except ValueError:
                    pass
    return out


def _fetch_tpex_closes(date_yyyymmdd: str) -> Dict[str, float]:
    """抓 TPEX 上櫃某日收盤價（key 為股票代號）。"""
    out: Dict[str, float] = {}
    try:
        roc_year = int(date_yyyymmdd[:4]) - 1911
    except Exception:
        return out
    roc_date = f"{roc_year}/{date_yyyymmdd[4:6]}/{date_yyyymmdd[6:8]}"
    url = (
        "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/"
        f"stk_quote_result.php?l=zh-tw&d={roc_date}"
    )

    # TPEX 偶有 IncompleteRead，加入重試
    data = None
    last_err = None
    for _ in range(3):
        try:
            data = _http_get_json(url, timeout=45)
            break
        except Exception as e:
            last_err = e
    if data is None:
        print(f"  TPEX 收盤價查詢失敗 ({date_yyyymmdd}): {last_err}")
        return out

    # 新版回應為 {tables:[{fields:[...], data:[...]}]}
    # 注意：此端點目前不論 d= 參數一律回最新一日資料，因此需驗證 response.date 是否符合
    resp_date = str(data.get("date") or "").strip()
    if resp_date and resp_date != date_yyyymmdd:
        return out
    tables = data.get("tables") or []
    for tbl in tables:
        fields = tbl.get("fields") or []
        # 欄位可能含後綴空白，做寬鬆比對
        norm = [str(f).strip() for f in fields]
        try:
            ci = next(i for i, n in enumerate(norm) if n in ("代號", "證券代號"))
            pi = next(i for i, n in enumerate(norm) if n in ("收盤", "收盤價"))
        except StopIteration:
            continue
        for row in tbl.get("data", []) or []:
            if len(row) <= max(ci, pi):
                continue
            code = str(row[ci]).strip()
            raw = str(row[pi]).replace(",", "").strip()
            try:
                out[code] = float(raw)
            except ValueError:
                pass

    # 舊版 aaData 相容（保險）
    if not out:
        for row in data.get("aaData", []) or []:
            if len(row) < 3:
                continue
            code = str(row[0]).strip()
            raw = str(row[2]).replace(",", "").strip()
            try:
                out[code] = float(raw)
            except ValueError:
                pass
    return out


def _fetch_tpex_openapi_latest() -> Dict[str, float]:
    """TPEX OpenAPI（最新一日）作為當日上櫃價的備援。"""
    out: Dict[str, float] = {}
    try:
        data = _http_get_json(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=45,
        )
    except Exception as e:
        print(f"  TPEX OpenAPI 查詢失敗: {e}")
        return out
    if not isinstance(data, list):
        return out
    for row in data:
        try:
            code = str(row.get("SecuritiesCompanyCode") or "").strip()
            close = str(row.get("Close") or "").replace(",", "").strip()
            if code and close:
                out[code] = float(close)
        except Exception:
            continue
    return out


def _fetch_tpex_openapi_latest_with_date() -> Optional[Tuple[str, Dict[str, float]]]:
    """同 _fetch_tpex_openapi_latest，但會額外回傳 OpenAPI 標示的日期 (YYYYMMDD)。"""
    try:
        data = _http_get_json(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=45,
        )
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    raw_date = str(data[0].get("Date") or "").strip()
    # 民國格式 1150522 -> 20260522
    api_date = ""
    if raw_date.isdigit() and len(raw_date) == 7:
        api_date = f"{int(raw_date[:3]) + 1911}{raw_date[3:]}"
    out: Dict[str, float] = {}
    for row in data:
        try:
            code = str(row.get("SecuritiesCompanyCode") or "").strip()
            close = str(row.get("Close") or "").replace(",", "").strip()
            if code and close:
                out[code] = float(close)
        except Exception:
            continue
    return api_date, out


def get_tw_closing_prices(date_yyyymmdd: str) -> Dict[str, float]:
    """合併上市 + 上櫃收盤價。"""
    if not date_yyyymmdd:
        return {}
    if date_yyyymmdd in _PRICE_CACHE:
        return _PRICE_CACHE[date_yyyymmdd]
    merged: Dict[str, float] = {}
    merged.update(_fetch_twse_closes(date_yyyymmdd))
    tpex = _fetch_tpex_closes(date_yyyymmdd)
    for k, v in tpex.items():
        merged.setdefault(k, v)
    # 若 TPEX 歷史查不到，再以 OpenAPI（最新一日）補上櫃資料；但只有當請求的日期就是 OpenAPI 的日期才採用
    if not tpex:
        try:
            api_data = _fetch_tpex_openapi_latest_with_date()
            api_date, api_prices = api_data if api_data else (None, {})
            if api_date == date_yyyymmdd:
                for k, v in api_prices.items():
                    merged.setdefault(k, v)
        except Exception:
            pass
    _PRICE_CACHE[date_yyyymmdd] = merged
    return merged


def _fetch_tpex_stock_month(code: str, yyyymm: str) -> Dict[str, float]:
    """抓 TPEX 個股某月份的日收盤。回傳 {YYYYMMDD: close}。

    TPEX 端點：tradingStock?code=XXXX&date=民國年/MM/01&response=json
    若 date 無法被接受時，端點會回當月資料；故仍以代號為主要 key 並用回傳 row 的日期解析。
    """
    key = (code, yyyymm)
    if key in _TPEX_STOCK_MONTH_CACHE:
        return _TPEX_STOCK_MONTH_CACHE[key]
    out: Dict[str, float] = {}
    try:
        roc = int(yyyymm[:4]) - 1911
        roc_date = f"{roc}/{yyyymm[4:6]}/01"
    except Exception:
        roc_date = ""
    urls = [
        f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={code}&date={roc_date}&id=&response=json",
        f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={code}&id=&response=json",
    ]
    data = None
    for url in urls:
        try:
            d = _http_get_json(url, timeout=30)
            if isinstance(d, dict) and (d.get("tables") or d.get("data")):
                data = d
                break
        except Exception:
            continue
    if not data:
        _TPEX_STOCK_MONTH_CACHE[key] = out
        return out

    rows = []
    tables = data.get("tables") or []
    if tables:
        rows = tables[0].get("data") or []
    else:
        rows = data.get("data") or []

    for row in rows:
        if not row or len(row) < 7:
            continue
        # 欄位：日期(民國), 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, 漲跌, 成交筆數
        raw_date = str(row[0]).strip()
        raw_close = str(row[6]).replace(",", "").strip()
        m = re.match(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$", raw_date)
        if not m:
            continue
        ad_year = int(m.group(1)) + 1911
        ymd = f"{ad_year:04d}{int(m.group(2)):02d}{int(m.group(3)):02d}"
        try:
            out[ymd] = float(raw_close)
        except ValueError:
            pass
    _TPEX_STOCK_MONTH_CACHE[key] = out
    return out


def get_close_price(code: str, date_yyyymmdd: str) -> Optional[float]:
    """取個股某日收盤價。優先 TWSE 批次（含修好的 TPEX 當日），不在則查 TPEX 個股月歷史。"""
    if not code or not date_yyyymmdd:
        return None
    head = code.strip().split()[0]
    prices = get_tw_closing_prices(date_yyyymmdd)
    p = _lookup_price(prices, code)
    if p is not None:
        return p
    # 退而求其次：TPEX 個股月歷史
    month = _fetch_tpex_stock_month(head, date_yyyymmdd[:6])
    return month.get(date_yyyymmdd)


def _lookup_price(prices: Dict[str, float], code: str) -> Optional[float]:
    """股票代號可能含後綴（如 '6981 JP'、'2330 TT'），先取純代號嘗試。"""
    if not code:
        return None
    code = code.strip()
    if code in prices:
        return prices[code]
    head = code.split()[0]
    return prices.get(head)


def _attach_market_values(item: Dict, shares_field: str, prices: Dict[str, float],
                          price_date: str = "") -> None:
    """根據總股數補上 當日收盤價 / 目前總投入金額 / 每1000股成本均值（單日估算備援用）。"""
    code = str(item.get("股票代號") or "").strip()
    shares = int(item.get(shares_field) or 0)
    price = _lookup_price(prices, code)
    if price is None and price_date:
        # TPEX 個股月歷史備援
        price = get_close_price(code, price_date)
    if price is None:
        item.setdefault("當日收盤價", None)
        item.setdefault("目前總投入金額", None)
        item.setdefault("每1000股成本均值", None)
        return
    item["當日收盤價"] = round(float(price), 4)
    item["目前總投入金額"] = int(round(price * shares))
    item["每1000股成本均值"] = round(price * 1000, 2)


def _compute_cumulative_cost(history: List[Dict]) -> Tuple[Optional[float], Optional[float]]:
    """依由新到舊的 history（含 date/總股數/收盤價）回算結算累計成本與平均每1000股成本。

    規則：每日新增股數視為以該日收盤價買進；股數減少時按比例沖銷既有成本。
    回傳 (累計投入成本, 每1000股平均成本)；資料不足回 (None, None)。
    """
    if not history:
        return None, None
    ordered = list(reversed(history))  # 由舊到新
    cum_shares = 0
    cum_cost = 0.0
    for h in ordered:
        try:
            shares = int(h.get("總股數") or 0)
        except Exception:
            shares = 0
        price = h.get("收盤價")
        try:
            price = float(price) if price not in (None, "") else None
        except Exception:
            price = None
        delta = shares - cum_shares
        if price is None and (delta > 0 or (delta < 0 and shares > 0)):
            return None, None
        if cum_shares == 0:
            if price is not None and shares > 0:
                cum_cost = price * shares
            cum_shares = shares
        elif delta > 0:
            if price is not None:
                cum_cost += price * delta
            cum_shares = shares
        elif delta < 0:
            # 股數減少：以當日收盤價計算賣出金額，從累計成本扣除（實現反映）
            if price is not None:
                cum_cost -= price * (-delta)
            cum_shares = shares
    if cum_shares <= 0 or cum_cost <= 0:
        return None, None
    avg_per_k = cum_cost / cum_shares * 1000
    return cum_cost, avg_per_k


def enrich_diff_with_market_values(diff_summary: Dict, price_date: str,
                                    stock_shares_dir: Optional[str] = None) -> Dict:
    """依 price_date 收盤價，補上每檔個股估值欄位。

    若提供 stock_shares_dir，會用近期 summary 檔回算累計投入成本與平均每1000股成本；
    否則回退為「當日收盤價 × 總股數」之單日估算。
    """
    if not diff_summary:
        return diff_summary
    prices = get_tw_closing_prices(price_date) if price_date else {}
    if not prices:
        print(f"  注意：{price_date} 沒抓到任何收盤價，估值欄位將為 None。")

    for it in diff_summary.get("新增個股", []) or []:
        _attach_market_values(it, "總股數", prices, price_date=price_date)
    for it in diff_summary.get("持股異動", []) or []:
        _attach_market_values(it, "本次總股數", prices, price_date=price_date)

    if stock_shares_dir:
        all_items = list(diff_summary.get("新增個股", []) or []) + list(diff_summary.get("持股異動", []) or [])
        codes = []
        seen = set()
        for it in all_items:
            c = str(it.get("股票代號") or "").strip()
            if c and c not in seen:
                seen.add(c)
                codes.append(c)
        try:
            history_map = build_stock_5d_history(stock_shares_dir, codes, price_date, days=30)
        except Exception as e:
            print(f"  累計成本回算失敗：{e}")
            history_map = {}
        for it in all_items:
            c = str(it.get("股票代號") or "").strip()
            hist = history_map.get(c) or []
            cum_cost, avg_per_k = _compute_cumulative_cost(hist)
            # 不把資料不足的累計成本偽裝成已知成本。
            it["目前總投入金額"] = int(round(cum_cost)) if cum_cost is not None else None
            it["每1000股成本均值"] = round(avg_per_k, 2) if avg_per_k is not None else None

    diff_summary["收盤價基準日"] = price_date
    return diff_summary


def build_stock_5d_history(stock_shares_dir: str, codes: List[str], end_date: str,
                           days: int = 10) -> Dict[str, List[Dict]]:
    """為指定股票代號彙整近 days 個交易日（依現有 summary 檔）的庫存與收盤價/估值。

    回傳：{code: [{date, 總股數, 收盤價, 總投入金額}, ...]}  依日期由新到舊。
    """
    if not codes:
        return {}

    # 收集 summary 檔（檔名格式 stock_shares_summary_YYYYMMDD.json）
    files = []
    pattern = re.compile(r"stock_shares_summary_(\d{8})\.json$")
    for fname in os.listdir(stock_shares_dir):
        m = pattern.search(fname)
        if not m:
            continue
        ymd = m.group(1)
        if end_date and ymd > end_date:
            continue
        files.append((ymd, os.path.join(stock_shares_dir, fname)))
    files.sort(key=lambda x: x[0], reverse=True)
    files = files[:days]
    if not files:
        return {}

    code_set = {str(c).strip() for c in codes if c}
    history: Dict[str, List[Dict]] = {c: [] for c in code_set}

    reference_scope = None
    for ymd, path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except Exception as e:
            print(f"  讀取 {os.path.basename(path)} 失敗：{e}")
            continue

        scope = _summary_etf_scope(snap)
        if reference_scope is None:
            reference_scope = scope
        elif scope != reference_scope:
            # 統計範圍改變不是買賣，不跨越此邊界回算成本。
            break

        stocks = snap.get("stocks", []) or []
        by_code: Dict[str, Dict] = {}
        for s in stocks:
            c = str(s.get("股票代號") or "").strip()
            if c in code_set:
                by_code[c] = s

        prices = get_tw_closing_prices(ymd)

        for c in code_set:
            s = by_code.get(c)
            shares = int((s or {}).get("總股數") or 0)
            price = _lookup_price(prices, c) if prices else None
            if price is None:
                # 退而求其次：TPEX 個股月歷史
                price = get_close_price(c, ymd)
            entry = {
                "date": ymd,
                "總股數": shares,
                "收盤價": round(float(price), 4) if price is not None else None,
                "目前總投入金額": int(round(price * shares)) if (price is not None and shares) else None,
                "ETF明細": list((s or {}).get("ETF明細", []) or []),
            }
            history[c].append(entry)

    return history


def generate_diff_html_report(stock_shares_dir: str, diff_summary: Dict, today: str) -> Optional[str]:
        """依 diff 產生網頁報表（三分類）：新增、原持有增加、原持有減少。"""
        if not diff_summary:
                return None

        report_dir = os.path.join(stock_shares_dir, "web_reports")
        os.makedirs(report_dir, exist_ok=True)

        # 補上收盤價 / 估值欄位（若尚未填入）
        price_date = str(diff_summary.get("date") or today or "")
        enrich_diff_with_market_values(diff_summary, price_date, stock_shares_dir=stock_shares_dir)

        # 取「前次」收盤價（給 ETP 細項使用）
        prev_date = str(diff_summary.get("previous_date") or "")
        prev_prices = get_tw_closing_prices(prev_date) if prev_date else {}

        summary_candidates = [
            os.path.join(stock_shares_dir, f"stock_shares_summary_{price_date}.json"),
            os.path.join(stock_shares_dir, "stock_shares_summary.json"),
        ]
        all_stock_rows: List[Dict] = []
        for summary_path in summary_candidates:
            if not os.path.exists(summary_path):
                continue
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary_payload = json.load(f)
                all_stock_rows = list(summary_payload.get("stocks", []) or [])
                if all_stock_rows:
                    break
            except Exception as e:
                print(f"  讀取全量個股清單失敗 {summary_path}: {e}")
        all_stock_rows.sort(key=lambda x: int(x.get("總股數") or 0), reverse=True)

        new_stocks = list(diff_summary.get("新增個股", []))
        changed = list(diff_summary.get("持股異動", []))

        existed_increase = [
                x for x in changed
                if int(x.get("前次總股數") or 0) > 0 and int(x.get("總股數差異") or 0) > 0
        ]
        existed_decrease = [
                x for x in changed
                if int(x.get("前次總股數") or 0) > 0 and int(x.get("總股數差異") or 0) < 0
        ]

        # 變動大至小排序：新增以本次總股數視為變動量
        new_stocks.sort(key=lambda x: abs(int(x.get("總股數") or 0)), reverse=True)
        existed_increase.sort(key=lambda x: abs(int(x.get("總股數差異") or 0)), reverse=True)
        existed_decrease.sort(key=lambda x: abs(int(x.get("總股數差異") or 0)), reverse=True)

        def _fmt_int(v) -> str:
                try:
                        return f"{int(v):,}"
                except Exception:
                        return str(v)

        _etf_color_map = {
                '00980A': 1, '00982A': 2, '00981A': 3, '00984A': 4,
                '00985A': 5, '00986A': 6, '00991A': 7, '00987A': 8,
                '00992A': 9, '00994A': 10, '00995A': 11, '00993A': 12,
                '00996A': 13, '00400A': 14, '00401A': 15, '00997A': 16,
        }
        def _etf_chip(etf_code: str, etf_name: str, suffix: str = "") -> str:
                raw_code = str(etf_code or "").strip()
                num = _etf_color_map.get(raw_code, 0)
                cls = f"etf-c{num}" if num else ""
                num_tag = f"<span class='etf-num'>{num}</span>" if num else ""
                esc_code = html.escape(raw_code)
                esc_name = html.escape(str(etf_name or ""))
                content = f"{num_tag}{esc_code} {esc_name}{suffix}"
                return f"<span class='tag {cls}'>{content}</span>"

        def _etf_tags_from_current(item: Dict) -> str:
                etfs = item.get("目前持有ETF", []) or []
                if not etfs:
                        return "-"
                tags = []
                for e in etfs:
                        code = str(e.get("ETF股票代號") or "")
                        name = str(e.get("ETF股票名稱") or "")
                        tags.append(_etf_chip(code, name))
                return "".join(tags)

        def _etf_tags_from_new(item: Dict) -> str:
                etfs = item.get("新增 ETF", []) or []
                if not etfs:
                        return "-"
                return "".join([_etf_chip(str(x), "") for x in etfs])

        def _etp_change_table(item: Dict) -> str:
            rows = item.get("ETF股數變動", []) or []
            if not rows:
                return "-"
            rows = sorted(rows, key=lambda r: abs(int(r.get("差異") or 0)), reverse=True)
            # 本次收盤價：取個股當日收盤價
            curr_price = item.get("當日收盤價")
            try:
                curr_price = float(curr_price) if curr_price not in (None, "") else None
            except Exception:
                curr_price = None
            # 前次收盤價：以 previous_date 收盤價查表
            prev_price = _lookup_price(prev_prices, str(item.get("股票代號") or "")) if prev_prices else None
            prev_per_k = round(prev_price * 1000, 2) if prev_price is not None else None
            curr_per_k = round(curr_price * 1000, 2) if curr_price is not None else None
            body = []
            for r in rows:
                prev_sh = int(r.get("前次股數") or 0)
                curr_sh = int(r.get("本次股數") or 0)
                diff_sh = int(r.get("差異") or 0)
                row_class = "etf-up-row" if diff_sh > 0 else ("etf-down-row" if diff_sh < 0 else "")
                prev_cost = f"{int(round(prev_price * prev_sh)):,}" if prev_price is not None else "-"
                curr_cost = f"{int(round(curr_price * curr_sh)):,}" if curr_price is not None else "-"
                prev_per_k_str = f"{prev_per_k:,.2f}" if prev_per_k is not None else "-"
                curr_per_k_str = f"{curr_per_k:,.2f}" if curr_per_k is not None else "-"
                body.append(
                    f"<tr class='{row_class}'>"
                    f"<td>{html.escape(str(r.get('ETF股票代號') or ''))}</td>"
                    f"<td>{html.escape(str(r.get('ETF股票名稱') or ''))}</td>"
                    f"<td class='num'>{_fmt_int(prev_sh)}</td>"
                    f"<td class='num'>{_fmt_int(curr_sh)}</td>"
                    f"<td class='num'>{_fmt_int(diff_sh)}</td>"
                    f"<td class='num'>{prev_cost}</td>"
                    f"<td class='num'>{curr_cost}</td>"
                    f"<td class='num'>{prev_per_k_str}</td>"
                    f"<td class='num'>{curr_per_k_str}</td>"
                    "</tr>"
                )
            return (
                "<details><summary>展開 ETP 股數變動</summary>"
                "<table class='subtbl'><thead><tr>"
                "<th>ETP代號</th><th>ETP名稱</th>"
                "<th>前次股數</th><th>本次股數</th><th>差異</th>"
                "<th>前次總成本</th><th>本次總成本</th>"
                "<th>前次每1000股單價</th><th>本次每1000股單價</th>"
                "</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table></details>"
            )

        def _fmt_price(v):
                if v in (None, ""):
                        return "-"
                try:
                        return f"{float(v):,.2f}"
                except Exception:
                        return str(v)

        def _fmt_money(v):
                if v in (None, ""):
                        return "-"
                try:
                        return f"{int(round(float(v))):,}"
                except Exception:
                        return str(v)

        def _build_all_stock_rows(items: List[Dict]) -> str:
            out = []
            for it in items:
                raw_code = str(it.get("股票代號") or "")
                code = html.escape(raw_code)
                name = html.escape(str(it.get("股票名稱") or ""))
                qty = _fmt_int(it.get("總股數") or 0)
                etf_count = _fmt_int(it.get("持有 ETF 數") or 0)
                delta = _fmt_int(it.get("總異動股數") or 0)
                etf_tags = []
                for e in it.get("ETF明細", []) or []:
                    etf_code = str(e.get("ETF股票代號") or "")
                    etf_name = str(e.get("ETF股票名稱") or "")
                    sh = _fmt_int(e.get("股數") or 0)
                    etf_tags.append(_etf_chip(etf_code, etf_name, f" · {sh}"))
                out.append(
                    "<tr class='all-stock-row'>"
                    f"<td>{code}</td><td>{name}</td><td class='num'>{qty}</td>"
                    f"<td class='num'>{etf_count}</td><td class='num'>{delta}</td>"
                    f"<td>{''.join(etf_tags) if etf_tags else '-'}</td>"
                    "</tr>"
                )
            return "".join(out)

        def _build_new_rows(items: List[Dict]) -> str:
                out = []
                for it in items:
                        raw_code = str(it.get("股票代號") or "")
                        code = html.escape(raw_code)
                        name = html.escape(str(it.get("股票名稱") or ""))
                        qty = _fmt_int(it.get("總股數") or 0)
                        price_str = _fmt_price(it.get("當日收盤價"))
                        value_str = _fmt_money(it.get("目前總投入金額"))
                        per_k_str = _fmt_price(it.get("每1000股成本均值"))
                        out.append(
                            f"<tr class='clickable' data-code=\"{html.escape(raw_code, quote=True)}\" title='點選檢視近十日資訊'>"
                                f"<td>{code}</td><td>{name}</td><td class='num'>{qty}</td>"
                                f"<td class='num'>{price_str}</td><td class='num'>{value_str}</td><td class='num'>{per_k_str}</td>"
                                f"<td>{_etf_tags_from_new(it)}</td>"
                                "</tr>"
                        )
                return "".join(out)

        def _build_changed_rows(items: List[Dict]) -> str:
                out = []
                for it in items:
                        raw_code = str(it.get("股票代號") or "")
                        code = html.escape(raw_code)
                        name = html.escape(str(it.get("股票名稱") or ""))
                        prev_qty = _fmt_int(it.get("前次總股數") or 0)
                        curr_qty = _fmt_int(it.get("本次總股數") or 0)
                        delta = _fmt_int(it.get("總股數差異") or 0)
                        prev_qty_n = int(it.get("前次總股數") or 0)
                        delta_n = int(it.get("總股數差異") or 0)
                        ratio_str = "-"
                        if prev_qty_n > 0:
                            ratio = (delta_n / prev_qty_n) * 100
                            ratio_str = f"{ratio:+.2f}%"
                        price_str = _fmt_price(it.get("當日收盤價"))
                        value_str = _fmt_money(it.get("目前總投入金額"))
                        per_k_str = _fmt_price(it.get("每1000股成本均值"))
                        out.append(
                            f"<tr class='clickable' data-code=\"{html.escape(raw_code, quote=True)}\" title='點選檢視近十日資訊'>"
                            f"<td>{code}</td><td>{name}</td><td class='num'>{prev_qty}</td><td class='num'>{curr_qty}</td><td class='num'>{delta}</td><td class='num'>{ratio_str}</td>"
                                f"<td class='num'>{price_str}</td><td class='num'>{value_str}</td><td class='num'>{per_k_str}</td>"
                                f"<td>{_etf_tags_from_current(it)}</td><td>{_etp_change_table(it)}</td>"
                                "</tr>"
                        )
                return "".join(out)

        # 建立近 10 日歷史（包含所有出現於本次報表的個股）
        _all_items = list(new_stocks) + list(changed)
        _codes = []
        _name_map: Dict[str, str] = {}
        _seen = set()
        for _it in _all_items:
                _c = str(_it.get("股票代號") or "").strip()
                if _c and _c not in _seen:
                        _seen.add(_c)
                        _codes.append(_c)
                        _name_map[_c] = str(_it.get("股票名稱") or "")
        try:
                _history = build_stock_5d_history(stock_shares_dir, _codes, price_date, days=10)
        except Exception as _e:
                print(f"  建立近十日歷史失敗：{_e}")
                _history = {}
        _history_json = json.dumps(_history, ensure_ascii=False)
        _name_json = json.dumps(_name_map, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html lang='zh-Hant'>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>個股異動分類報表 {today}</title>
    <style>
        :root {{ --bg:#f6f8fb; --card:#ffffff; --text:#16202a; --muted:#5f6b76; --line:#d7dde5; --up:#0a7a42; --down:#b42318; --new:#155eef; }}
        body {{ margin:0; padding-top:70px; background:var(--bg); color:var(--text); font-family:"Microsoft JhengHei",sans-serif; }}
        .top-nav {{ position:fixed; top:0; left:0; right:0; z-index:60; background:rgba(246,248,251,.96); border-bottom:1px solid var(--line); backdrop-filter:blur(8px); }}
        .top-nav-inner {{ width:100%; max-width:none; padding:10px 16px; box-sizing:border-box; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
        .top-nav-label {{ color:var(--muted); font-size:13px; white-space:nowrap; }}
        .top-nav a {{ text-decoration:none; }}
        .wrap {{ width:100%; max-width:none; margin:0 auto 24px; padding:0 16px; box-sizing:border-box; }}
        .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }}
        .card-head {{ display:flex; gap:12px; align-items:flex-start; justify-content:space-between; margin-bottom:12px; }}
        .card-head h2 {{ margin:0; }}
        .head-actions {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
        .back-top {{ display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border-radius:999px; border:1px solid var(--line); background:#fff; color:var(--text); text-decoration:none; font-size:13px; white-space:nowrap; }}
        .back-top:hover {{ background:#eef4ff; border-color:#bfd4ff; }}
        .toggle-sec {{ display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border-radius:999px; border:1px solid var(--line); background:#fff; color:var(--text); font-size:13px; cursor:pointer; }}
        .toggle-sec:hover {{ background:#f2f5fa; }}
        .card.collapsed .card-body {{ display:none; }}
        h1 {{ margin:0 0 8px; font-size:28px; }}
        h2 {{ margin:0 0 12px; font-size:22px; }}
        .meta {{ color:var(--muted); font-size:14px; }}
        .kpis {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }}
        .kpi {{ padding:8px 12px; border-radius:999px; font-size:14px; border:1px solid var(--line); background:#fff; }}
        .new {{ color:var(--new); border-color:#bfd4ff; background:#eef4ff; }}
        .up {{ color:var(--up); border-color:#b7e2cb; background:#edf9f2; }}
        .down {{ color:var(--down); border-color:#f2c5c2; background:#fff1f0; }}
        .all {{ color:#5a3e1b; border-color:#ead9b6; background:#fff8e8; }}
        table {{ width:100%; border-collapse:collapse; font-size:14px; }}
        th, td {{ border-bottom:1px solid var(--line); padding:8px; vertical-align:top; }}
        th {{ text-align:left; background:#f9fbfd; position:sticky; top:0; z-index:1; }}
        .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
        .tag {{ display:inline-block; margin:2px 4px 2px 0; padding:2px 8px; border-radius:999px; background:#eef2f7; border:1px solid #dde4ec; font-size:12px; white-space:nowrap; }}
        details {{ margin:0; }}
        summary {{ cursor:pointer; color:#1a5fb4; }}
        .subtbl th, .subtbl td {{ font-size:12px; padding:6px; }}
        .tblbox {{ overflow-x:auto; }}
        .card[id] {{ scroll-margin-top:92px; }}
        a.kpi {{ text-decoration:none; cursor:pointer; }}
        a.kpi:hover {{ filter:brightness(0.97); }}
        .jump-link {{ display:inline-flex; align-items:center; padding:7px 12px; border-radius:999px; border:1px solid var(--line); background:#fff; color:var(--text); font-size:13px; }}
        .jump-link:hover {{ background:#eef4ff; border-color:#bfd4ff; }}
        tr.clickable {{ cursor:pointer; }}
        tr.clickable:hover td {{ background:#f0f6ff; }}
        .modal-mask {{ position:fixed; inset:0; background:rgba(20,28,40,.55); display:none; align-items:center; justify-content:center; z-index:50; }}
        .modal-mask.show {{ display:flex; }}
        .modal {{ background:#fff; border-radius:14px; box-shadow:0 24px 60px rgba(0,0,0,.25); width:80vw; max-height:86vh; overflow:auto; padding:20px 22px; }}
        .modal h3 {{ margin:0 0 8px; font-size:20px; }}
        .modal .meta {{ color:var(--muted); font-size:13px; margin-bottom:12px; }}
        .modal .close-btn {{ float:right; background:transparent; border:0; font-size:22px; cursor:pointer; color:#5f6b76; }}
        .modal table {{ font-size:13px; }}
        .modal th {{ position:static; }}
        .empty {{ color:var(--muted); padding:18px 0; text-align:center; }}
        .searchbar {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:0 0 12px; }}
        .searchbar input {{ flex:1 1 320px; min-width:220px; padding:10px 12px; border:1px solid var(--line); border-radius:10px; font-size:14px; background:#fff; }}
        .search-meta {{ color:var(--muted); font-size:13px; }}
        .etf-up-row td {{ background:#eaf5ff; }}
        .etf-down-row td {{ background:#fff0f4; }}
        .etf-info-cell {{ min-width:260px; }}
        .etf-chip {{ display:inline-block; margin:2px 6px 2px 0; padding:3px 8px; border-radius:999px; border:1px solid #dde4ec; background:#eef2f7; font-size:12px; white-space:nowrap; }}
        .etf-chip.up {{ background:#eaf5ff; border-color:#bfdfff; color:#0b5ea8; }}
        .etf-chip.down {{ background:#fff0f4; border-color:#f7c7d5; color:#9d2148; }}
        .etf-chip.neutral {{ background:#f2f5fa; border-color:#dde4ec; color:#4f5b66; }}
        .etf-num {{ display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; font-size:11px; font-weight:600; margin-right:4px; flex-shrink:0; }}
        .etf-c1 {{ background:#e3f2fd; border-color:#90caf9; color:#1565c0; }} .etf-c1 .etf-num {{ background:#1565c0; color:#fff; }}
        .etf-c2 {{ background:#fce4ec; border-color:#f48fb1; color:#c2185b; }} .etf-c2 .etf-num {{ background:#c2185b; color:#fff; }}
        .etf-c3 {{ background:#e8f5e9; border-color:#a5d6a7; color:#2e7d32; }} .etf-c3 .etf-num {{ background:#2e7d32; color:#fff; }}
        .etf-c4 {{ background:#fff3e0; border-color:#ffcc80; color:#e65100; }} .etf-c4 .etf-num {{ background:#e65100; color:#fff; }}
        .etf-c5 {{ background:#f3e5f5; border-color:#ce93d8; color:#7b1fa2; }} .etf-c5 .etf-num {{ background:#7b1fa2; color:#fff; }}
        .etf-c6 {{ background:#e0f7fa; border-color:#80deea; color:#00838f; }} .etf-c6 .etf-num {{ background:#00838f; color:#fff; }}
        .etf-c7 {{ background:#fff8e1; border-color:#ffe082; color:#f9a825; }} .etf-c7 .etf-num {{ background:#f9a825; color:#fff; }}
        .etf-c8 {{ background:#efebe9; border-color:#bcaaa4; color:#5d4037; }} .etf-c8 .etf-num {{ background:#5d4037; color:#fff; }}
        .etf-c9 {{ background:#e8eaf6; border-color:#9fa8da; color:#303f9f; }} .etf-c9 .etf-num {{ background:#303f9f; color:#fff; }}
        .etf-c10 {{ background:#fbe9e7; border-color:#ffab91; color:#d84315; }} .etf-c10 .etf-num {{ background:#d84315; color:#fff; }}
        .etf-c11 {{ background:#e0f2f1; border-color:#80cbc4; color:#00695c; }} .etf-c11 .etf-num {{ background:#00695c; color:#fff; }}
        .etf-c12 {{ background:#fafafa; border-color:#bdbdbd; color:#424242; }} .etf-c12 .etf-num {{ background:#424242; color:#fff; }}
        .etf-c13 {{ background:#ede7f6; border-color:#b39ddb; color:#512da8; }} .etf-c13 .etf-num {{ background:#512da8; color:#fff; }}
        .etf-c14 {{ background:#ffebee; border-color:#ef9a9a; color:#c62828; }} .etf-c14 .etf-num {{ background:#c62828; color:#fff; }}
        .etf-c15 {{ background:#e1f5fe; border-color:#81d4fa; color:#0277bd; }} .etf-c15 .etf-num {{ background:#0277bd; color:#fff; }}
        .etf-c16 {{ background:#f1f8e9; border-color:#aed581; color:#558b2f; }} .etf-c16 .etf-num {{ background:#558b2f; color:#fff; }}
    </style>
</head>
<body>
    <div class='top-nav'>
        <div class='top-nav-inner'>
            <div class='top-nav-label'>區塊導覽</div>
            <a class='jump-link' href='#sec-all'>全部個股</a>
            <a class='jump-link' href='#sec-new'>新增分類</a>
            <a class='jump-link' href='#sec-inc'>持股增加</a>
            <a class='jump-link' href='#sec-dec'>持股減少</a>
            <a class='jump-link' href='#top'>回最上方</a>
        </div>
    </div>
    <div class='wrap' id='top'>
        <div class='card'>
            <h1>個股異動分類統整</h1>
            <div class='meta'>資料日：{html.escape(str(diff_summary.get('date') or today))}，比較日：{html.escape(str(diff_summary.get('previous_date') or '-'))}</div>
            <div class='meta'>缺少股數、不納入股數統計的 ETF：{html.escape(', '.join(diff_summary.get('missing_share_etfs', [])) or '無')}</div>
            <div class='kpis'>
                <a class='kpi new' href='#sec-new'>新增分類資訊：{len(new_stocks)} 檔</a>
                <a class='kpi up' href='#sec-inc'>原本持有而新增股數：{len(existed_increase)} 檔</a>
                <a class='kpi down' href='#sec-dec'>原本持有減少股數：{len(existed_decrease)} 檔</a>
                <a class='kpi all' href='#sec-all'>全部個股資訊：{len(all_stock_rows)} 檔</a>
            </div>
        </div>

        <div class='card' id='sec-all'>
            <div class='card-head'>
                <h2>全部個股資訊</h2>
                <div class='head-actions'>
                    <button class='toggle-sec' type='button' onclick="toggleCard('sec-all', this)">收合</button>
                    <a class='back-top' href='#top'>回最上面</a>
                </div>
            </div>
            <div class='card-body'>
            <div class='searchbar'>
                <input id='allStockSearch' type='search' placeholder='搜尋股票代號、股票名稱、ETF 代號/名稱...' oninput='filterAllStocks()'>
                <div class='search-meta' id='allStockSearchMeta'>顯示 {len(all_stock_rows)} / {len(all_stock_rows)} 檔</div>
            </div>
            <div class='tblbox'>
                <table>
                    <thead><tr><th>股票代號</th><th>股票名稱</th><th class='num'>總股數</th><th class='num'>持有 ETF 數</th><th class='num'>總異動股數</th><th>ETF明細</th></tr></thead>
                    <tbody id='allStockTbody'>{_build_all_stock_rows(all_stock_rows)}</tbody>
                </table>
            </div>
            </div>
        </div>

        <div class='card' id='sec-new'>
            <div class='card-head'>
                <h2>新增分類資訊（由變動大至小）</h2>
                <div class='head-actions'>
                    <button class='toggle-sec' type='button' onclick="toggleCard('sec-new', this)">收合</button>
                    <a class='back-top' href='#top'>回最上面</a>
                </div>
            </div>
            <div class='card-body'>
            <div class='tblbox'>
                <table>
                    <thead><tr><th>股票代號</th><th>股票名稱</th><th class='num'>新增股數</th>
                        <th class='num'>當日收盤價</th><th class='num'>目前總投入金額</th><th class='num'>每1000股成本均值</th>
                        <th>ETP資訊</th></tr></thead>
                    <tbody>{_build_new_rows(new_stocks)}</tbody>
                </table>
            </div>
            </div>
        </div>

        <div class='card' id='sec-inc'>
            <div class='card-head'>
                <h2>原本持有而新增股數資訊（由變動大至小）</h2>
                <div class='head-actions'>
                    <button class='toggle-sec' type='button' onclick="toggleCard('sec-inc', this)">收合</button>
                    <a class='back-top' href='#top'>回最上面</a>
                </div>
            </div>
            <div class='card-body'>
            <div class='tblbox'>
                <table>
                    <thead><tr><th>股票代號</th><th>股票名稱</th><th class='num'>前次總股數</th><th class='num'>本次總股數</th><th class='num'>差異</th>
                        <th class='num'>變動/前次(%)</th>
                        <th class='num'>當日收盤價</th><th class='num'>目前總投入金額</th><th class='num'>每1000股成本均值</th>
                        <th>目前持有 ETP</th><th>各 ETP 詳細異動</th></tr></thead>
                    <tbody>{_build_changed_rows(existed_increase)}</tbody>
                </table>
            </div>
            </div>
        </div>

        <div class='card' id='sec-dec'>
            <div class='card-head'>
                <h2>原本持有減少股數資訊（由變動大至小）</h2>
                <div class='head-actions'>
                    <button class='toggle-sec' type='button' onclick="toggleCard('sec-dec', this)">收合</button>
                    <a class='back-top' href='#top'>回最上面</a>
                </div>
            </div>
            <div class='card-body'>
            <div class='tblbox'>
                <table>
                    <thead><tr><th>股票代號</th><th>股票名稱</th><th class='num'>前次總股數</th><th class='num'>本次總股數</th><th class='num'>差異</th>
                        <th class='num'>變動/前次(%)</th>
                        <th class='num'>當日收盤價</th><th class='num'>目前總投入金額</th><th class='num'>每1000股成本均值</th>
                        <th>目前持有 ETP</th><th>各 ETP 詳細異動</th></tr></thead>
                    <tbody>{_build_changed_rows(existed_decrease)}</tbody>
                </table>
            </div>
            </div>
        </div>
    </div>

    <div id='detailMask' class='modal-mask' role='dialog' aria-modal='true'>
        <div class='modal'>
            <button class='close-btn' type='button' onclick='closeStockModal()' aria-label='關閉'>×</button>
            <h3 id='modalTitle'>個股近十日資訊</h3>
            <div class='meta' id='modalMeta'></div>
            <div id='modalBody'></div>
        </div>
    </div>

    <script>
        window.__STOCK_HISTORY = {_history_json};
        window.__STOCK_NAMES = {_name_json};

        function fmtInt(v) {{
            if (v === null || v === undefined || v === '') return '-';
            try {{ return Number(v).toLocaleString('en-US'); }} catch (e) {{ return String(v); }}
        }}
        function fmtPrice(v) {{
            if (v === null || v === undefined || v === '') return '-';
            const n = Number(v);
            if (!isFinite(n)) return String(v);
            return n.toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }}
        function filterAllStocks() {{
            const input = document.getElementById('allStockSearch');
            const meta = document.getElementById('allStockSearchMeta');
            const tbody = document.getElementById('allStockTbody');
            if (!input || !meta || !tbody) return;
            const q = (input.value || '').trim().toLowerCase();
            const rows = Array.from(tbody.querySelectorAll('tr.all-stock-row'));
            let visible = 0;
            rows.forEach(function(row) {{
                const text = (row.textContent || '').toLowerCase();
                const show = !q || text.indexOf(q) !== -1;
                row.style.display = show ? '' : 'none';
                if (show) visible += 1;
            }});
            meta.textContent = '顯示 ' + visible + ' / ' + rows.length + ' 檔';
        }}
        function toggleCard(cardId, btn) {{
            const card = document.getElementById(cardId);
            if (!card) return;
            const collapsed = card.classList.toggle('collapsed');
            if (btn) btn.textContent = collapsed ? '展開' : '收合';
        }}
        const ETF_COLOR_MAP = {{
            '00980A': 1, '00982A': 2, '00981A': 3, '00984A': 4,
            '00985A': 5, '00986A': 6, '00991A': 7, '00987A': 8,
            '00992A': 9, '00994A': 10, '00995A': 11, '00993A': 12,
            '00996A': 13, '00400A': 14, '00401A': 15, '00997A': 16,
        }};
        function etfChipHtml(code, name, suffix, extraCls) {{
            const num = ETF_COLOR_MAP[code] || 0;
            const colorCls = num ? ('etf-c' + num) : '';
            const numTag = num ? ("<span class='etf-num'>" + num + "</span>") : '';
            const allCls = ['etf-chip', colorCls, extraCls || ''].filter(Boolean).join(' ');
            return "<span class='" + allCls + "'>" + numTag + code + " " + name + (suffix || '') + "</span>";
        }}
        function renderEtfChangeChips(changes) {{
            if (!changes || !changes.length) return '-';
            return changes.map(function(c) {{
                const code = c.code || '';
                const name = c.name || '';
                const delta = Number(c.delta || 0);
                const cls = delta > 0 ? 'up' : 'down';
                const deltaText = delta > 0 ? (' +' + fmtInt(delta)) : (' ' + fmtInt(delta));
                return etfChipHtml(code, name, deltaText, cls);
            }}).join('');
        }}
        function renderEtfSnapshotChips(snapshot) {{
            if (!snapshot || !snapshot.length) return '-';
            return snapshot.map(function(c) {{
                const code = c.code || '';
                const name = c.name || '';
                const shares = fmtInt(c.shares || 0);
                return etfChipHtml(code, name, ' ' + shares, 'neutral');
            }}).join('');
        }}
        function openStockModal(code) {{
            const hist = (window.__STOCK_HISTORY || {{}})[code] || [];
            const name = (window.__STOCK_NAMES || {{}})[code] || '';
            document.getElementById('modalTitle').textContent = code + ' ' + name + '　近十日資訊';
            document.getElementById('modalMeta').textContent = hist.length ? ('共 ' + hist.length + ' 日（依現有 summary 檔提供）') : '';
            const body = document.getElementById('modalBody');
            if (!hist.length) {{
                body.innerHTML = "<div class='empty'>無近十日資料。</div>";
            }} else {{
                // hist 為由新到舊；先轉為由舊到新計算累計成本與每1000股平均成本
                // 規則：每日新增的股數視為以該日收盤價買進；股數減少時按比例沖銷成本。
                const ordered = hist.slice().reverse();
                let cumShares = 0;
                let cumCost = 0;
                let costKnown = true;
                let prevEtfMap = null;
                const calc = ordered.map(function(h) {{
                    const shares = (h['總股數'] === null || h['總股數'] === undefined) ? 0 : Number(h['總股數']);
                    const price = (h['收盤價'] === null || h['收盤價'] === undefined) ? null : Number(h['收盤價']);
                    const delta = shares - cumShares;
                    const etfRows = Array.isArray(h['ETF明細']) ? h['ETF明細'] : [];
                    const currEtfMap = {{}};
                    etfRows.forEach(function(e) {{
                        const etfCode = String(e['ETF股票代號'] || '').trim();
                        if (!etfCode) return;
                        currEtfMap[etfCode] = {{
                            code: etfCode,
                            name: String(e['ETF股票名稱'] || ''),
                            shares: Number(e['股數'] || 0)
                        }};
                    }});
                    let etfChanges = [];
                    if (prevEtfMap !== null) {{
                        const keys = new Set(Object.keys(currEtfMap).concat(Object.keys(prevEtfMap)));
                        keys.forEach(function(k) {{
                            const cur = currEtfMap[k] ? Number(currEtfMap[k].shares || 0) : 0;
                            const prv = prevEtfMap[k] ? Number(prevEtfMap[k].shares || 0) : 0;
                            const d = cur - prv;
                            if (d !== 0) {{
                                etfChanges.push({{
                                    code: k,
                                    name: (currEtfMap[k] && currEtfMap[k].name) || (prevEtfMap[k] && prevEtfMap[k].name) || '',
                                    delta: d
                                }});
                            }}
                        }});
                        etfChanges.sort(function(a, b) {{ return Math.abs(b.delta) - Math.abs(a.delta); }});
                    }}
                    const etfSnapshot = Object.keys(currEtfMap).map(function(k) {{ return currEtfMap[k]; }});
                    etfSnapshot.sort(function(a, b) {{ return Number(b.shares || 0) - Number(a.shares || 0); }});
                    if (cumShares === 0) {{
                        costKnown = shares === 0 || price !== null;
                        if (price !== null && shares > 0) cumCost = price * shares;
                        cumShares = shares;
                    }} else if (delta > 0) {{
                        if (price === null) costKnown = false;
                        if (price !== null) cumCost += price * delta;
                        cumShares = shares;
                    }} else if (delta < 0) {{
                        if (price === null && shares > 0) costKnown = false;
                        // 股數減少：以當日收盤價計算賣出金額，從累計成本扣除
                        if (price !== null) cumCost -= price * (-delta);
                        cumShares = shares;
                    }}
                    const avgPerK = (costKnown && cumShares > 0 && cumCost > 0) ? (cumCost / cumShares * 1000) : null;
                    prevEtfMap = currEtfMap;
                    return {{
                        date: h.date,
                        shares: shares,
                        delta: delta,
                        close: h['收盤價'],
                        invest: h['目前總投入金額'],
                        cumCost: costKnown && cumShares > 0 ? cumCost : null,
                        avgPerK: avgPerK,
                        etfChanges: etfChanges,
                        etfSnapshot: etfSnapshot,
                    }};
                }});
                // 顯示時依新到舊
                const reversed = calc.slice().reverse();
                const rows = reversed.map(function(c, i) {{
                    const isOldest = (i === reversed.length - 1);
                    const deltaText = isOldest ? '-' : ((c.delta > 0 ? '+' : '') + fmtInt(c.delta));
                    return "<tr>"
                        + "<td>" + c.date + "</td>"
                        + "<td class='num'>" + fmtInt(c.shares) + "</td>"
                        + "<td class='num'>" + deltaText + "</td>"
                        + "<td class='num'>" + fmtPrice(c.close) + "</td>"
                        + "<td class='num'>" + fmtInt(c.invest) + "</td>"
                        + "<td class='num'>" + fmtInt(c.cumCost) + "</td>"
                        + "<td class='num'>" + fmtPrice(c.avgPerK) + "</td>"
                        + "<td class='etf-info-cell'>" + renderEtfChangeChips(c.etfChanges) + "</td>"
                        + "<td class='etf-info-cell'>" + renderEtfSnapshotChips(c.etfSnapshot) + "</td>"
                        + "</tr>";
                }}).join('');
                body.innerHTML = "<table><thead><tr>"
                    + "<th>日期</th>"
                    + "<th class='num'>總股數</th>"
                    + "<th class='num'>日變化</th>"
                    + "<th class='num'>收盤價</th>"
                    + "<th class='num'>當日市值</th>"
                    + "<th class='num'>累計投入成本</th>"
                    + "<th class='num'>每1000股平均成本</th>"
                    + "<th>ETF異動（相較前一日）</th>"
                    + "<th>目前持有ETF</th>"
                    + "</tr></thead><tbody>" + rows + "</tbody></table>";
            }}
            document.getElementById('detailMask').classList.add('show');
        }}
        function closeStockModal() {{
            document.getElementById('detailMask').classList.remove('show');
        }}
        document.addEventListener('click', function(e) {{
            const tr = e.target.closest('tr.clickable');
            if (!tr) return;
            // 避免點到 details/summary/連結/按鈕 時觸發 modal
            if (e.target.closest('details, summary, a, button')) return;
            const code = tr.getAttribute('data-code');
            if (code) openStockModal(code);
        }});
        document.getElementById('detailMask').addEventListener('click', function(e) {{
            if (e.target === this) closeStockModal();
        }});
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeStockModal();
        }});
        filterAllStocks();
    </script>
</body>
</html>
"""

        dated_path = os.path.join(report_dir, f"stock_changes_report_{today}.html")
        latest_path = os.path.join(report_dir, "stock_changes_report_latest.html")
        with open(dated_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        with open(latest_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        return dated_path


def scrape_ezmoney(soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """舊版 ezmoney table"""
    stocks = []
    stock_table = soup.find("table", {"id": "stockTable"})
    
    if not stock_table:
        tables = soup.find_all("table")
        for table in tables:
            table_text = table.get_text(" ", strip=True)
            if (
                "股票代號" in table_text
                and "股票名稱" in table_text
                and ("持股權重" in table_text or "持股比例" in table_text)
            ):
                stock_table = table
                break
    
    if stock_table:
        for row in stock_table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 4:
                stock = {
                    "股票代號": cols[0].get_text(strip=True),
                    "股票名稱": cols[1].get_text(strip=True),
                    "股數": cols[2].get_text(strip=True),
                    "持股比例": cols[3].get_text(strip=True),
                    "ETF股票代號": etf_stock_code
                }
                if stock["股票代號"]:
                    stocks.append(stock)
    
    return stocks


def scrape_nomurafunds(soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """野村基金站：Angular SPA，表格使用 .col-code/.col-name/.col-quantity/.col-weight"""
    stocks = []

    # 真實 class selector（Angular SPA 渲染後）
    # 注意：#Shareholding 範圍可能僅含部份 row，先用 .table-list 抓全部
    rows = soup.select(".table-list tbody tr")
    if not rows:
        rows = soup.select("#Shareholding .table-list tbody tr")

    for row in rows:
        # 跳過「查看更多」按鈕所在 tr
        row_cls = " ".join(row.get("class") or [])
        if "red" in row_cls or row.select_one(".showMore"):
            continue
        code_el = row.select_one(".col-code")
        name_el = row.select_one(".col-name")
        qty_el = row.select_one(".col-quantity")
        weight_el = row.select_one(".col-weight")
        if not (code_el and name_el):
            continue
        code = code_el.get_text(strip=True)
        name = name_el.get_text(strip=True)
        if not code or not name:
            continue
        weight = weight_el.get_text(strip=True) if weight_el else ""
        # 後備：若 col-weight 抹不到，扫 row 內含 % 的 cell
        if not weight:
            for cell in row.find_all(["td", "div", "span"]):
                txt = cell.get_text(strip=True)
                if txt and txt.endswith("%"):
                    weight = txt
                    break
        stocks.append(
            {
                "股票代號": code,
                "股票名稱": name,
                "股數": qty_el.get_text(strip=True) if qty_el else "",
                "持股比例": weight,
                "ETF股票代號": etf_stock_code,
            }
        )

    if stocks:
        return stocks

    # 後備：通用 table 掃描
    tables = soup.find_all("table")
    for table in tables:
        table_text = table.get_text(" ", strip=True)
        if "代號" in table_text or "股票代號" in table_text:
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    code = cols[0].get_text(strip=True)
                    name = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                    if code and name:
                        stock = {
                            "股票代號": code,
                            "股票名稱": name,
                        }
                        if len(cols) > 2:
                            stock["股數"] = cols[2].get_text(strip=True)
                        if len(cols) > 3:
                            stock["持股比例"] = cols[3].get_text(strip=True)
                        stock["ETF股票代號"] = etf_stock_code
                        stocks.append(stock)
            if stocks:
                break

    return stocks


def scrape_megafunds(soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """兆豐基金站：div.fund-info 結構"""
    stocks = []
    rows = soup.select("div.fundInfo-content div.fund-info")

    for row in rows:
        cols = row.select("div.fund-content")
        if len(cols) >= 4:
            code = cols[0].get_text(strip=True)
            name = cols[1].get_text(strip=True)
            shares = cols[2].get_text(strip=True)
            weight = cols[3].get_text(strip=True)
            if code and name:
                stocks.append(
                    {
                        "股票代號": code,
                        "股票名稱": name,
                        "股數": shares,
                        "持股比例": weight,
                        "ETF股票代號": etf_stock_code,
                    }
                )

    return stocks


def scrape_cathaysite_api(etf_stock_code: str, etf_url: str) -> List[Dict[str, str]]:
    """國泰投信：直接打 cwapi.cathaysite.com.tw/api/ETF/GetIndexStockWeights。"""
    # URL 路徑形如 /ETF/detail/EEA?tab=etf3，FundCode=EA（去掉前綴 E）
    m = re.search(r"/ETF/detail/([A-Z0-9]+)", etf_url)
    fund_code = m.group(1) if m else ""
    if fund_code.startswith("E") and len(fund_code) > 1:
        fund_code = fund_code[1:]
    if not fund_code:
        return []
    api = f"https://cwapi.cathaysite.com.tw/api/ETF/GetIndexStockWeights?FundCode={fund_code}"
    try:
        data = _http_get_json(api)
    except Exception as e:
        print(f"  cathay API 失敗: {e}")
        return []
    items = (data.get("result") or {}).get("stockWeights") or []
    return [
        {
            "股票代號": it.get("stockCode", "").strip(),
            "股票名稱": (it.get("stockName") or "").strip(),
            # 此權重 API 通常不提供數量；保留未知值，不從比例推算股數。
            "股數": _parse_shares(it.get("shares")),
            "持股比例": f"{it.get('weights', '')}%" if it.get("weights") else "",
            "ETF股票代號": etf_stock_code,
        }
        for it in items
        if it.get("stockCode")
    ]


def scrape_jpmorgan_api(etf_stock_code: str, etf_url: str) -> List[Dict[str, str]]:
    """JPMorgan ETF：直接打 FundsMarketingHandler/product-data。"""
    # URL 中含 tw00000401a1，cusip 為 TW00000401A1
    m = re.search(r"(tw\d{8}[a-z]\d)", etf_url, re.IGNORECASE)
    cusip = m.group(1).upper() if m else f"TW0000{etf_stock_code}1"
    api = (
        "https://am.jpmorgan.com/FundsMarketingHandler/product-data"
        f"?cusip={cusip}&country=tw&role=twetf&language=zh&userLoggedIn=false&version=9.7.1_1776467615"
    )
    try:
        data = _http_get_json(api)
    except Exception as e:
        print(f"  jpmorgan API 失敗: {e}")
        return []
    fund = (data.get("fundData") or {})
    holdings = (((fund.get("holdings") or {}).get("pcfEquityHoldings") or {}).get("data")) or []
    out = []
    for it in holdings:
        ticker = (it.get("securityTicker") or "").strip()
        if not ticker:
            continue
        out.append(
            {
                "股票代號": ticker,
                "股票名稱": (it.get("securityDescription") or "").strip(),
                "股數": f"{it.get('shares'):,}" if isinstance(it.get("shares"), (int, float)) else str(it.get("shares") or ""),
                "持股比例": f"{it.get('marketValuePercent')}%" if it.get("marketValuePercent") is not None else "",
                "ETF股票代號": etf_stock_code,
            }
        )
    return out


def scrape_ctbc_api(driver, etf_stock_code: str) -> List[Dict[str, str]]:
    """中信投信：從 performance log 攔到 ETFHoldingWeight 的 POST URL+body，重發取資料。"""
    print("  [ctbc] 開始攔截 XHR...", flush=True)
    api_url = None
    post_data = ""
    deadline = time.time() + 40
    while time.time() < deadline and api_url is None:
        try:
            logs = driver.get_log("performance")
        except Exception as e:
            print(f"  [ctbc] get_log 例外: {e}", flush=True)
            logs = []
        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
            except Exception:
                continue
            if msg.get("method") != "Network.requestWillBeSent":
                continue
            req = (msg.get("params") or {}).get("request") or {}
            url = req.get("url", "")
            if "ETFHoldingWeight" in url and req.get("method") == "POST":
                api_url = url
                post_data = req.get("postData") or ""
                break
        if api_url:
            break
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(1.5)
    if not api_url:
        print("  [ctbc] 未攔到 ETFHoldingWeight POST", flush=True)
        return []
    print(f"  [ctbc] 攔到 URL，postData={post_data[:120]}", flush=True)

    # 同源 fetch（在頁面 context 重發），避開 server 對 Origin/cookies 的限制
    script = (
        "var cb = arguments[arguments.length - 1];"
        "fetch(arguments[0], {"
        "  method: 'POST',"
        "  credentials: 'include',"
        "  headers: {'Content-Type': 'application/json; charset=UTF-8', 'Accept': 'application/json, text/plain, */*'},"
        "  body: arguments[1]"
        "}).then(r => r.text()).then(t => cb(t)).catch(e => cb('ERR:' + e));"
    )
    try:
        driver.set_script_timeout(20)
        text = driver.execute_async_script(script, api_url, post_data)
    except Exception as e:
        print(f"  ctbc fetch 失敗: {e}", flush=True)
        return []
    if not text or str(text).startswith("ERR:"):
        print(f"  ctbc fetch 回傳: {str(text)[:160]}", flush=True)
        return []
    try:
        with open(os.path.join("debug", "debug_ctbc_response.json"), "w", encoding="utf-8") as _f:
            _f.write(text)
    except Exception:
        pass
    print(f"  [ctbc] response 前 300 字: {text[:300]}", flush=True)
    try:
        data = json.loads(text)
    except Exception as e:
        print(f"  ctbc JSON 解析失敗: {e}", flush=True)
        return []
    if isinstance(data, dict) and data.get("ResultCode") not in (0, "0", None):
        print(f"  ctbc 回傳異常: {data.get('ResultMsg')}", flush=True)
        return []
    # 中信結構：Data.FundAssetsDetail 為分類 list，挑 Code=='STOCK' 取其 Data
    items = []
    if isinstance(data, dict):
        detail = ((data.get("Data") or {}).get("FundAssetsDetail")) or []
        if isinstance(detail, list):
            for grp in detail:
                if isinstance(grp, dict) and grp.get("Code") == "STOCK":
                    d = grp.get("Data")
                    if isinstance(d, list):
                        items = d
                        break
    print(f"  [ctbc] items 數量: {len(items)}", flush=True)
    if items and isinstance(items[0], dict):
        print(f"  [ctbc] 第一筆欄位: {list(items[0].keys())}", flush=True)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = (it.get("code_") or it.get("StockCode") or it.get("stockCode") or it.get("code") or it.get("Symbol") or "").strip()
        name = (it.get("name_") or it.get("StockName") or it.get("stockName") or it.get("name") or it.get("Name") or "").strip()
        weight = it.get("weights_") or it.get("Weight") or it.get("weight") or it.get("HoldingWeight") or it.get("Percent") or ""
        shares = it.get("qty_") or it.get("Shares") or it.get("shares") or it.get("Quantity") or ""
        if not code:
            continue
        weight_str = str(weight)
        if weight_str and "%" not in weight_str:
            weight_str = f"{weight_str}%"
        out.append(
            {
                "股票代號": code,
                "股票名稱": name,
                "股數": str(shares) if shares != "" else "",
                "持股比例": weight_str,
                "ETF股票代號": etf_stock_code,
            }
        )
    return out


_STOCK_CODE_RE = re.compile(
    r"^("
    r"\d{4,5}[A-Z]?"           # 台股 4~5 碼，可帶尾英文（如 00986A、2330）
    r"|[A-Z]{1,5}"             # 美股代號（如 AVGO、MSFT）
    r")"
    r"(\s+(TT|US|HK|JP|KS|SS|SZ|TW))?$"  # 可選市場尾碼
)


def _looks_like_stock_code(text: str) -> bool:
    if not text:
        return False
    text = text.strip()
    return bool(_STOCK_CODE_RE.match(text))


def _detect_table_columns(headers: List[str]) -> Dict[str, int]:
    """从表頭文字列判别欄位索引。"""
    mapping: Dict[str, int] = {}
    for idx, h in enumerate(headers):
        h = h.strip()
        if not h:
            continue
        if "代號" in h and "code" not in mapping:
            mapping["code"] = idx
        elif "名稱" in h and "name" not in mapping:
            mapping["name"] = idx
        elif ("股數" in h or "持股數" in h or "數量" in h) and "shares" not in mapping:
            mapping["shares"] = idx
        elif ("比例" in h or "比重" in h or "權重" in h or "百分比" in h) and "weight" not in mapping:
            mapping["weight"] = idx
    return mapping


def scrape_generic_table(soup, etf_stock_code: str) -> List[Dict[str, str]]:
    """通用表格解析器：先試 <table>，再試 div-based 偽表格（SPA 常用）。以表頭定位欄位。"""
    stocks = []
    tables = soup.find_all("table")

    for table in tables:
        table_text = table.get_text(" ", strip=True)
        if not (
            ("代號" in table_text or "股票代號" in table_text)
            and ("名稱" in table_text or "股票名稱" in table_text)
        ):
            continue

        # 取 header 行（thead 或第一個 tr）
        header_cells = []
        thead = table.find("thead")
        if thead:
            tr = thead.find("tr")
            if tr:
                header_cells = tr.find_all(["th", "td"])
        if not header_cells:
            first_tr = table.find("tr")
            if first_tr:
                header_cells = first_tr.find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True) for c in header_cells]
        col_map = _detect_table_columns(headers)
        if "code" not in col_map or "name" not in col_map:
            continue

        body = table.find("tbody")
        rows = body.find_all("tr") if body else table.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) <= max(col_map.values()):
                continue
            code = cols[col_map["code"]].get_text(strip=True)
            name = cols[col_map["name"]].get_text(strip=True)
            if not code or not name or len(name) > 80:
                continue
            if not _looks_like_stock_code(code):
                continue
            stock = {
                "股票代號": code,
                "股票名稱": name,
                "ETF股票代號": etf_stock_code,
            }
            if "shares" in col_map:
                stock["股數"] = cols[col_map["shares"]].get_text(strip=True)
            if "weight" in col_map:
                stock["持股比例"] = cols[col_map["weight"]].get_text(strip=True)
            else:
                # 後備：扫 row 內含 % 的字串
                for c in cols:
                    txt = c.get_text(strip=True)
                    if txt.endswith("%"):
                        stock["持股比例"] = txt
                        break
            stocks.append(stock)
        if stocks:
            return stocks

    # div-based 偽表格：尋找重複出現「股票代號 + 名稱 + 比例」的列
    # div-based 偽表格：尋找重複出現「股票代號 + 名稱 + 比例」的列
    # 策略：找到所有以股票代號開頭的小型 container
    candidates = []
    for el in soup.find_all(["div", "li", "tr"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 200:
            continue
        # 必須含百分比（比例欄位）
        if "%" not in text:
            continue
        # 第一個 token 必須像股票代號
        first_token = text.split()[0] if text.split() else ""
        if not _looks_like_stock_code(first_token):
            continue
        # 排除巢狀過深者（取最內層）
        if any(child for child in el.find_all(["div", "li", "tr"]) if child.get_text(strip=True) == text):
            continue
        candidates.append((el, text))

    if len(candidates) >= 5:
        seen = set()
        for el, text in candidates:
            tokens = text.split()
            code = tokens[0]
            if code in seen:
                continue
            seen.add(code)
            # name 取代號之後第一個非數字 token
            name = ""
            weight = ""
            shares = ""
            for tok in tokens[1:]:
                if "%" in tok and not weight:
                    weight = tok
                elif tok.replace(",", "").replace(".", "").isdigit() and not shares:
                    shares = tok
                elif not name and not tok.replace(",", "").replace(".", "").isdigit() and "%" not in tok:
                    name = tok
            stocks.append(
                {
                    "股票代號": code,
                    "股票名稱": name,
                    "股數": shares,
                    "持股比例": weight,
                    "ETF股票代號": etf_stock_code,
                }
            )

    return stocks


def wait_for_dynamic_content(driver, site_type: str, timeout: int = 25) -> None:
    """針對 SPA 站等待動態內容載入；不同站等待不同關鍵特徵。"""
    if site_type in ("tsit", "capitalfund", "megafunds"):
        # The static page already contains column headings; wait for actual rows.
        end = time.time() + timeout
        while time.time() < end:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            parser = {"capitalfund":scrape_capitalfund,"megafunds":scrape_megafunds}.get(site_type, scrape_generic_table)
            if parser(soup, ""):
                return
            time.sleep(1)
        return
    keyword_map = {
        "nomurafunds": ["col-code", "持股比例", "股票代號"],
        "ctbcinvestments": ["持股", "股票代號", "成分"],
        "allianzgi": ["持股", "股票代號", "成分"],
        "cathaysite": ["持股", "股票代號", "成分"],
        "jpmorgan": ["持股", "holding", "portfolio"],
        "fsitc": ["2330", "台積電", "股票代號"],
        "fhtrust": ["etfStockTable", "證券名稱"],
    }
    keywords = keyword_map.get(site_type, ["股票代號", "持股"])

    end = time.time() + timeout
    while time.time() < end:
        page = driver.page_source
        if any(kw in page for kw in keywords):
            # 再多等 1.5 秒，讓表格列也渲染
            time.sleep(1.5)
            return
        # 滾動觸發 lazy load
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(1.0)
    # 逾時就交給後續解析（仍可能成功）


def expand_more_buttons(driver, site_type: str) -> None:
    """依站別點擊『展開全部 / 顯示更多 / 查看更多』，重複點到不再變化為止。"""
    selector_map = {
        "capitalfund": ["button.pct-stock-table-tbody-toggle-btn"],
        "allianzgi": ["div.more-etf", ".more-etf"],
        "nomurafunds": ["td.showMore", "tr.red.text-center td", ".showMore"],
    }
    selectors = selector_map.get(site_type)
    if not selectors:
        return

    # 只點符合『展開』語意的按鈕，避免反覆收合
    expand_keywords = ("展開", "顯示更多", "查看更多", "更多", "show more", "load more")
    collapse_keywords = ("收合", "收起", "收回", "less", "hide")

    for _round in range(6):
        clicked = False
        for sel in selectors:
            try:
                btns = driver.find_elements("css selector", sel)
            except Exception:
                btns = []
            for btn in btns:
                try:
                    if not btn.is_displayed():
                        continue
                    # 點擊前先把按鈕文字記下，因為 click 後 toggle 文字會立刻變成「收合」
                    btn_text_raw = (btn.text or "").strip()
                    txt = btn_text_raw.lower()
                    # 跳過「收合」類
                    if any(k in txt for k in collapse_keywords):
                        continue
                    # capitalfund：必須是『展開全部』
                    if site_type == "capitalfund" and "展開" not in btn_text_raw:
                        continue
                    # nomurafunds/allianzgi：若按鈕有文字，必須含展開語意；若無文字（純圖示），仍嘗試
                    if site_type in ("nomurafunds", "allianzgi") and txt:
                        if not any(k in txt for k in expand_keywords):
                            continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.3)
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                    print(f"  [expand] 點擊 {site_type} 按鈕: {btn_text_raw[:20]!r}", flush=True)
                    clicked = True
                    time.sleep(1.2)
                except Exception:
                    continue
        if not clicked:
            break


def scrape_etf(etf_config: Dict[str, str]) -> Optional[List[Dict[str, str]]]:
    """爬取單個 ETF 的持股資訊"""
    etf_code = etf_config["code"]
    etf_url = etf_config["url"]
    site_type = detect_site_type(etf_url)

    print(f"\n爬取 {etf_code} ({etf_config['name']}) - {site_type}")
    print(f"  URL: {etf_url}")

    # 純 API 路徑：免開瀏覽器
    if site_type == "cathaysite":
        stocks = scrape_cathaysite_api(etf_code, etf_url)
        if stocks:
            print(f"  成功爬取 {len(stocks)} 筆股票")
        else:
            print(f"  cathay API 未取得資料")
        return stocks
    if site_type == "jpmorgan":
        stocks = scrape_jpmorgan_api(etf_code, etf_url)
        if stocks:
            print(f"  成功爬取 {len(stocks)} 筆股票")
        else:
            print(f"  jpmorgan API 未取得資料")
        return stocks

    # 其他站走 Selenium
    chrome_opts = ChromeOptions()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--window-size=1920,1080")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    if site_type == "ctbcinvestments":
        # 需要 performance log 攔截 token
        chrome_opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = None
    stocks = []

    try:
        driver = webdriver.Chrome(options=chrome_opts)
        driver.set_page_load_timeout(60)
        driver.get(etf_url)

        # 等待頁面加載
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception as e:
            print(f"  頁面加載超時: {e}")
            return None

        # SPA / 慢渲染站需要額外等待動態內容
        if site_type in ("nomurafunds", "ctbcinvestments", "allianzgi", "fsitc", "fhtrust", "tsit", "capitalfund", "megafunds"):
            wait_for_dynamic_content(driver, site_type)

        # 點擊『展開全部 / 顯示更多』類按鈕，避免被預設 10 筆截斷
        if site_type in ("capitalfund", "allianzgi", "nomurafunds"):
            expand_more_buttons(driver, site_type)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        detected_code = detect_etf_stock_code(soup, etf_url)
        # 以使用者配置代號為主，避免 fundCode=49YTW 這類內部代碼覆蓋
        etf_stock_code = etf_code if etf_code else detected_code
        print(f"  檢測 ETF 代號: {etf_stock_code}")

        # 根據網站類型選擇解析器
        if site_type == "fhtrust":
            stocks = scrape_fhtrust(driver, soup, etf_stock_code)
        elif site_type == "capitalfund":
            stocks = scrape_capitalfund(soup, etf_stock_code)
        elif site_type == "ezmoney":
            stocks = scrape_ezmoney(soup, etf_stock_code)
        elif site_type == "nomurafunds":
            stocks = scrape_nomurafunds(soup, etf_stock_code)
        elif site_type == "megafunds":
            stocks = scrape_megafunds(soup, etf_stock_code)
        elif site_type == "ctbcinvestments":
            stocks = scrape_ctbc_api(driver, etf_stock_code)
        else:
            # 其他網站使用通用表格解析
            stocks = scrape_generic_table(soup, etf_stock_code)

        if stocks:
            print(f"  成功爬取 {len(stocks)} 筆股票")
        else:
            print(f"  未找到股票資訊，已輸出 debug_page_{etf_code}.html")
            with open(f"debug_page_{etf_code}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)

        return stocks

    except Exception as e:
        print(f"  爬取失敗: {type(e).__name__}: {e}")
        return None

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as e:
                print(f"  關閉瀏覽器失敗: {e}")


def main():
    """主程式：爬取所有 ETF。

    流程：
        1. 對 ETF_CONFIG 中每檔 ETF 執行 scrape_etf
        2. 將每檔結果存成個別 JSON（檔名帶日期，最多保留 20 天）
        3. 彙總成 all_stocks_<日期>.json 與 all_stocks.json
        4. 依股票代號彙總所有 ETF 的股數 → stock_shares_summary_<日期>.json
        5. 與前一份 summary 比對 → stock_shares_diff_<日期>.json
        6. 全程 print 同步寫入 logs/run_<日期>.txt
    """

    # === Tee logger：把 print 同時輸出到 console 與 logs/run_YYYYMMDD.txt ===
    today = _taipei_today().strftime("%Y%m%d")
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"run_{today}.txt")
    log_file = open(log_path, "w", encoding="utf-8")

    class _Tee:
        """同時寫入多個 stream（如 stdout 與 log file）。"""

        def __init__(self, *streams):
            self._streams = streams

        def write(self, data):
            for s in self._streams:
                try:
                    s.write(data)
                except Exception:
                    pass
            return len(data)

        def flush(self):
            for s in self._streams:
                try:
                    s.flush()
                except Exception:
                    pass

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = _Tee(original_stdout, log_file)
    sys.stderr = _Tee(original_stderr, log_file)

    try:
        return _run_crawler(today, log_path)
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()


def _run_crawler(today: str, log_path: str) -> int:

    all_stocks: Dict[str, Dict] = {}
    failed_etfs: List[str] = []

    print("="*60)
    print("開始爬取多個 ETF 網站")
    print(f"執行日期: {today}")
    print(f"Log 檔: {log_path}")
    print("="*60)

    # 交易日判斷：非交易日直接結束，不執行任何爬取
    today_date = datetime.datetime.strptime(today, "%Y%m%d").date()
    if not is_tw_trading_day(today_date):
        print(f"\n今日 {today_date.isoformat()} 非交易日，停止執行。")
        print(f"Log 已寫入 {log_path}")
        return 0

    for etf_config in ETF_CONFIG:
        attempts = 1 + max(0, min(int(os.environ.get("CRAWLER_RETRIES", "0")), 2))
        stocks = None
        for attempt in range(attempts):
            try:
                stocks = scrape_etf(etf_config)
            except Exception as e:
                print(f"  {etf_config['code']} 爬取失敗: {e}")
                stocks = None
            if stocks:
                break
            if attempt + 1 < attempts:
                print(f"  {etf_config['code']} 稍後重試 ({attempt + 2}/{attempts})")
                time.sleep(3)

        if stocks:
            all_stocks[etf_config["code"]] = {
                "name": etf_config["name"],
                "date": today,
                "status": "fresh",
                "stocks": stocks
            }
        else:
            failed_etfs.append(etf_config["code"])

    fresh_codes = set(all_stocks)
    if failed_etfs and (os.environ.get("CRAWLER_ALLOW_PARTIAL") != "1" or not fresh_codes):
        print(f"爬取不完整，保留上一份完整資料，不產生異動：{', '.join(failed_etfs)}")
        return 1

    if failed_etfs:
        try:
            with open(os.path.join("etf", "all_stocks.json"), encoding="utf-8") as source:
                previous_payload = json.load(source)
        except (OSError, ValueError):
            previous_payload = {}
        configs = {item["code"]:item for item in ETF_CONFIG}
        for code in failed_etfs:
            previous = previous_payload.get("etfs", {}).get(code) or {}
            all_stocks[code] = {
                "name": configs[code]["name"], "stocks": previous.get("stocks", []),
                "date": previous.get("date", previous_payload.get("date")) if previous else None,
                "status": "stale" if previous.get("stocks") else "unavailable",
            }
        print(f"部分更新：{len(fresh_codes)} 檔成功；未更新基金保留原資料日期：{', '.join(failed_etfs)}")

    missing_share_etfs = sorted(
        code for code, data in all_stocks.items()
        if any(_parse_shares(s.get("股數")) is None for s in data["stocks"])
    )
    included_etfs = sorted(fresh_codes - set(missing_share_etfs))
    if missing_share_etfs:
        print(f"缺少有效股數，以下 ETF 僅保留持股清單，不納入股數統計：{', '.join(missing_share_etfs)}")

    # 保存結果
    print("\n" + "="*60)
    print("保存結果")
    print("="*60)

    etf_dir = "etf"
    stocks_dir = "stocks"
    stock_shares_dir = "stock_shares"
    debug_dir = "debug"
    os.makedirs(etf_dir, exist_ok=True)
    os.makedirs(stocks_dir, exist_ok=True)
    os.makedirs(stock_shares_dir, exist_ok=True)
    os.makedirs(debug_dir, exist_ok=True)

    # 1. 每個 ETF 個別保存（檔名加上日期，例如 stocks_00980A_20260428.json）
    #    並保留近 20 天，超過則刪除（每個股票代號一組獨立保留）
    KEEP_DAYS = 20
    for etf_code, data in all_stocks.items():
        if etf_code not in fresh_codes:
            continue
        filename = os.path.join(stocks_dir, f"stocks_{etf_code}_{today}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data["stocks"], f, ensure_ascii=False, indent=4)
        print(f"✓ 已保存 {filename} ({len(data['stocks'])} 筆)")

        # 清理該 ETF 超過保留天數的舊檔
        # 檔名 pattern: stocks_<code>_YYYYMMDD.json
        old_files = sorted(glob.glob(os.path.join(stocks_dir, f"stocks_{etf_code}_*.json")))
        # 過濾掉非日期後綴（如舊的 stocks_<code>.json 不會被 match 到，因為缺底線）
        valid = [f for f in old_files if re.search(rf"stocks_{etf_code}_\d{{8}}\.json$", f)]
        if len(valid) > KEEP_DAYS:
            for old in valid[:-KEEP_DAYS]:
                try:
                    os.remove(old)
                    print(f"  └ 已刪除過期檔: {old}")
                except OSError as e:
                    print(f"  └ 刪除失敗 {old}: {e}")
    
    # 2. 所有 ETF 匯總（檔名以執行日期命名，例如 all_stocks_20260428.json）
    summary = {
        "date": today,
        "total_etfs": len(ETF_CONFIG),
        "successful_etfs": len(fresh_codes),
        "updated_etfs": sorted(fresh_codes),
        "failed_etfs": failed_etfs,
        "missing_share_etfs": missing_share_etfs,
        "updated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "etfs": all_stocks
    }

    dated_filename = os.path.join(etf_dir, f"all_stocks_{today}.json")
    with open(dated_filename, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
    print(f"\n✓ 已保存 {dated_filename}")

    # 同時保留一份不帶日期的檔案，便於最新版本快速取用
    with open(os.path.join(etf_dir, "all_stocks.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
    print(f"✓ 已保存 {os.path.join(etf_dir, 'all_stocks.json')}")

    # 3. 依股票代號彙總所有 ETF 的股數
    etf_name_map = {cfg["code"]: cfg["name"] for cfg in ETF_CONFIG}
    aggregate: Dict[str, Dict] = {}
    for etf_code, data in all_stocks.items():
        if etf_code not in included_etfs:
            continue
        for s in data["stocks"]:
            code = (s.get("股票代號") or "").strip()
            if not code:
                continue
            shares = _parse_shares(s.get("股數"))
            entry = aggregate.setdefault(code, {
                "股票代號": code,
                "股票名稱": s.get("股票名稱") or "",
                "總股數": 0,
                "持有 ETF 數": 0,
                "ETF明細": [],
            })
            # 名稱以非空者為主
            if not entry["股票名稱"] and s.get("股票名稱"):
                entry["股票名稱"] = s["股票名稱"]
            entry["總股數"] += shares
            entry["持有 ETF 數"] += 1
            entry["ETF明細"].append({
                "ETF股票代號": etf_code,
                "ETF股票名稱": etf_name_map.get(etf_code, data.get("name", "")),
                "股數": shares,
                "持股比例": s.get("持股比例") or "",
            })

    # 依總股數遞減排序（暫時）
    aggregated_list = sorted(aggregate.values(), key=lambda x: x["總股數"], reverse=True)
    agg_filename = os.path.join(stock_shares_dir, f"stock_shares_summary_{today}.json")

    # 檢查是否有前一份 summary 可比較，並計算異動股數
    prev_files = sorted(
        f for f in glob.glob(os.path.join(stock_shares_dir, "stock_shares_summary_*.json"))
        if (ymd := _extract_ymd_from_filename(f, "stock_shares_summary")) and ymd < today
    )
    diff_summary = None
    total_delta_map: Dict[str, int] = {}
    if prev_files:
        prev_path = prev_files[-1]
        try:
            with open(prev_path, "r", encoding="utf-8") as f:
                prev_summary = json.load(f)
        except Exception as e:
            print(f"  無法讀取前一份 {prev_path}: {e}")
            prev_summary = None

        if prev_summary:
            if _summary_etf_scope(prev_summary) != included_etfs:
                print("  前後股數統計涵蓋的 ETF 不同，略過異動比較，避免產生假增減。")
                prev_summary = None

        if prev_summary:
            prev_date = prev_summary.get("date") or os.path.basename(prev_path)
            prev_map = {x["股票代號"]: x for x in prev_summary.get("stocks", [])}
            today_map = {x["股票代號"]: x for x in aggregated_list}
            total_delta_map = {
                code: today_map[code]["總股數"] - prev_map.get(code, {}).get("總股數", 0)
                for code in today_map
            }

            new_codes = sorted(set(today_map) - set(prev_map))
            removed_codes = sorted(set(prev_map) - set(today_map))
            common_codes = set(today_map) & set(prev_map)

            new_stocks_out = []
            for code in new_codes:
                t = today_map[code]
                new_stocks_out.append({
                    "股票代號": code,
                    "股票名稱": t["股票名稱"],
                    "總股數": t["總股數"],
                    "新增 ETF": [d["ETF股票代號"] for d in t["ETF明細"]],
                })

            removed_stocks_out = []
            for code in removed_codes:
                p = prev_map[code]
                removed_stocks_out.append({
                    "股票代號": code,
                    "股票名稱": p["股票名稱"],
                    "前次總股數": p["總股數"],
                    "移除自 ETF": [d["ETF股票代號"] for d in p.get("ETF明細", [])],
                })

            changed_out = []
            for code in sorted(common_codes):
                t = today_map[code]
                p = prev_map[code]
                shares_delta = t["總股數"] - p["總股數"]
                t_etfs = {d["ETF股票代號"]: d for d in t["ETF明細"]}
                p_etfs = {d["ETF股票代號"]: d for d in p.get("ETF明細", [])}
                added_etfs = sorted(set(t_etfs) - set(p_etfs))
                dropped_etfs = sorted(set(p_etfs) - set(t_etfs))
                etf_share_changes = []
                for e in sorted(set(t_etfs) & set(p_etfs)):
                    d_t = t_etfs[e]["股數"]
                    d_p = p_etfs[e]["股數"]
                    if d_t != d_p:
                        etf_share_changes.append({
                            "ETF股票代號": e,
                            "ETF股票名稱": t_etfs[e].get("ETF股票名稱") or p_etfs[e].get("ETF股票名稱") or etf_name_map.get(e, ""),
                            "前次股數": d_p,
                            "本次股數": d_t,
                            "差異": d_t - d_p,
                        })

                # ETF 新增/移除也併入 ETF股數變動明細，便於一次檢視完整差異
                for e in added_etfs:
                    d_t = t_etfs[e]["股數"]
                    etf_share_changes.append({
                        "ETF股票代號": e,
                        "ETF股票名稱": t_etfs[e].get("ETF股票名稱") or etf_name_map.get(e, ""),
                        "前次股數": 0,
                        "本次股數": d_t,
                        "差異": d_t,
                    })

                for e in dropped_etfs:
                    d_p = p_etfs[e]["股數"]
                    etf_share_changes.append({
                        "ETF股票代號": e,
                        "ETF股票名稱": p_etfs[e].get("ETF股票名稱") or etf_name_map.get(e, ""),
                        "前次股數": d_p,
                        "本次股數": 0,
                        "差異": -d_p,
                    })

                etf_share_changes.sort(key=lambda x: abs(x["差異"]), reverse=True)
                if shares_delta == 0 and not added_etfs and not dropped_etfs and not etf_share_changes:
                    continue
                changed_out.append({
                    "股票代號": code,
                    "股票名稱": t["股票名稱"],
                    "前次總股數": p["總股數"],
                    "本次總股數": t["總股數"],
                    "總股數差異": shares_delta,
                    "目前持有ETF": [
                        {
                            "ETF股票代號": d["ETF股票代號"],
                            "ETF股票名稱": d.get("ETF股票名稱") or etf_name_map.get(d["ETF股票代號"], ""),
                        }
                        for d in t["ETF明細"]
                    ],
                    "ETF新增": added_etfs,
                    "ETF移除": dropped_etfs,
                    "ETF股數變動": etf_share_changes,
                })

            # 依總股數差異絕對值排序，凸顯變動最大的個股
            changed_out.sort(key=lambda x: abs(x["總股數差異"]), reverse=True)

            diff_summary = {
                "date": today,
                "previous_date": prev_date,
                "previous_file": os.path.basename(prev_path),
                "included_etfs": included_etfs,
                "missing_share_etfs": missing_share_etfs,
                "新增個股數": len(new_stocks_out),
                "移除個股數": len(removed_stocks_out),
                "持股異動個股數": len(changed_out),
                "新增個股": new_stocks_out,
                "移除個股": removed_stocks_out,
                "持股異動": changed_out,
            }

    # 為每個股票項目新增總異動股數
    for stock in aggregated_list:
        code = stock["股票代號"]
        if diff_summary:
            stock["總異動股數"] = total_delta_map.get(code, 0)
        else:
            stock["總異動股數"] = 0  # 沒有前一份比較，異動股數為 0

    # 依異動股數絕對值遞減排序（如果異動股數為 0，則按總股數遞減）
    aggregated_list.sort(key=lambda x: (abs(x["總異動股數"]), x["總股數"]), reverse=True)

    agg_summary = {
        "date": today,
        "included_etfs": included_etfs,
        "missing_share_etfs": missing_share_etfs,
        "stale_etfs": failed_etfs,
        "total_unique_stocks": len(aggregated_list),
        "stocks": aggregated_list,
    }
    with open(agg_filename, "w", encoding="utf-8") as f:
        json.dump(agg_summary, f, ensure_ascii=False, indent=4)
    print(f"✓ 已保存 {agg_filename}（{len(aggregated_list)} 檔股票）")

    with open(os.path.join(stock_shares_dir, "stock_shares_summary.json"), "w", encoding="utf-8") as f:
        json.dump(agg_summary, f, ensure_ascii=False, indent=4)
    print(f"✓ 已保存 {os.path.join(stock_shares_dir, 'stock_shares_summary.json')}")

    # 4. 保存 diff（如果有）
    if diff_summary:
        # 用本日收盤價補上 當日收盤價 / 目前總投入金額 / 每1000股成本均值
        enrich_diff_with_market_values(diff_summary, today, stock_shares_dir=stock_shares_dir)

        diff_filename = os.path.join(stock_shares_dir, f"stock_shares_diff_{today}.json")
        with open(diff_filename, "w", encoding="utf-8") as f:
            json.dump(diff_summary, f, ensure_ascii=False, indent=4)
        print(f"✓ 已保存 {diff_filename}（vs {os.path.basename(prev_path)}）")
        with open(os.path.join(stock_shares_dir, "stock_shares_diff.json"), "w", encoding="utf-8") as f:
            json.dump(diff_summary, f, ensure_ascii=False, indent=4)
        print(f"  新增 {len(diff_summary['新增個股'])} 檔，移除 {len(diff_summary['移除個股'])} 檔，持股異動 {len(diff_summary['持股異動'])} 檔")

        report_path = generate_diff_html_report(stock_shares_dir, diff_summary, today)
        if report_path:
            print(f"✓ 已保存 {report_path}")
    else:
        print("（無可比較的前一份 stock_shares_summary，略過 diff）")

    # 5. 用 diff 產生近一週個股每日庫存量折線圖
    if diff_summary:
        generate_weekly_inventory_charts(stock_shares_dir, window_days=7, top_n=20)

    print(f"\n統計：")
    print(f"  總 ETF 數: {len(ETF_CONFIG)}")
    print(f"  成功爬取: {len(fresh_codes)}")
    print(f"  失敗: {len(failed_etfs)}")
    if failed_etfs:
        print(f"  失敗的 ETF: {', '.join(failed_etfs)}")

    print(f"\nLog 已寫入 {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
