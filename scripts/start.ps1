$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$ollamaExe = Join-Path $projectRoot '.local/ollama/ollama.exe'
if (!(Test-Path -LiteralPath $ollamaExe)) { throw 'Run scripts/install-runtime.ps1 first.' }
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $projectRoot '.local/models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
& $ollamaExe serve
if ($LASTEXITCODE -ne 0) { throw "Ollama exited: $LASTEXITCODE" }

