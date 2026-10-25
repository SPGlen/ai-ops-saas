param([int]$Port=8188,[switch]$Install,[switch]$Publisher)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
$taskPython=Join-Path $projectRoot '.venv\Scripts\python.exe'
if ($Install) {
    & $taskPython -m pip install -r backend/requirements.lock
    & $taskPython -m pip install --no-deps -e ./backend
    npm ci --prefix frontend
}
& $taskPython scripts/configure.py
$publisherProcess=$null
if ($Publisher) {
    & $taskPython scripts/configure-publisher-dev.py
    if ($LASTEXITCODE -ne 0) { throw 'Local publisher configuration failed' }
    $publisherProcess=Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','publisher.dev_gateway:app','--host','127.0.0.1','--port','8900','--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
}
if (!(Test-Path -LiteralPath 'frontend\dist\index.html')) { npm run build --prefix frontend }
& $taskPython -m app.cli demo
$env:OPS_PUBLIC_URL="http://127.0.0.1:$Port"
try { & $taskPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --no-access-log } finally { if ($publisherProcess -and !$publisherProcess.HasExited) { Stop-Process -Id $publisherProcess.Id } }
