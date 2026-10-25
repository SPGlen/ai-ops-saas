param([switch]$Stop,[switch]$NoBrowser,[ValidateRange(1,72)][int]$Hours=8,[ValidateRange(1024,65535)][int]$Port=8191)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$folder=Join-Path $projectRoot '.local\showcase-shared'
$stateFile=Join-Path $folder 'tunnel.json'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
function Stop-DemoTunnel {
 if(Test-Path -LiteralPath $stateFile) {
  $state=Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
  $info=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)" -ErrorAction SilentlyContinue
  if($info -and $info.CommandLine -and $info.CommandLine.Contains($projectRoot) -and $info.CommandLine.Contains('cloudflared-2026.10.3.exe') -and $info.CommandLine.Contains("127.0.0.1:$($state.port)")) { Stop-Process -Id $state.pid }
 }
}
Stop-DemoTunnel
if($Stop) { & (Join-Path $PSScriptRoot 'showcase.ps1') -Channel shared -Port $Port -Stop -NoBrowser;Write-Output '临时外网入口已关闭。';return }
$lock=Get-Content -LiteralPath (Join-Path $projectRoot 'docs\demo-tools-lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$tools=Join-Path $projectRoot '.local\tools'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$executable=Join-Path $tools 'cloudflared-2026.10.3.exe'
if(!(Test-Path -LiteralPath $executable)) {
 $download=Join-Path $tools ('cloudflared-'+[guid]::NewGuid().ToString('N')+'.download')
 Write-Output '正在下载官方临时演示连接工具，随后核对固定版本校验值。'
 Invoke-WebRequest -Uri $lock.url -OutFile $download -TimeoutSec 45
 if((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.sha256) { throw '连接工具校验失败，未运行下载内容。' }
 Move-Item -LiteralPath $download -Destination $executable
}
if((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.sha256) { throw '连接工具与官方版本校验值不符，未运行。' }
# Start only a loopback origin on its own port; the normal local demo remains separate.
if(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { & (Join-Path $PSScriptRoot 'showcase.ps1') -Channel shared -Port $Port -Stop -NoBrowser }
$stamp=(Get-Date).ToString('yyyyMMdd-HHmmss')
$log=Join-Path $folder ("tunnel-$stamp.log")
$out=Join-Path $folder ("tunnel-$stamp-stdout.log")
$err=Join-Path $folder ("tunnel-$stamp-stderr.log")
$process=$null
try {
 $process=Start-Process -FilePath $executable -ArgumentList @('tunnel','--no-autoupdate','--url',"http://127.0.0.1:$Port",'--protocol','http2','--loglevel','info','--logfile',$log) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
 $url=''
 for($attempt=0;$attempt -lt 80;$attempt++) {
  if($process.HasExited) { throw '临时隧道未能连接；本机演示仍可使用，请查看 .local\showcase-shared 的连接日志。' }
  $text=''
  foreach($file in @($log,$err,$out)) { if(Test-Path -LiteralPath $file) { $text+=(Get-Content -LiteralPath $file -Raw -ErrorAction SilentlyContinue) } }
  $match=[regex]::Match($text,'https://[a-z0-9-]+\.trycloudflare\.com')
  if($match.Success) { $url=$match.Value;break }
  Start-Sleep -Milliseconds 250
 }
 if(!$url) { throw '获取临时地址超时；请先使用本机演示。' }
 & (Join-Path $PSScriptRoot 'showcase.ps1') -Channel shared -Port $Port -PublicUrl $url -Hours $Hours -NoBrowser
 if(!$?) { throw '独立外部演示服务未能启动。' }
 @{pid=$process.Id;port=$Port;url=$url;started_at=(Get-Date).ToString('o');hours=$Hours} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
 $config=Get-Content -LiteralPath (Join-Path $folder 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 $verified=$false
 for($probe=0;$probe -lt 5;$probe++) {
  try { $result=Invoke-RestMethod -Uri "$url/api/v1/health" -TimeoutSec 5;if($result.status -eq 'ok' -and $result.tasks -eq 'demo'){$verified=$true;break} } catch { Start-Sleep -Milliseconds 800 }
 }
 if(!$verified) { Write-Warning '隧道和本机服务已经启动，但本机到临时域名的外网验证未通过。请用手机移动网络检查，现场先使用本机地址。' }
 @{pid=$process.Id;port=$Port;url=$url;started_at=(Get-Date).ToString('o');hours=$Hours;external_probe_verified=$verified} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
 Write-Output "临时外部演示地址：$url"
 Write-Output "有效期：$Hours 小时；本机、网络及连接进程需要保持运行。"
 Write-Output ('访问码文件：'+(Join-Path $folder '外部演示访问说明.txt'))
 if(!$NoBrowser) { Start-Process -FilePath "$url" }
} catch {
 if($process -and !$process.HasExited) { Stop-Process -Id $process.Id }
 throw
}
