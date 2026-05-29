"""針對 nomurafunds 找『查看更多』按鈕的真實位置/class。"""
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

opt = Options()
opt.add_argument("--headless=new")
opt.add_argument("--window-size=1400,1000")
d = webdriver.Chrome(options=opt)
try:
    d.get("https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00985A&tab=Shareholding")
    time.sleep(8)
    for _ in range(3):
        d.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
    soup = BeautifulSoup(d.page_source, "html.parser")

    # 找所有含『更多』的元素
    for tag in soup.find_all(True):
        txt = tag.get_text(strip=True)
        if not txt or len(txt) > 25:
            continue
        if "更多" in txt or "查看" in txt:
            cls = " ".join(tag.get("class") or [])
            print(f"<{tag.name} class='{cls}' id='{tag.get('id') or ''}'> {txt!r}", flush=True)
            # 印 parent class 也方便找 selector
            p = tag.parent
            for _ in range(3):
                if p is None: break
                pcls = " ".join(p.get("class") or [])
                print(f"   parent <{p.name} class='{pcls}'>", flush=True)
                p = p.parent
            print("---", flush=True)

    # row 數
    print("rows .table-list tbody tr:", len(soup.select(".table-list tbody tr")), flush=True)
    print("rows table tr:", len(soup.select("table tr")), flush=True)
finally:
    d.quit()
