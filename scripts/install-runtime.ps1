$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$downloadRoot = Join-Path $projectRoot '.local/downloads'
$runtimeRoot = Join-Path $projectRoot '.local/ollama'
$archive = Join-Path $downloadRoot 'ollama-windows-amd64.zip'
$expectedHash = '65d68cade6cf6375f398b518224f8c8a15e062387f38cf477abfc848de7e7e29'
New-Item -ItemType Directory -Force $downloadRoot | Out-Null
if (!(Test-Path -LiteralPath $archive)) {
    & curl.exe -fL --retry 2 -o $archive 'https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-windows-amd64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Runtime download failed; remove incomplete archive before retrying.' }
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Runtime checksum mismatch; inspect or remove incomplete archive before retrying.'
}
if (Test-Path -LiteralPath $runtimeRoot) { throw 'Runtime directory already exists; inspect it rather than overwriting.' }
Expand-Archive -LiteralPath $archive -DestinationPath $runtimeRoot
& (Join-Path $runtimeRoot 'ollama.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Runtime version check failed.' }

