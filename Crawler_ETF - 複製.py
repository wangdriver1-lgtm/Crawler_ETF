from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import json

url = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"

driver = webdriver.Chrome()

try:
    # 啟動瀏覽器並開啟目標頁面
    driver.get(url)

    # 等待表格元素出現，降低 JS 尚未載入完成造成抓不到資料的機率
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "table")))

    # 取得完整 HTML
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # 優先找既有 id，再退回以表頭關鍵字判斷目標表格
    stock_table = soup.find("table", {"id": "stockTable"})
    if stock_table is None:
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

    if stock_table is None:
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise RuntimeError("找不到股票持股表格，已輸出 debug_page.html 供檢查")

    stocks = []
    for row in stock_table.find_all("tr")[1:]:  # 跳過表頭
        cols = row.find_all("td")
        if len(cols) >= 4:
            stock = {
                "股票代號": cols[0].get_text(strip=True),
                "股票名稱": cols[1].get_text(strip=True),
                "股數": cols[2].get_text(strip=True),
                "持股比例": cols[3].get_text(strip=True)
            }
            stocks.append(stock)

    # 存成 JSON
    with open("stocks.json", "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=4)

    print(f"已成功存成 stocks.json，共 {len(stocks)} 筆")

except Exception as e:
    print(f"發生例外狀況: {type(e).__name__}")
    print(e)

finally:
    driver.quit()