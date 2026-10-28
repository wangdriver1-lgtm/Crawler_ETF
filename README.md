# ETF Observatory

台灣主動式 ETF 觀測站，提供持股快照、增減比較、官方盤後價與配息公告、個人損益試算，以及本機 Gemini 研究介面。

**網站：https://wangdriver1-lgtm.github.io/Crawler_ETF/**

## 每日更新

GitHub Actions 在台灣時間每天 **21:00（UTC 13:00）** 啟動，非台股交易日略過持股抓取。
成功後會提交持股 JSON、產生網站資料並部署 GitHub Pages。GitHub 排程可能因平台排隊而延遲。
部分來源失敗時，成功基金先更新；失敗基金保留原日期與持股，明確標示「來源未更新」。股數增減只比較相同統計範圍，不將失敗當成減持。
全部來源失敗時保留舊資料，並在 Actions 保存診斷記錄；網站顯示各基金實際快照日期，不是瀏覽日期。

可在 [Daily Crawler ETF](https://github.com/wangdriver1-lgtm/Crawler_ETF/actions/workflows/crawler.yml) 查看狀態或手動 Run workflow。

每天先查證交所官方主動式 ETF 清單及上市日期，自動將已上市新基金加入清單（含海外股票與主動債券 ETF）。
清單快取於 `etf/active_etf_registry.json`，官方暫時無法連線時沿用快取。
既有基金沿用已驗證的持股網址；野村、台新新基金可直接由代碼建立網址。其他投信若使用內部編號且尚無可用持股接口，新基金仍自動列入並標示尚無資料；新增投信網站格式仍可能需要擴充解析器。

持股完全相同（忽略排序、數字逗號格式）時，略過新的增減計算，不覆寫已有異動報表。
ETF 詳情的增減頁保留最近 **10 個有快照的資料日**，可展開各日紀錄；重複快照標示「無異動」。
底層保留 20 份快照以提供比較基準；不補造休市日資料，也不將未知股數當成零。

## 本機執行

```sh
python -m pip install -r requirements.txt
python dashboard_server.py --port 8766
```

開啟 `http://127.0.0.1:8766/`。先執行 `python etf_registry.py` 更新官方清單，再執行 `python Crawler_ETF.py` 可單次更新持股，`python -m unittest discover -s tests` 執行離線測試。

Google AI Studio 金鑰設定於伺服器環境變數 `GEMINI_API_KEY`；模型可用 `GEMINI_MODEL` 指定。
不要將金鑰放入網頁或 Git。**GitHub Pages 提供靜態資料；即時 Gemini 分析需要另外執行 Python 後端。**

增減張數是兩份快照的股數差，不是實際成交。未知成本不能用來推算基金實際獲利，配息亦不等於總報酬。

更多操作與資料說明見 [docs/README.md](docs/README.md)。
