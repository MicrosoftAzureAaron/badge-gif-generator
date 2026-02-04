# Badge GIF Generator - Run Script (Windows)
# Starts the local web server and opens the browser

param(
    [switch]$Install,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Badge GIF Generator - Offline Mode" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Python not found! Please install Python 3.8+ from python.org" -ForegroundColor Red
    exit 1
}

# Create virtual environment if it doesn't exist
$venvPath = Join-Path $ScriptDir ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $venvPath
    $Install = $true
}

# Activate virtual environment
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
. $activateScript

# Install dependencies if needed
if ($Install) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r (Join-Path $ScriptDir "requirements.txt")
    Write-Host "Dependencies installed!" -ForegroundColor Green
}

# Start the server
Write-Host ""
Write-Host "Starting server on http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host ""

Set-Location $ScriptDir
python -m src.server
