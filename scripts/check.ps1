$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& python (Join-Path $projectRoot 'examples/chat.py') --check
if ($LASTEXITCODE -ne 0) { throw 'API or tool check failed.' }
$env:OLLAMA_HOST = '127.0.0.1:11435'
& (Join-Path $projectRoot '.local/ollama/ollama.exe') ps
if ($LASTEXITCODE -ne 0) { throw 'GPU placement check failed.' }

