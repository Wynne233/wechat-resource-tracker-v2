$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$exporter = Join-Path $root "external\wechat-article-exporter"

Push-Location $exporter
$env:PORT = "4100"
$env:HOST = "127.0.0.1"
node .output/server/index.mjs
Pop-Location
