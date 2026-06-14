$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$wewe = Join-Path $root "external\wewe-rss"
$weweServer = Join-Path $wewe "apps\server"
$exporter = Join-Path $root "external\wechat-article-exporter"

$env:PUPPETEER_SKIP_DOWNLOAD = "true"

Write-Host "Installing wechat-article-exporter dependencies..."
Push-Location $exporter
$env:PUPPETEER_SKIP_DOWNLOAD = "true"
npm install --package-lock=false --legacy-peer-deps --no-audit --no-fund --ignore-scripts
npx nuxt prepare
$env:NODE_OPTIONS = "--max-old-space-size=8192"
npx nuxt build
Pop-Location

Write-Host "Installing wewe-rss dependencies..."
Push-Location $wewe
npx -y pnpm@8.15.9 install --frozen-lockfile
npx -y pnpm@8.15.9 --filter web build
npx -y pnpm@8.15.9 --filter server build
Pop-Location

Write-Host "Switching wewe-rss server Prisma schema to SQLite..."
$prismaDir = Join-Path $weweServer "prisma"
$sqlitePrismaDir = Join-Path $weweServer "prisma-sqlite"
$mysqlPrismaBackup = Join-Path $weweServer "prisma-mysql"
if ((Test-Path $prismaDir) -and -not (Test-Path $mysqlPrismaBackup)) {
  Rename-Item -LiteralPath $prismaDir -NewName "prisma-mysql"
}
if (Test-Path $prismaDir) {
  Remove-Item -LiteralPath $prismaDir -Recurse -Force
}
Copy-Item -LiteralPath $sqlitePrismaDir -Destination $prismaDir -Recurse

Write-Host "Generating and migrating wewe-rss SQLite database..."
Push-Location $wewe
$weweDbDir = Join-Path $env:TEMP "wechat-resource-tracker-v2"
New-Item -ItemType Directory -Force -Path $weweDbDir | Out-Null
$weweDbPath = (Join-Path $weweDbDir "wewe-rss.db").Replace("\", "/")
$env:DATABASE_URL = "file:$weweDbPath"
$env:DATABASE_TYPE = "sqlite"
Push-Location (Join-Path $wewe "apps\server")
.\node_modules\.bin\prisma.CMD generate --schema prisma\schema.prisma
$migrationRoot = Join-Path (Get-Location) "prisma\migrations"
Get-ChildItem -LiteralPath $migrationRoot -Directory | Sort-Object Name | ForEach-Object {
  $sql = Join-Path $_.FullName "migration.sql"
  if (Test-Path $sql) {
    python -c "import sqlite3, pathlib; db=r'$weweDbPath'; sql=pathlib.Path(r'$sql').read_text(encoding='utf-8'); con=sqlite3.connect(db); con.executescript(sql); con.commit(); con.close()"
  }
}
Pop-Location
Pop-Location

Write-Host "External tools are ready."
