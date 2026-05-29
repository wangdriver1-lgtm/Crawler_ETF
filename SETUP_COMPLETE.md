# GitHub 上傳和 GitHub Actions 設置完成

## ✅ 已完成的設置

### 1. Git 安裝
- ✅ Git 2.54.0 已安裝
- ✅ 位置: `C:\Program Files\Git\bin\git.exe`

### 2. 本地倉庫初始化
- ✅ Git 倉庫已初始化
- ✅ 用戶配置: wangdriver1-lgtm (wangdriver1@gmail.com)
- ✅ 已添加 67 個文件（首次提交）
- ✅ 分支已改名為 `main`

### 3. 遠程倉庫配置
- ✅ 遠程倉庫地址: `https://github.com/wangdriver1-lgtm/Crawler_ETF.git`
- ⏳ 等待推送到 GitHub

### 4. GitHub Actions 工作流
- ✅ 工作流文件已創建: `.github/workflows/crawler.yml`
- ✅ 時間表：每天晚上 9 點 (台灣時間 = UTC 13:00)
- ✅ 自動運行命令: `python Crawler_ETF.py`
- ✅ 支持手動觸發

### 5. 輔助文件
- ✅ `.gitignore` - 排除不需要的文件
- ✅ `requirements.txt` - Python 依賴清單
- ✅ 說明文檔 - `GITHUB_SETUP_CN.md`

## 📋 最後步驟

### 步驟 1: 創建 GitHub 倉庫
如果您還沒有創建倉庫，請訪問:
https://github.com/new

配置：
- 倉庫名稱: `Crawler_ETF`
- 隱私性: Public (或 Private)
- **不要初始化 README 或其他文件**

### 步驟 2: 推送代碼
打開 PowerShell 並運行以下命令：

```powershell
cd "C:\Users\leo_m\OneDrive\Desktop\Code\Crawler_ETF"
& "C:\Program Files\Git\bin\git.exe" push -u origin main
```

### 步驟 3: GitHub 認證
如果出現認證提示：

**選項 A: 使用 Personal Access Token (推薦)**
1. 訪問 https://github.com/settings/tokens
2. 點擊 "Generate new token" → "Generate new token (classic)"
3. 設置：
   - Token name: `git-cli`
   - Expiration: 90 days (或更長)
   - Select scopes: ✓ repo, ✓ workflow
4. 複製生成的 token
5. 在終端提示時：
   - Username: `wangdriver1-lgtm`
   - Password: 粘貼 token

**選項 B: 使用 Windows 認證管理器**
```powershell
& "C:\Program Files\Git\bin\git.exe" config --global credential.helper wincred
```

### 步驟 4: 驗證推送
1. 訪問 https://github.com/wangdriver1-lgtm/Crawler_ETF
2. 確認所有文件已上傳

### 步驟 5: 啟用 GitHub Actions 權限
1. 進入倉庫設置: Settings → Actions → General
2. 在 "Workflow permissions" 中選擇:
   - ✓ "Read and write permissions"
   - ✓ "Allow GitHub Actions to create and approve pull requests"
3. 點擊 "Save"

## 🕘 GitHub Actions 排程詳解

工作流運行時間表：
```
0 13 * * *  (CRON 表達式)
↑  ↑ ↑ ↑ ↑
│  │ │ │ └─ 星期 (0-6, 0=Sunday)
│  │ │ └─── 月份 (1-12)
│  │ └───── 月份中的日期 (1-31)
│  └─────── 小時 (0-23, UTC 時區)
└────────── 分鐘 (0-59)

13:00 UTC = 21:00 台灣時間 (UTC+8)
```

## 🔧 工作流任務詳細

每次執行時，GitHub Actions 將：
1. 檢查代碼
2. 設置 Python 3.11
3. 安裝依賴 (requirements.txt)
4. 運行爬蟲: `python Crawler_ETF.py`
5. 如有更新，自動提交到 GitHub

## 📊 監控和調試

- **查看執行日誌**: 倉庫 → Actions → Daily Crawler ETF
- **手動執行工作流**: Actions → Daily Crawler ETF → "Run workflow"
- **查看工作流日誌**: 選擇特定運行 → 查看日誌

## 常見問題排除

### 推送失敗: "fatal: could not read Username"
**解決**:
```powershell
git config --global credential.helper wincred
```

### 推送失敗: "Authentication failed"
**解決**: 
- 確認使用了 Personal Access Token (不是 GitHub 密碼)
- 檢查 Token 權限是否包含 `repo` 和 `workflow`

### 工作流失敗: "ModuleNotFoundError"
**解決**:
- 更新 `requirements.txt` 文件
- 確保所有依賴都被列出

### 工作流失敗: "ChromeDriver not found"
**解決**:
- GitHub Actions 環境需要額外配置 Selenium
- 添加浏览器设置到工作流中

## 📞 下一步

1. ✅ 完成推送和認證
2. ✅ 確認 GitHub 倉庫中有所有文件
3. ✅ 配置 GitHub Actions 權限
4. ✅ 等待第一次自動執行 (明天晚上 9 點)
5. ✅ 檢查執行日誌確認爬蟲正常運行

---

更新日期: 2026-05-29
