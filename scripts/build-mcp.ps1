param([switch]$InstallTools,[switch]$Audit)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path $projectRoot '.local\tools'
$goBinary=Join-Path $toolRoot 'go\bin\go.exe'
if (!(Test-Path -LiteralPath $goBinary)) {
 if (!$InstallTools) { throw 'Run scripts/build-mcp.ps1 -InstallTools to prepare the pinned local Go toolchain.' }
 New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
 $archive=Join-Path $toolRoot 'go1.27.3.windows-amd64.zip'
 if (!(Test-Path -LiteralPath $archive)) { Invoke-WebRequest -Uri 'https://go.dev/dl/go1.27.3.windows-amd64.zip' -OutFile $archive }
 if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff') { throw 'Go archive integrity check failed' }
 Expand-Archive -LiteralPath $archive -DestinationPath $toolRoot
}
$env:GOTOOLCHAIN='local'
$env:GOCACHE=Join-Path $projectRoot '.local\go-cache'
$env:GOPATH=Join-Path $projectRoot '.local\go-path'
$env:PATH=(Join-Path $toolRoot 'go\bin')+';'+$env:PATH
$source=Join-Path $projectRoot 'publisher\vendor\xiaohongshu'
& $goBinary -C $source mod verify
if ($LASTEXITCODE -ne 0) { throw 'Go dependency verification failed' }
& $goBinary -C $source build -trimpath -o (Join-Path $projectRoot '.local\xiaohongshu-mcp.exe') .
if ($LASTEXITCODE -ne 0) { throw 'MCP compilation failed' }
if ($Audit) {
 Push-Location -LiteralPath $source
 try {
  & $goBinary run golang.org/x/vuln/cmd/govulncheck@v1.9.0 -json ./... | Set-Content -LiteralPath (Join-Path $projectRoot 'docs\xhs-go-vuln-report.jsonl') -Encoding utf8
  if ($LASTEXITCODE -ne 0) { throw 'Reachable vulnerability detected; see audit report' }
 } finally { Pop-Location }
}
Write-Output 'MCP executable built in .local. Real account login and publishing require separate verification.'
