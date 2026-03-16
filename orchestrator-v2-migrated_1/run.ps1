<#
.SYNOPSIS
    Native Windows 11 / PowerShell 7 Bootstrapper (Accelerated by 'uv')
#>

$ErrorActionPreference = "Stop"

Write-Host "🎙️ Initializing Interview Orchestrator (uv-powered)..." -ForegroundColor Cyan

# 0. Verify uv is installed
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "🛑 ERROR: 'uv' is not recognized. Please ensure it is installed and in your PATH." -ForegroundColor Red
    exit 1
}

# 1. Create Virtual Environment via uv (uv uses .venv by default)
if (-not (Test-Path ".venv")) {
    Write-Host "⚡ Creating ultra-fast virtual environment with uv..." -ForegroundColor Yellow
    uv venv | Out-Null
}

# 2. Install Dependencies via uv
Write-Host "⬇️ Resolving 2026 Dependencies with uv..." -ForegroundColor Yellow
# uv pip install is lightning fast and strictly respects the .venv sandbox
uv pip install -r requirements.txt | Out-Null

# 3. Secure .env Configuration (Enforcing UTF-8 for PowerShell 7)
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    }
    else {
        Set-Content -Path ".env" -Value "GEMINI_API_KEY=your_key_here" -Encoding utf8
    }
    Write-Host "⚠️ ACTION REQUIRED: Created .env file." -ForegroundColor Red
    Write-Host "Opening Notepad. Please paste your GEMINI_API_KEY, save, close, and run this script again." -ForegroundColor Red
    Start-Process "notepad.exe" ".env" -Wait
    exit 0
}

# 4. API Key Audit
$envContent = Get-Content ".env" -Raw
if ($envContent -match "your_key_here" -or $envContent -match "your_actual_key") {
    Write-Host "🛑 ERROR: GEMINI_API_KEY is still set to the placeholder in .env!" -ForegroundColor Red
    Start-Process "notepad.exe" ".env"
    exit 1
}

# 5. Boot Server & Auto-Launch Chrome
Write-Host "🚀 Starting Flask Server via uv (Press Ctrl+C to stop)..." -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor DarkGray

# Spin off a background OS job to wait 2 seconds, then launch Chrome
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    $URL = "http://127.0.0.1:5000"
    try {
        Start-Process "chrome.exe" $URL -ErrorAction Stop
    }
    catch {
        # Fallback to system default if Chrome isn't mapped in PATH
        Start-Process $URL
    }
} | Out-Null

# 6. Start Flask seamlessly inside the uv isolated environment
# This completely bypasses the need for Activate.ps1 or Execution Policies!
uv run python app.py