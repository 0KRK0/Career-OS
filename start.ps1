# Career OS launcher (Windows). Double-click start.bat, or run:
#   powershell -ExecutionPolicy Bypass -File start.ps1
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "  Career OS" -ForegroundColor Cyan
Write-Host "  ---------"

# 1) Python 3.10+
$py = $null
foreach ($cand in @("py -3", "python", "python3")) {
  try { $null = cmd /c "$cand --version" 2>$null; if ($LASTEXITCODE -eq 0) { $py = $cand; break } } catch {}
}
if (-not $py) {
  Write-Host "Python not found. Installing Python 3.12 with winget..." -ForegroundColor Yellow
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  Write-Host "Close this window and run start.bat again." -ForegroundColor Yellow
  exit 1
}

# 2) Private virtual environment
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating the Python environment (first run only)..."
  cmd /c "$py -m venv .venv"
}
$vpy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# 3) Packages (reinstalled only when requirements.txt changes)
$hash = (Get-FileHash requirements.txt).Hash
$stamp = ".venv\.requirements-hash"
if (-not (Test-Path $stamp) -or ((Get-Content $stamp) -ne $hash)) {
  Write-Host "Installing packages (first run takes a minute)..."
  & $vpy -m pip install --upgrade pip --quiet
  & $vpy -m pip install -r requirements.txt --quiet
  Set-Content $stamp $hash
}

# 4) Browser for autofill: your installed Chrome, else Playwright's Chromium
$chrome = (Test-Path "$env:ProgramFiles\Google\Chrome\Application\chrome.exe") -or
          (Test-Path "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe") -or
          (Test-Path "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
if (-not $chrome -and -not (Test-Path ".venv\.chromium")) {
  Write-Host "Chrome not found - downloading Chromium for autofill (once)..."
  & $vpy -m playwright install chromium
  Set-Content ".venv\.chromium" "ok"
  & $vpy -c "from careeros.config import save_settings; save_settings({'browser_channel': ''})"
}

# 5) Claude Code = the agents' brain, runs on your Claude Pro plan (no API key, no extra cost)
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude -and -not (Test-Path "$env:USERPROFILE\.local\bin\claude.exe")) {
  Write-Host "Installing Claude Code (included with your Pro plan)..." -ForegroundColor Yellow
  try { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression } catch { Write-Host "Claude Code install failed: $_" -ForegroundColor Red }
  Write-Host ""
  Write-Host "  ONE-TIME LOGIN: open a new terminal, type  claude  and sign in with your" -ForegroundColor Yellow
  Write-Host "  Claude Pro account (choose the Claude subscription login, NOT an API key)." -ForegroundColor Yellow
  Write-Host "  Career OS still starts now; agents that need Claude wait until you log in." -ForegroundColor Yellow
  Write-Host ""
}
if ($env:ANTHROPIC_API_KEY) {
  Write-Host "Note: ANTHROPIC_API_KEY is set on this PC. Career OS removes it for its agents so they use your Pro plan, never paid API billing." -ForegroundColor Yellow
}

# 6) Go
Write-Host "Starting at http://127.0.0.1:8765  (keep this window open; close it to stop)" -ForegroundColor Green
if ($NoBrowser) { & $vpy -m careeros --no-browser } else { & $vpy -m careeros }
