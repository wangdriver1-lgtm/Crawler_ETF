# 固定專案目錄
$scriptDir = 'D:\Source_Code\Crawler_ETF'

# Python 與 Script 路徑
$venvPython = Join-Path $scriptDir '.venv\Scripts\python.exe'
$scriptFile = Join-Path $scriptDir 'Crawler_ETF.py'

if (-not (Test-Path $scriptFile)) {
    Write-Error "Cannot find Crawler_ETF.py in $scriptDir"
    Read-Host "Press Enter to exit"
    exit 1
}

Push-Location $scriptDir

if (Test-Path $venvPython) {
    Write-Host "Using virtual environment Python at $venvPython"
    & $venvPython $scriptFile
} else {
    Write-Host "Virtual environment not found. Using system Python."
    python $scriptFile
}

Pop-Location
