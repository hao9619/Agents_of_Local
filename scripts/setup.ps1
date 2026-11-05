$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$ollamaExe = Join-Path $projectRoot '.local/ollama/ollama.exe'
$env:OLLAMA_HOST = '127.0.0.1:11435'
Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 5
& $ollamaExe show 'qwen3.5:4b-q4_K_M' *> $null
if ($LASTEXITCODE -ne 0) {
    & $ollamaExe pull 'qwen3.5:4b-q4_K_M'
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
}
& $ollamaExe create 'local-coder-4060' -f (Join-Path $projectRoot 'profiles/rtx-4060/Modelfile')
if ($LASTEXITCODE -ne 0) { throw 'Model creation failed.' }

