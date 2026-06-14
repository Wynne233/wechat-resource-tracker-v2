$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$wewe = Join-Path $root "external\wewe-rss"

Push-Location $wewe
$dbDir = Join-Path $env:TEMP "wechat-resource-tracker-v2"
New-Item -ItemType Directory -Force -Path $dbDir | Out-Null
$dbPath = (Join-Path $dbDir "wewe-rss.db").Replace("\", "/")
$env:DATABASE_URL = "file:$dbPath"
$env:DATABASE_TYPE = "sqlite"
$env:AUTH_CODE = "123567"
$env:SERVER_ORIGIN_URL = "http://localhost:4000"
$env:FEED_MODE = "fulltext"
npx -y pnpm@8.15.9 run start:server
Pop-Location
