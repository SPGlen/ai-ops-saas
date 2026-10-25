param(
 [ValidateRange(1024,65535)][int]$Port=8188,
 [string]$PublicUrl='',
 [switch]$Fresh,
 [switch]$Stop,
 [switch]$NoBrowser,
 [ValidateSet('local','shared')][string]$Channel='local',
 [ValidateRange(1,72)][int]$Hours=8
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$taskPython=Join-Path $projectRoot '.venv\Scripts\python.exe'
$demoFolder=Join-Path $projectRoot $(if($Channel -eq 'shared'){'.local\showcase-shared'}else{'.local\showcase'})
$statePath=Join-Path $demoFolder 'server.json'
Push-Location -LiteralPath $projectRoot
try {
 if (!(Test-Path -LiteralPath $taskPython)) { throw '请先安装项目依赖：运行 scripts\dev.ps1 -Install，或使用本机已配置的项目环境。' }
 $listeners=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
 foreach($listener in $listeners) {
  $processInfo=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
  if (!$processInfo -or !$processInfo.CommandLine -or !$processInfo.CommandLine.Contains($projectRoot) -or $processInfo.CommandLine -notmatch 'uvicorn\s+app\.main:app' -or $processInfo.CommandLine -notmatch "--port\s+$Port(?:\s|$)") {
   throw "端口 $Port 被其他程序占用，未停止该程序。请更换 -Port 参数。"
  }
  Stop-Process -Id $listener.OwningProcess
 }
 if($Stop) { Write-Output '企业演示已停止；原有数据库及演示记录均保留。'; return }
 if(!$PublicUrl) { $PublicUrl="http://127.0.0.1:$Port" }
 $prepare=@('scripts/prepare-showcase.py','--public-url',$PublicUrl,'--channel',$Channel,'--hours',"$Hours")
 if($Fresh) { $prepare+='--fresh' }
 & $taskPython @prepare
 if($LASTEXITCODE -ne 0) { throw '演示数据准备失败，原有开发数据库未改动。' }
 $config=Get-Content -LiteralPath (Join-Path $demoFolder 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 if(!(Test-Path -LiteralPath 'frontend\dist\index.html')) {
  npm run build --prefix frontend
  if($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
 }
 $expiryValue=if($config.expires_at -is [datetime]){$config.expires_at.ToUniversalTime().ToString('o')}else{[string]$config.expires_at}
 $overrides=@{
  OPS_ENVIRONMENT='development';OPS_DEMO_MODE='true';OPS_TASK_MODE='demo';
  OPS_DATABASE_URL=('sqlite:///'+$config.database_path.Replace('\','/'));
  OPS_DATA_DIR=$config.data_dir;OPS_SECRET_KEY=$config.secret_key;OPS_PUBLIC_URL=$config.public_url;
  OPS_DEMO_ACCESS_CODE=$config.access_code;OPS_DEMO_EXPIRES_AT=$expiryValue;OPS_ALIYUN_API_KEY='';OPS_SMTP_HOST='';OPS_SMTP_USER='';OPS_SMTP_PASSWORD='';
  OPS_S3_BUCKET='';OPS_S3_ACCESS_KEY='';OPS_S3_SECRET_KEY='';OPS_PUBLISHER_URL='';OPS_PUBLISHER_TOKEN='';
  OPS_ALLOW_LIVE_PUBLISH='false';OPS_ALLOW_LIVE_REPLIES='false';OPS_OCR_ENABLED='false'
 }
 $previous=@{}
 try {
  foreach($item in $overrides.GetEnumerator()) { $previous[$item.Key]=[Environment]::GetEnvironmentVariable($item.Key,'Process');[Environment]::SetEnvironmentVariable($item.Key,[string]$item.Value,'Process') }
  $process=Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port",'--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $demoFolder 'server.log') -RedirectStandardError (Join-Path $demoFolder 'server-error.log')
 } finally { foreach($item in $previous.GetEnumerator()) { [Environment]::SetEnvironmentVariable($item.Key,$item.Value,'Process') } }
 $ready=$false
 for($attempt=0;$attempt -lt 50;$attempt++) {
  if($process.HasExited) { throw '演示服务启动失败，请查看 .local\showcase\server-error.log。' }
  try { $health=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2;$ready=$true;break } catch { Start-Sleep -Milliseconds 250 }
 }
 if(!$ready) { throw '启动超时，请查看演示服务日志。' }
 @{pid=$process.Id;port=$Port;public_url=$config.public_url;started_at=(Get-Date).ToString('o');run_dir=$config.run_dir} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
 Write-Output "企业演示已就绪：$PublicUrl"
 Write-Output '全部资料均为虚构；正常岗位权限生效；AI、外部发布与消息发送关闭。'
 if($config.access_code) {
  $accessFile=Join-Path $demoFolder '外部演示访问说明.txt'
  @("访问地址：$PublicUrl",'打开网页后输入演示访问码，无需用户名。',"访问码：$($config.access_code)",'通过验证后，在页面选择演示岗位进入。',"访问到期（UTC）：$expiryValue",'请将访问码单独发送给获准测试者；不要录入真实资料。') | Set-Content -LiteralPath $accessFile -Encoding UTF8
  Write-Output "外部访问验证已启用；访问码请在本机文件查看：$accessFile"
 }
 if(!$NoBrowser) { Start-Process -FilePath "$PublicUrl" }
} finally { Pop-Location }
