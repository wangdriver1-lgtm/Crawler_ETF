# 📊 ETF 爬蟲數據查看器

歡迎使用 ETF 爬蟲數據查看器！這是一個通過 GitHub Pages 展示實時 ETF 基金數據的網站。

## 🌐 訪問網站

網站已部署在 GitHub Pages，訪問以下地址：

```
https://wangdriver1-lgtm.github.io/Crawler_ETF/
```

## ✨ 功能特性

- 📈 **實時數據展示** - 展示最新的 ETF 基金信息
- 🔄 **自動更新** - 每晚 9 點自動更新數據
- 📱 **響應式設計** - 支持桌面和移動設備
- 🎨 **現代界面** - 美觀的視覺設計

## 📊 數據來源

- **更新頻率**: 每晚 21:00（台灣時間）
- **數據格式**: JSON
- **數據位置**: `docs/data/` 目錄
- **採集來源**: 台灣主要基金公司官網

## 📁 文件結構

```
docs/
├── index.html                 # 主頁面
└── data/
    └── active_etf_summary.json # ETF 基金數據
```

## 🚀 工作流程

1. **爬蟲運行** - 每晚 9 點自動運行 `Crawler_ETF.py`
2. **數據收集** - 從各基金公司網站收集最新信息
3. **數據更新** - 更新 `docs/data/` 中的 JSON 文件
4. **網站更新** - GitHub Pages 自動刷新顯示最新數據

## 資料日期與股數統計

網站摘要使用 `{ "date": "YYYYMMDD", "updated_at": "ISO 8601", "etfs": { ... } }` 格式。
日期取自爬蟲資料；缺少來源日期或更新時間時顯示「未提供」，不使用瀏覽時間代替。

本機預設：若任何 ETF 爬取失敗，本次執行回傳失敗狀態，保留上一份完整輸出。
GitHub 每日排程啟用 `CRAWLER_ALLOW_PARTIAL=1`，成功來源先更新；失敗來源保留原持股與原資料日，標示為「來源未更新」，不寫成當日持股。
股數統計只涵蓋本次成功且股數有效的 ETF，範圍改變時略過增減比較，避免假減持。若所有來源皆失敗則不更新。
國泰權重 API 目前沒有股數欄位，因此仍保留其持股清單與比例，但不納入股數統計。
`missing_share_etfs` 列出缺少有效股數的 ETF；`included_etfs` 列出實際納入股數統計的 ETF。
只有統計範圍相同的快照才比較異動；範圍變動後第一份快照作為新基準。

離線回歸測試：在專案根目錄執行 `python -m unittest discover -s tests`。
測試使用暫存目錄與模擬 API／瀏覽器，不更新現有爬蟲資料。

## 🔧 技術棧

- **前端**: HTML5 + CSS3 + JavaScript (Vanilla)
- **數據格式**: JSON
- **部署平台**: GitHub Pages
- **自動化**: GitHub Actions
- **運行時**: Python 3.11

## 💡 使用說明

### 瀏覽器訪問

1. 打開瀏覽器
2. 訪問: https://wangdriver1-lgtm.github.io/Crawler_ETF/
3. 頁面會自動加載最新數據

### 刷新數據

點擊頁面上的 "🔄 重新加載" 按鈕可強制刷新數據。

## 📋 監控 GitHub Actions

要查看自動更新的執行日誌：

1. 進入 GitHub 倉庫
2. 點擊 "Actions" 標籤
3. 選擇 "Daily Crawler ETF" 工作流
4. 查看最近的運行記錄

## 🐛 故障排除

### 網頁無法加載
- 確認 GitHub Pages 已啟用
- 檢查倉庫設置中的 Pages 配置

### 數據未更新
- 檢查 GitHub Actions 工作流是否成功執行
- 查看執行日誌中的錯誤信息

### JSON 文件加載失敗
- 確認 `docs/data/active_etf_summary.json` 文件存在
- 檢查文件路徑是否正確

## ETF 詳細資訊

在 ETF 清單點選代碼或任一列，可開啟持股、持股增減、獲利試算、股利分配與未來趨勢。
持股以本機快照日期為準；增減比較最近兩份較早快照，不等同昨日實際成交。
台股以 1,000 股換算一張，海外成分股僅顯示股數。缺少股數時不計算增減。

盤後收盤價與配息公告由本機後端查詢證交所，顯示各自資料日期，快取五分鐘。
官方資料無法取得時保留缺值，不將「未取得」當作零股價或無配息。
個人損益以輸入的持有單位、平均成本、參考價與實領配息試算；不代表基金本身獲利，未計費稅。
基金實際持股成本沒有公開於本機資料，不能由快照推算實際基金損益。

GitHub Pages 的持股詳情由工作流程匯出 `docs/data/etf_details/*.json`；本機可執行
`python etf_details.py --export docs/data/etf_details` 更新。靜態頁無法直接提供官方即時查詢及 AI 後端。

## AI 個股分析（本機網站）

左側「AI 個股分析」可輸入股票代碼或公司名稱，選擇一、三或六個月的分析期間。
結果含基本面、近期事件、價量趨勢與基本／偏多／偏空情境，並保留搜尋引用。
資料不足時不推算虛構報價或勝率；這是研究與情境分析，不是報酬保證。

在啟動伺服器的終端機環境設定 `GEMINI_API_KEY`，再於專案根目錄執行：

```powershell
python dashboard_server.py --port 8765
```

開啟 `http://127.0.0.1:8765/#ai-analysis`。金鑰只由伺服器使用，不放入 HTML、瀏覽器儲存空間或 Git。
請從 [Google AI Studio](https://aistudio.google.com/apikey) 取得金鑰。預設模型為 `gemini-3.8-flash`，可用 `GEMINI_MODEL` 覆寫為帳戶可用且支援 Google 搜尋的 Gemini 模型。
每次按下分析會呼叫 Gemini API 與 Google 搜尋，依 Google API 帳戶額度計費。金鑰以伺服器端 `x-goog-api-key` 標頭傳送，不放在網址中。
未設定金鑰時會顯示設定提示；純靜態 GitHub Pages 與 `python -m http.server` 只支援查看 ETF 資料。
本機伺服器固定綁定 `127.0.0.1`；如需公開部署，應先加入使用者驗證與用量限制。

串接依據：[Gemini Google 搜尋引用文件](https://ai.google.dev/gemini-api/docs/generate-content/google-search)。

## 📞 聯絡方式

如有問題或建議，請提交 Issue 或 Pull Request。

## 📄 授權

本項目採用 MIT 授權。詳見 LICENSE 文件。

---

**最後更新**: 2026-05-29
