$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$web = Join-Path $root "apps\web"

Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" -WorkingDirectory $api -WindowStyle Hidden
Start-Process -FilePath "powershell" -ArgumentList "-NoProfile","-Command",'$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"; npx next dev -p 3000' -WorkingDirectory $web -WindowStyle Hidden

Write-Host "Product API: http://127.0.0.1:8000"
Write-Host "Product Web: http://127.0.0.1:3000"
