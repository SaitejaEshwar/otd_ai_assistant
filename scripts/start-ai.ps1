$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$server = Get-ChildItem -LiteralPath (Join-Path $projectRoot "runtime\llama") -Filter llama-server.exe -Recurse | Select-Object -First 1
$model = Join-Path $projectRoot "models\qwen2.5-1.5b-instruct-q4_k_m.gguf"
if (-not $server -or -not (Test-Path -LiteralPath $model)) { throw "Run .\.venv\Scripts\python.exe scripts\setup_ai.py first." }
& $server.FullName -m $model --host 127.0.0.1 --port 8081 -c 8192 -np 1 -ngl 0 --alias otd-qwen
if ($LASTEXITCODE -ne 0) { throw "The local AI server exited with an error." }
