# ✅ GitHub 配置檢查清單

## 已完成的配置 ✓

- ✅ Git 2.54.0 已安裝
- ✅ 本地倉庫已初始化
- ✅ 所有文件已提交 (3 次提交)
- ✅ `.gitignore` 已配置
- ✅ `requirements.txt` 已配置
- ✅ GitHub Actions 工作流文件已優化
- ✅ 工作流已配置每晚 9 點（台灣時間）執行

## 待完成事項 ⏳

### ☐ 步驟 1: 在 GitHub 上創建倉庫

訪問: https://github.com/new

設置:
- 倉庫名稱: `Crawler_ETF`
- 隱私: Public 或 Private (根據需要)
- **重要**: 不要初始化任何文件 (README、.gitignore 等)

點擊 "Create repository"

### ☐ 步驟 2: 推送代碼

在 PowerShell 中執行:

```powershell
cd "C:\Users\leo_m\OneDrive\Desktop\Code\Crawler_ETF"
& "C:\Program Files\Git\bin\git.exe" push -u origin main
```

如出現認證提示:
- **Username**: `wangdriver1-lgtm`
- **Password**: 使用 Personal Access Token (見下方)

### ☐ 步驟 3: 生成 Personal Access Token

1. 訪問: https://github.com/settings/tokens
2. 點擊 "Generate new token" > "Generate new token (classic)"
3. 填寫:
   - Token name: `git-cli-crawler`
   - Expiration: 90 days (或 180 days)
   - Select scopes:
     - ✓ `repo` (完整控制)
     - ✓ `workflow` (更新 GitHub Actions)
4. 點擊 "Generate token"
5. **複製並保存** token (只會顯示一次!)

### ☐ 步驟 4: 驗證推送

訪問: https://github.com/wangdriver1-lgtm/Crawler_ETF

檢查:
- ✓ 所有文件已上傳
- ✓ 分支名為 `main`
- ✓ 可看到 3 次提交

### ☐ 步驟 5: 啟用 GitHub Actions

進入倉庫設置:
1. 倉庫頁面 > Settings (設定齒輪圖標)
2. 左側菜單 > Actions > General
3. 在 "Workflow permissions" 中:
   - 選擇: ◉ "Read and write permissions"
   - ✓ 勾選 "Allow GitHub Actions to create and approve pull requests"
4. 點擊 "Save"

## ⏰ 工作流運行時間

配置: 每天 **13:00 UTC** (= 台灣時間 **21:00**)

- **第一次運行**: 明天 (05-30) 晚上 9 點
- **監控**: 進入倉庫 > Actions 標籤查看執行日誌

## 🧪 測試工作流 (可選)

立即測試工作流:
1. 進入倉庫 > Actions 標籤
2. 左側 > "Daily Crawler ETF"
3. 點擊 "Run workflow" > "Run workflow" 確認

## 📞 故障排除

### 推送失敗: "fatal: could not read Username"
```powershell
& "C:\Program Files\Git\bin\git.exe" config --global credential.helper wincred
```

### 推送失敗: "Invalid username or password"
- 確認使用 **Personal Access Token** (不是 GitHub 密碼)
- 確認 Token 包含 `repo` 和 `workflow` 權限

### Actions 不執行
- 確認 Repository 設置中已啟用 "Workflow permissions"
- 確認工作流文件語法正確 (YAML 格式)

### 爬蟲執行失敗
- 檢查 Actions 日誌查看錯誤信息
- 可能需要在 `requirements.txt` 中添加額外依賴
- Selenium 可能需要 ChromeDriver

## 📋 完整流程總結

```
1. 建立 GitHub 倉庫 ──→ 2. 推送代碼 ──→ 3. 配置 Actions ──→ 4. 完成!
                        (認證)
```

---

**當完成以上所有步驟後，爬蟲將在每個工作日晚上 9 點自動執行。**

祝設置順利! 🚀
