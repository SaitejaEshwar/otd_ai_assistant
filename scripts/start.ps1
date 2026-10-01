$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Run scripts\setup.ps1 first." }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "frontend\dist\index.html"))) {
    throw "Build the frontend first: pnpm --dir frontend build"
}
Push-Location $projectRoot
try {
    & $pythonPath -m otd_assistant
    if ($LASTEXITCODE -ne 0) { throw "The application exited with an error." }
} finally { Pop-Location }
