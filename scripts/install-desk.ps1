# 노트북 앱 Trip Desk 설치. Windows PowerShell. %USERPROFILE%\.trip-tools\desk 에 설치하고 바탕화면 바로가기를 만든다.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$HomeDir = if ($env:TRIP_TOOLS_HOME) { $env:TRIP_TOOLS_HOME } else { Join-Path $env:USERPROFILE '.trip-tools' }
$Dest = Join-Path $HomeDir 'desk'
function Say($m) { Write-Host ""; Write-Host $m -ForegroundColor Cyan }
function Die($m) { Write-Host ""; Write-Host "오류: $m" -ForegroundColor Red; exit 1 }

$py = $null
foreach ($c in @(@('py', '-3'), @('python'))) {
  if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
    $a = if ($c.Count -gt 1) { $c[1..($c.Count - 1)] } else { @() }
    & $c[0] @a -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  }
}
if (-not $py) { Die 'Python 3.10 이상이 필요해요. https://www.python.org 에서 설치하고(설치 화면에서 "Add python.exe to PATH" 체크) 다시 실행해 주세요.' }
$pyExe = $py[0]; $pyArgs = if ($py.Count -gt 1) { $py[1..($py.Count - 1)] } else { @() }

Say "1/3 파일 복사 -> $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if (Test-Path (Join-Path $Dest 'tripdesk')) { Remove-Item (Join-Path $Dest 'tripdesk') -Recurse -Force }
Copy-Item (Join-Path $Root 'desk\tripdesk') (Join-Path $Dest 'tripdesk') -Recurse
Copy-Item (Join-Path $Root 'desk\requirements.txt') $Dest -Force
Copy-Item (Join-Path $Root 'desk\requirements-whisper.txt') $Dest -Force
Get-ChildItem $Dest -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Say '2/3 실행 환경 만들기 (venv + openpyxl)'
$venvPy = Join-Path $Dest 'venv\Scripts\python.exe'
# 이전 시도에서 pip 없이 만들어진 반쪽짜리 venv 가 남아 있을 수 있어, pip 가 되는지 확인하고 아니면 새로 만든다
$pipOk = $false
if (Test-Path $venvPy) { & $venvPy -m pip --version *> $null; $pipOk = ($LASTEXITCODE -eq 0) }
if (-not $pipOk) {
  if (Test-Path (Join-Path $Dest 'venv')) { Remove-Item (Join-Path $Dest 'venv') -Recurse -Force }
  & $pyExe @pyArgs -m venv (Join-Path $Dest 'venv'); if ($LASTEXITCODE -ne 0) { Die 'venv 를 만들지 못했어요.' }
  & $venvPy -m ensurepip --upgrade *> $null
  & $venvPy -m pip --version *> $null; if ($LASTEXITCODE -ne 0) { Die 'venv 에 pip 가 없어요. Python 을 다시 설치해 주세요.' }
}
& $venvPy -m pip install --quiet --disable-pip-version-check -r (Join-Path $Dest 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Die '패키지 설치에 실패했어요(인터넷 연결 확인).' }
if ($env:WHISPER -eq '1') {
  Say '   음성 인식 엔진(faster-whisper) 설치 중... 용량이 커서 몇 분 걸릴 수 있어요'
  & $venvPy -m pip install --quiet --disable-pip-version-check -r (Join-Path $Dest 'requirements-whisper.txt')
  if ($LASTEXITCODE -ne 0) { Die '음성 인식 엔진 설치에 실패했어요(인터넷 연결 확인). WHISPER 없이 다시 실행하면 나머지 기능은 쓸 수 있어요.' }
}

Say '3/3 바로가기 만들기'
$cmd = Join-Path $HomeDir 'tripdesk.cmd'
"@echo off`r`ncd /d `"$Dest`"`r`n`"$venvPy`" -m tripdesk %*`r`n" | Set-Content -Path $cmd -Encoding ASCII
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Trip Desk.lnk'
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk); $sc.TargetPath = $cmd; $sc.WorkingDirectory = $Dest; $sc.Description = 'Trip Desk'; $sc.Save()

Write-Host @"

설치가 끝났어요.
  실행: 바탕화면의 'Trip Desk' 바로가기 (검은 창이 열리고 브라우저가 떠요. 끝낼 땐 검은 창을 닫으세요)
  데이터 폴더: $env:USERPROFILE\TripDesk (삭제해도 이 폴더는 남겨 둬요)
"@ -ForegroundColor Green
