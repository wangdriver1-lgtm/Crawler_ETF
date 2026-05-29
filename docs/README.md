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

## 📞 聯絡方式

如有問題或建議，請提交 Issue 或 Pull Request。

## 📄 授權

本項目採用 MIT 授權。詳見 LICENSE 文件。

---

**最後更新**: 2026-05-29
