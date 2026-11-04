# 설치한 번역 서버(Worker)와 폰 앱(Pages)을 Cloudflare 에서 삭제한다. Windows PowerShell.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StateDir = if ($env:TRIP_TOOLS_HOME) { $env:TRIP_TOOLS_HOME } else { Join-Path $env:USERPROFILE '.trip-tools' }
$StateFile = Join-Path $StateDir 'install.json'
$WorkerName = if ($env:WORKER_NAME) { $env:WORKER_NAME } else { 'trip-translate' }
$PagesName = if ($env:PAGES_NAME) { $env:PAGES_NAME } else { 'trip-field' }
if (Test-Path $StateFile) {
  $s = Get-Content $StateFile -Raw | ConvertFrom-Json
  if ($s.WORKER_NAME) { $WorkerName = $s.WORKER_NAME }; if ($s.PAGES_NAME) { $PagesName = $s.PAGES_NAME }
}
function Run-Wr([string[]]$ArgList, [string]$StdIn = $null) {
  Push-Location (Join-Path $Root 'worker')
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    if ($StdIn) { $out = ($StdIn | & npx.cmd --no-install wrangler @ArgList 2>&1 | Out-String) } else { $out = (& npx.cmd --no-install wrangler @ArgList 2>&1 | Out-String) }
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $old; Pop-Location }
  return @{ Out = $out; Code = $code }
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Write-Host 'Node.js(npm)가 없어요.' -ForegroundColor Red; exit 1 }

Write-Host @"
다음을 Cloudflare 에서 삭제합니다.
  - 번역 서버(Worker): $WorkerName   (등록한 Gemini 키·토큰도 함께 사라져요)
  - 폰 앱(Pages 프로젝트): $PagesName
  - 로컬 설치 기록: $StateFile
폰에 저장된 출장 데이터(녹음·메모)는 건드리지 않아요. 단, 앱 주소가 사라지면 그 앱은 더 열 수 없어요.
"@
if ($env:YES -ne '1') { if ((Read-Host "계속하려면 '삭제' 를 입력하세요") -ne '삭제') { Write-Host '취소했어요.'; exit 0 } }

Push-Location (Join-Path $Root 'worker'); try { & npm.cmd install --no-audit --no-fund --loglevel=error } finally { Pop-Location }
if ((Run-Wr @('whoami')).Code -ne 0) { Push-Location (Join-Path $Root 'worker'); try { & npx.cmd --no-install wrangler login } finally { Pop-Location } }

$failed = $false
Write-Host "`n번역 서버 삭제" -ForegroundColor Cyan
$r = Run-Wr @('delete', $WorkerName) "y"
if ($r.Code -eq 0) { Write-Host '삭제했어요.' } else { Write-Host $r.Out; Write-Host '삭제하지 못했어요(이미 없거나 권한 문제).'; $failed = $true }
Write-Host "`n폰 앱(Pages) 삭제" -ForegroundColor Cyan
if ($s -and $s.KV_ID) {
  Write-Host '패키지 보관함(KV) 삭제'
  $rk = Run-Wr @('kv', 'namespace', 'delete', '--namespace-id', $s.KV_ID) "y"
  if ($rk.Code -ne 0) { Write-Host '삭제하지 못했어요(이미 없거나 권한 문제).'; $failed = $true } else { Write-Host '삭제했어요.' }
}
$r = Run-Wr @('pages', 'project', 'delete', $PagesName, '--yes')
if ($r.Code -eq 0) { Write-Host '삭제했어요.' } else { Write-Host $r.Out; Write-Host '삭제하지 못했어요(이미 없거나 권한 문제).'; $failed = $true }
if (-not $failed) { Remove-Item $StateFile -Force -ErrorAction SilentlyContinue }

Write-Host @"

정리할 것이 더 있어요(자동으로 할 수 없어요):
  1. Google AI Studio 에서 이 용도로 만든 Gemini API 키를 삭제(또는 재발급)하세요.
  2. 폰 홈 화면에 추가한 Trip Field 아이콘을 지우세요.
  3. $(if ($failed) { '삭제에 실패한 항목은 Cloudflare 대시보드(Workers & Pages)에서 직접 지워 주세요.' } else { 'Cloudflare 대시보드에서 남은 항목이 없는지 확인해 보세요.' })
"@
