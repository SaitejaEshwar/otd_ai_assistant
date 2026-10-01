param([string]$PythonCommand = "python", [string]$PnpmCommand = "pnpm")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    & $PythonCommand -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating the Python environment failed." }
    & ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Installing backend dependencies failed." }
    if (-not (Test-Path -LiteralPath ".env")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
    }
    & $PnpmCommand --dir frontend install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "Installing frontend dependencies failed." }
    & $PnpmCommand --dir frontend build
    if ($LASTEXITCODE -ne 0) { throw "Building the frontend failed." }
    Write-Host "Setup complete. Run .\scripts\start.ps1"
} finally { Pop-Location }
