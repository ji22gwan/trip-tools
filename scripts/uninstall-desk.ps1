# Trip Desk 삭제. 프로그램과 바로가기만 지우고, 출장 데이터는 물어본 뒤에만 지운다. Windows PowerShell.
$ErrorActionPreference = 'Stop'
$HomeDir = if ($env:TRIP_TOOLS_HOME) { $env:TRIP_TOOLS_HOME } else { Join-Path $env:USERPROFILE '.trip-tools' }
$Data = if ($env:TRIPDESK_HOME) { $env:TRIPDESK_HOME } else { Join-Path $env:USERPROFILE 'TripDesk' }
if ($env:YES -ne '1') { if ((Read-Host 'Trip Desk 프로그램을 삭제할까요? [y/N]') -notmatch '^[yY]') { Write-Host '취소했어요.'; exit 0 } }
Remove-Item (Join-Path $HomeDir 'desk') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $HomeDir 'tripdesk.cmd') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Trip Desk.lnk') -Force -ErrorAction SilentlyContinue
if ((Test-Path $HomeDir) -and -not (Get-ChildItem $HomeDir -Force)) { Remove-Item $HomeDir -Force }
Write-Host '프로그램을 삭제했어요.'
if (Test-Path $Data) {
  Write-Host "출장 데이터 폴더가 남아 있어요: $Data  (지도, 업체 목록, AI 설정과 API 키 포함)"
  if ($env:YES -eq '1') { $purge = ($env:PURGE_DATA -eq '1') } else { $purge = ((Read-Host '이 데이터도 삭제할까요? 되돌릴 수 없어요. [y/N]') -match '^[yY]') }
  if ($purge) { Remove-Item $Data -Recurse -Force; Write-Host '데이터도 삭제했어요.' } else { Write-Host '데이터는 그대로 뒀어요.' }
}
