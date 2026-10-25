param([ValidateRange(1024,65535)][int]$Port=8190,[string]$Grep="")
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$taskPython=Join-Path $projectRoot '.venv\Scripts\python.exe'
$runRoot=Join-Path $projectRoot ('.local\e2e\'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$overrides=@{
 OPS_ENVIRONMENT='development'; OPS_DATABASE_URL=('sqlite:///'+(Join-Path $runRoot 'ops.db').Replace('\','/'));
 OPS_DATA_DIR=(Join-Path $runRoot 'data'); OPS_PUBLIC_URL="http://127.0.0.1:$Port";
 OPS_SECRET_KEY=([guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N'));
 OPS_TASK_MODE='local'; OPS_SMTP_HOST=''; OPS_S3_BUCKET=''; OPS_ALIYUN_API_KEY=''; OPS_DEEPSEEK_API_KEY=''; OPS_TEXT_PROVIDER='aliyun';
 OPS_PUBLISHER_URL=''; OPS_PUBLISHER_TOKEN=''; OPS_ALLOW_LIVE_PUBLISH='false'; OPS_ALLOW_LIVE_REPLIES='false';
 E2E_BASE_URL="http://127.0.0.1:$Port"; PLAYWRIGHT_BROWSERS_PATH=(Join-Path $projectRoot '.local\browsers')
}
$previous=@{}
$preview=$null
Push-Location -LiteralPath $projectRoot
try {
 foreach ($item in $overrides.GetEnumerator()) { $previous[$item.Key]=[Environment]::GetEnvironmentVariable($item.Key,'Process'); [Environment]::SetEnvironmentVariable($item.Key,$item.Value,'Process') }
 & $taskPython -m app.cli demo
 if ($LASTEXITCODE -ne 0) { throw 'Isolated demo initialization failed' }
 $preview=Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port",'--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runRoot 'server.log') -RedirectStandardError (Join-Path $runRoot 'server-error.log')
 $ready=$false
 for ($attempt=0; $attempt -lt 40; $attempt++) {
  if ($preview.HasExited) { throw 'Isolated preview could not start; see .local/e2e server logs' }
  try { $health=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2; $ready=$true; break } catch { Start-Sleep -Milliseconds 250 }
 }
 if (!$ready) { throw 'Isolated preview health timeout' }
 if ($Grep) { npm test --prefix frontend -- --grep $Grep } else { npm test --prefix frontend }
 if ($LASTEXITCODE -ne 0) { throw 'Browser acceptance failed; see docs/e2e-report.json' }
 Write-Output 'Browser acceptance passed against an isolated database. The working preview database was preserved.'
} finally {
 if ($preview -and !$preview.HasExited) { Stop-Process -Id $preview.Id }
 foreach ($item in $previous.GetEnumerator()) { [Environment]::SetEnvironmentVariable($item.Key,$item.Value,'Process') }
 Pop-Location
}
