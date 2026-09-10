# ============================================
# File: cli/run_cli.ps1
# Purpose: Launch the CLI in a new PowerShell window.
#
# Flow:
#   1. Detect Python; abort if not found.
#   2. Try importing httpx; install from requirements.txt if missing.
#   3. cd to cli/ and run python cli.py.
#   4. Ctrl+C / quit -> window closes naturally.
#
# Called by: setup.ps1 via Start-Process
# ============================================

$ErrorActionPreference = "Stop"

# ----- locate this script's directory -----
try {
    $ScriptDir = $PSScriptRoot
} catch {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = (Get-Location).Path
}

$CliDir  = $ScriptDir
$CliReqs = Join-Path $CliDir "requirements.txt"
$CliMain = Join-Path $CliDir "cli.py"

# ----- banner -----
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Recording Transcript Service - CLI" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ----- step 1: Python -----
Write-Host "[1/3] Detecting Python..." -ForegroundColor Yellow
$py = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $py = $candidate
        break
    }
}
if (-not $py) {
    Write-Host "  [X] Python not found." -ForegroundColor Red
    Write-Host "  Please install Python 3.10+ and ensure 'python' is in PATH." -ForegroundColor Yellow
    Write-Host "  Download: https://www.python.org/downloads/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
try {
    $ver = & $py --version 2>&1
    Write-Host "  OK  $ver" -ForegroundColor Green
} catch {
    Write-Host "  [X] Failed to run $py : $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ----- step 2: dependencies -----
Write-Host ""
Write-Host "[2/3] Checking dependencies..." -ForegroundColor Yellow
$depsOk = $false
try {
    & $py -c "import httpx" 2>$null
    if ($LASTEXITCODE -eq 0) { $depsOk = $true }
} catch {
    $depsOk = $false
}

if ($depsOk) {
    Write-Host "  OK  httpx already installed." -ForegroundColor Green
} else {
    Write-Host "  httpx missing - installing..." -ForegroundColor Yellow
    if (-not (Test-Path $CliReqs)) {
        Write-Host "  [X] requirements.txt not found: $CliReqs" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    & $py -m pip install -r $CliReqs -i "https://pypi.tuna.tsinghua.edu.cn/simple"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [X] pip install failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "  OK  dependencies installed." -ForegroundColor Green
}

# ----- step 3: launch CLI -----
Write-Host ""
Write-Host "[3/3] Starting CLI..." -ForegroundColor Yellow
Write-Host "  Type 'quit' to exit, Ctrl+C to cancel." -ForegroundColor DarkGray
Write-Host ""
Write-Host "-----------------------------------------" -ForegroundColor DarkGray
Write-Host ""

Push-Location $CliDir
try {
    & $py $CliMain
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "-----------------------------------------" -ForegroundColor DarkGray
if ($exitCode -ne 0) {
    Write-Host "CLI exited (code=$exitCode)" -ForegroundColor Yellow
} else {
    Write-Host "CLI exited normally." -ForegroundColor Green
}
Read-Host "Press Enter to close"
exit $exitCode
