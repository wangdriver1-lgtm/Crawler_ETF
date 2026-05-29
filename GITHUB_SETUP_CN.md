# GitHub 上傳和 GitHub Actions 配置說明

## 已準備的文件
✅ `.gitignore` - 排除不需要版本控制的文件
✅ `.github/workflows/crawler.yml` - GitHub Actions 工作流（每晚 9 點台灣時間執行）
✅ `requirements.txt` - Python 依賴包清單

## 後續步驟

### 1. 確認 Git 安裝完成
- 若彈出 Git 安裝窗口，請點擊 "Next" 完成安裝
- 安裝完成後，重新開啟 PowerShell

### 2. 初始化本地 Git 倉庫
```powershell
cd "c:\Users\leo_m\OneDrive\Desktop\Code\Crawler_ETF"
git init
git config --global user.email "你的GitHub郵箱"
git config --global user.name "你的GitHub用戶名"
```

### 3. 添加所有文件到 Git
```powershell
git add .
git commit -m "初始提交：ETF 爬蟲項目"
```

### 4. 在 GitHub 上創建新倉庫
- 訪問 https://github.com/new
- 倉庫名稱：`Crawler_ETF`
- 描述：(可選) "ETF data crawler"
- 選擇 "Public" 或 "Private"
- 點擊 "Create repository"

### 5. 連接本地倉庫到 GitHub（使用 HTTPS）
```powershell
git remote add origin https://github.com/wangdriver1-lgtm/Crawler_ETF.git
git branch -M main
git push -u origin main
```

如果出現認證窗口，輸入 GitHub 用戶名和密碼（或 Personal Access Token）

### 6. 設置 GitHub Actions 執行權限
- 進入倉庫 → Settings → Actions → General
- 在 "Workflow permissions" 中選擇 "Read and write permissions"
- 勾選 "Allow GitHub Actions to create and approve pull requests"
- 點擊 "Save"

## GitHub Actions 配置說明
- **運行時間**：每天晚上 9 點（台灣時間 = UTC 13:00）
- **運行任務**：執行 `python Crawler_ETF.py`
- **自動提交**：若有新數據，自動提交到 GitHub
- **環境**：Windows latest, Python 3.11

## 手動觸發工作流
可在任何時候手動運行工作流：
- 進入倉庫 → Actions → Daily Crawler ETF → "Run workflow"

## 常見問題排解
1. **認證失敗**：使用 Personal Access Token 替代密碼
   - GitHub → Settings → Developer settings → Personal access tokens → Generate new token
   - 權限勾選：repo, workflow

2. **Workflow 失敗**：檢查 Actions 標籤下的執行日誌

3. **推送失敗**：確保網路連接，重試推送命令
