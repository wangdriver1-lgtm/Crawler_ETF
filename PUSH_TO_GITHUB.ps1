#!/bin/bash
# GitHub 快速設置腳本 (PowerShell 版本)

# 如果在 PowerShell 中執行以下命令：

# 第一步：定義 Git 路徑
$gitPath = "C:\Program Files\Git\bin\git.exe"

# 第二步：在倉庫目錄中
cd "C:\Users\leo_m\OneDrive\Desktop\Code\Crawler_ETF"

# 第三步：推送到 GitHub
& $gitPath push -u origin main

# 如果出現認證提示，您需要：
# 1. 使用 GitHub 用戶名: wangdriver1-lgtm
# 2. 使用 Personal Access Token 作為密碼（而不是實際密碼）

# Personal Access Token 生成步驟：
# 1. 訪問 https://github.com/settings/tokens
# 2. 點擊 "Generate new token" → "Generate new token (classic)"
# 3. 名稱: "git-cli"
# 4. 選擇 "repo" 和 "workflow" 權限
# 5. 複製生成的 token
# 6. 在終端提示時粘貼 token 作為密碼

# 或者使用以下命令設置默認認證方式：
& $gitPath config --global credential.helper wincred

# 然後重試推送：
& $gitPath push -u origin main
