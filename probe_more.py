"""探測各站是否有『展開更多/分頁/載入全部』按鈕，以及目前 DOM 中 row 數量。"""
import sys, time, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

SITES = [
    ("00982A", "capitalfund", "https://www.capitalfund.com.tw/etf/product/detail/399/portfolio"),
    ("00984A", "allianzgi",   "https://etf.allianzgi.com.tw/etf-info/E0001?tab=4"),
    ("00980A", "nomurafunds", "https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A&tab=Shareholding"),
]

KEYWORDS = ["更多", "展開", "全部", "顯示", "more", "More", "Show", "expand", "load", "下一頁", "下一", "Next"]


def make_driver():
    opt = Options()
    opt.add_argument("--headless=new")
    opt.add_argument("--window-size=1400,1000")
    return webdriver.Chrome(options=opt)


def probe(code, site_type, url):
    print(f"\n========== {code} ({site_type}) ==========", flush=True)
    print(f"URL: {url}", flush=True)
    driver = make_driver()
    try:
        driver.get(url)
        time.sleep(8)
        # 多滾幾次觸發 lazy load
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 統計可能 row 數
        candidates = {
            "table tr": len(soup.select("table tr")),
            ".pct-stock-table-tbody .tr": len(soup.select(".pct-stock-table-tbody .tr")),
            ".pct-stock-table-tbody .tr.show-for-medium": len(soup.select(".pct-stock-table-tbody .tr.show-for-medium")),
            ".table-list tbody tr": len(soup.select(".table-list tbody tr")),
            "#Shareholding tbody tr": len(soup.select("#Shareholding tbody tr")),
            "tbody tr": len(soup.select("tbody tr")),
        }
        for k, v in candidates.items():
            if v:
                print(f"  rows[{k}] = {v}", flush=True)

        # 找含關鍵字的 button/a
        hits = []
        for tag in soup.find_all(["button", "a", "span", "div"]):
            txt = tag.get_text(strip=True)
            if not txt or len(txt) > 30:
                continue
            for kw in KEYWORDS:
                if kw.lower() in txt.lower():
                    cls = tag.get("class") or []
                    hits.append((tag.name, txt, " ".join(cls)))
                    break
        # 去重
        seen = set()
        uniq = []
        for h in hits:
            key = (h[0], h[1])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(h)
        print(f"  候選按鈕({len(uniq)}):", flush=True)
        for tag, txt, cls in uniq[:30]:
            print(f"    <{tag} class='{cls}'> {txt!r}", flush=True)

        # 也輸出含 'pagination' 的 class
        for el in soup.select("[class*=pagination], [class*=paging], [class*=page]"):
            cls = " ".join(el.get("class") or [])
            txt = el.get_text(" ", strip=True)[:60]
            if cls:
                print(f"  pagination-like class='{cls}' txt={txt!r}", flush=True)
    finally:
        driver.quit()


if __name__ == "__main__":
    for s in SITES:
        try:
            probe(*s)
        except Exception as e:
            print(f"  probe 失敗 {s[0]}: {e}", flush=True)
