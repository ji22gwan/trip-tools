# 번역 서버(Cloudflare Worker)와 폰 앱(Cloudflare Pages)을 내 Cloudflare 계정에 설치한다. Windows PowerShell.
# 다시 실행해도 안전하다(같은 토큰을 유지하고 코드만 갱신한다).
# 미리 준비: Node.js 18+, Cloudflare 계정(무료), Gemini API 키
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$WorkerName = if ($env:WORKER_NAME) { $env:WORKER_NAME } else { 'trip-translate' }
$PagesName = if ($env:PAGES_NAME) { $env:PAGES_NAME } else { 'trip-field' }
$StateDir = if ($env:TRIP_TOOLS_HOME) { $env:TRIP_TOOLS_HOME } else { Join-Path $env:USERPROFILE '.trip-tools' }
$StateFile = Join-Path $StateDir 'install.json'
$DefaultModel = 'gemini-3.5-flash-lite'

function Say($m) { Write-Host ""; Write-Host $m -ForegroundColor Cyan }
function Die($m) { Write-Host ""; Write-Host "오류: $m" -ForegroundColor Red; exit 1 }

# wrangler 를 worker 폴더에서 실행하고 출력과 종료 코드를 돌려준다
function Run-Wr([string[]]$ArgList) {
  Push-Location (Join-Path $Root 'worker')
  $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { $out = (& npx.cmd --no-install wrangler @ArgList 2>&1 | Out-String); $code = $LASTEXITCODE }
  finally { $ErrorActionPreference = $old; Pop-Location }
  return @{ Out = $out; Code = $code }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Die 'Node.js 가 없어요. https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해 주세요.' }
$major = [int](node -p "process.versions.node.split('.')[0]")
if ($major -lt 18) { Die "Node.js 18 이상이 필요해요(현재 $(node -v))." }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$state = @{}
if (Test-Path $StateFile) { (Get-Content $StateFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $state[$_.Name] = $_.Value } }

# 내 ID: 서버·폰 앱 이름에 붙어 나만의 주소가 된다(trip-field-ID.pages.dev). 각자 자기 Cloudflare 계정에 설치하므로 저장공간도 사람마다 따로예요.
$hadState = Test-Path $StateFile
$id = if ($env:TRIP_ID) { $env:TRIP_ID } elseif ($state['ID']) { $state['ID'] } else { '' }
if (-not $id -and -not $hadState -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
  Say '내 ID 정하기'
  Write-Host '영문 소문자·숫자·하이픈만, 2~20자 (예: ji). 이 ID 로 나만의 주소가 만들어져요.'
  while ($true) {
    $id = (Read-Host 'ID').Trim().ToLower()
    if ($id -match '^[a-z][a-z0-9-]{1,19}$') { break }
    Write-Host '형식이 맞지 않아요. 영문 소문자로 시작하고 영문 소문자·숫자·하이픈만 쓸 수 있어요.'
  }
}
if ($id) {
  if ($id -notmatch '^[a-z][a-z0-9-]{1,19}$') { Die 'ID 형식이 맞지 않아요(영문 소문자로 시작, 영문 소문자·숫자·하이픈, 2~20자).' }
  $WorkerName = "trip-translate-$id"; $PagesName = "trip-field-$id"
} elseif ($state['WORKER_NAME']) { $WorkerName = $state['WORKER_NAME']; $PagesName = $state['PAGES_NAME'] }

Say '1/6 도구 설치 (wrangler)'
Push-Location (Join-Path $Root 'worker'); try { & npm.cmd install --no-audit --no-fund --loglevel=error; if ($LASTEXITCODE -ne 0) { Die 'npm install 에 실패했어요.' } } finally { Pop-Location }

Say '2/6 Cloudflare 로그인 확인'
if ((Run-Wr @('whoami')).Code -ne 0) {
  Write-Host "브라우저가 열리면 Cloudflare 계정으로 로그인하고 '허용'을 눌러 주세요."
  Push-Location (Join-Path $Root 'worker'); try { & npx.cmd --no-install wrangler login } finally { Pop-Location }
}

Say '3/6 Gemini 설정'
$key = $env:GEMINI_API_KEY
if (-not $key) {
  $sec = Read-Host 'Gemini API 키를 붙여 넣고 Enter (화면에 보이지 않아요)' -AsSecureString
  $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
if (-not $key) { Die 'Gemini API 키가 비어 있어요.' }
$model = $env:GEMINI_MODEL
if (-not $model) { $model = Read-Host "사용할 모델 ID [기본: $DefaultModel]" }
if (-not $model) { $model = $DefaultModel }
Write-Host "모델: $model"

$token = $state['TOKEN']
if (-not $token) {
  $b = New-Object byte[] 24
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  $token = ($b | ForEach-Object { $_.ToString('x2') }) -join ''
}

$pagesUrl = ''
if ($env:SKIP_PAGES -ne '1') {
  Say '4/6 폰 앱 배포 (Cloudflare Pages)'
  [void](Run-Wr @('pages', 'project', 'create', $PagesName, '--production-branch', 'main'))   # 이미 있으면 실패해도 무시
  $r = Run-Wr @('pages', 'deploy', (Join-Path $Root 'field-pwa'), '--project-name', $PagesName, '--branch', 'main')
  if ($r.Code -ne 0) { Write-Host $r.Out; Die '폰 앱 배포에 실패했어요.' }
  # 배포 한 번마다 붙는 주소(8자리코드.이름.pages.dev)가 아니라 프로젝트 고정 주소(이름.pages.dev)를 쓴다.
  # 1순위: Cloudflare 에 프로젝트의 실제 주소를 물어본다 / 2순위: 출력에서 앞의 8자리 코드를 뗀다
  $pagesUrl = ''
  $lr = Run-Wr @('pages', 'project', 'list', '--json')
  if ($lr.Code -eq 0) {
    try {
      $t = $lr.Out; $rows = $t.Substring($t.IndexOf('[')) | ConvertFrom-Json
      foreach ($row in $rows) {
        $vals = @($row.PSObject.Properties | ForEach-Object { [string]$_.Value })
        if ($vals -contains $PagesName) {
          $doms = [regex]::Matches(($vals -join ','), '[a-z0-9-]+\.pages\.dev') | ForEach-Object { $_.Value }
          $d = ($doms | Where-Object { $_ -eq "$PagesName.pages.dev" } | Select-Object -First 1)
          if (-not $d) { $d = ($doms | Where-Object { $_ -like "$PagesName*" } | Select-Object -First 1) }
          if (-not $d) { $d = ($doms | Select-Object -First 1) }
          if ($d) { $pagesUrl = "https://$d"; break }
        }
      }
    } catch { }
  }
  if (-not $pagesUrl) {
    $urls = [regex]::Matches($r.Out, 'https://[a-z0-9.-]+\.pages\.dev') | ForEach-Object { $_.Value }
    $last = $urls | Select-Object -Last 1
    if ($last) { $pagesUrl = $last -replace '^https://[0-9a-f]{8}\.', 'https://' }
  }
} else { Say '4/6 폰 앱 배포 건너뜀 (SKIP_PAGES=1)' }

Say '5/6 번역 서버 배포 (Cloudflare Worker)'
$origin = if ($pagesUrl) { $pagesUrl } else { '*' }
# 출장 패키지 보관함(KV). 만들지 못해도 번역은 그대로 쓸 수 있다.
$deployCfg = 'wrangler.toml'
$kvId = if ($env:KV_ID) { $env:KV_ID } elseif ($state["KV_ID"]) { $state["KV_ID"] } else { '' }
if (-not $kvId) {
  $k = Run-Wr @('kv', 'namespace', 'create', 'TRIP_PACKAGES')
  $m0 = [regex]::Match($k.Out, '[0-9a-f]{32}'); if ($m0.Success) { $kvId = $m0.Value }
  if (-not $kvId) {
    $l = Run-Wr @('kv', 'namespace', 'list')
    try { $arr = $l.Out.Substring($l.Out.IndexOf('[')) | ConvertFrom-Json; $hit = $arr | Where-Object { $_.title -like '*TRIP_PACKAGES' } | Select-Object -First 1; if ($hit) { $kvId = $hit.id } } catch {}
  }
}
if ($kvId) {
  $base = Get-Content (Join-Path $Root 'worker\wrangler.toml') -Raw
  Set-Content -Path (Join-Path $Root 'worker\.deploy.toml') -Value ($base + "`n[[kv_namespaces]]`nbinding = `"PACKAGES`"`nid = `"$kvId`"`n") -Encoding UTF8
  $deployCfg = '.deploy.toml'
} else { Write-Host '참고: 패키지 보관함(KV)을 만들지 못했어요. 번역은 정상이고, 출장 패키지는 ZIP 파일로 옮겨 주세요.' }
$r = Run-Wr @('deploy', '-c', $deployCfg, '--name', $WorkerName, '--var', "GEMINI_MODEL:$model", '--var', "ALLOWED_ORIGIN:$origin")
if ($r.Code -ne 0) { Write-Host $r.Out; Die '번역 서버 배포에 실패했어요.' }
$m = [regex]::Match($r.Out, 'https://[a-z0-9.-]+\.workers\.dev')
$workerUrl = if ($m.Success) { $m.Value } else { '' }

Say '6/6 비밀 값 등록 (Gemini 키, 접근 토큰)'
$tmp = Join-Path $env:TEMP ("trip-secrets-" + [guid]::NewGuid().ToString('N') + '.json')
try {
  $json = @{ GEMINI_API_KEY = $key; TOKENS = $token } | ConvertTo-Json -Compress
  [IO.File]::WriteAllText($tmp, $json, (New-Object Text.UTF8Encoding $false))
  $r = Run-Wr @('secret', 'bulk', $tmp, '--name', $WorkerName)
  if ($r.Code -ne 0) { Write-Host $r.Out; Die '비밀 값 등록에 실패했어요.' }
} finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }

# 폰 앱에 내 서버 주소를 미리 넣어 다시 배포한다(폰에서는 토큰만 입력하면 되도록)
if ($env:SKIP_PAGES -ne '1' -and $workerUrl) {
  [IO.File]::WriteAllText((Join-Path $Root 'field-pwa\config.json'), (@{ workerUrl = $workerUrl } | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
  $rp = Run-Wr @('pages', 'deploy', (Join-Path $Root 'field-pwa'), '--project-name', $PagesName, '--branch', 'main')
  if ($rp.Code -ne 0) { Write-Host '참고: 서버 주소를 앱에 미리 넣지 못했어요. 폰 설정에서 직접 입력해 주세요.' }
}

@{ ID = $id; WORKER_NAME = $WorkerName; PAGES_NAME = $PagesName; WORKER_URL = $workerUrl; PAGES_URL = $pagesUrl; GEMINI_MODEL = $model; KV_ID = $kvId; TOKEN = $token } |
  ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8

Write-Host @"

=====================================================
설치가 끝났어요.

  폰 앱 주소      : $(if ($pagesUrl) { $pagesUrl } else { '(건너뜀)' })
  번역 서버 주소  : $(if ($workerUrl) { $workerUrl } else { '(주소를 찾지 못했어요. Cloudflare 대시보드에서 확인하세요)' })
  접근 토큰       : $token
  모델            : $model

폰에서: 1) 아래 '설정 링크'를 폰으로 보내(카톡 나에게 보내기·메일·AirDrop) 폰에서 열면 서버 주소와 토큰이 자동 저장돼요.
        2) 그 화면에서 바로 '홈 화면에 추가'를 하세요(iPhone 은 이렇게 해야 설정이 앱에 따라가요).
  설정 링크       : $(if ($pagesUrl) { $pagesUrl } else { '(폰 앱 주소)' })/?t=$token
        ※ 이 링크는 내 비밀번호와 같아요. 나에게만 보내고, 다른 사람에게 주지 마세요.
토큰은 $StateFile 에도 저장돼 있어요.
=====================================================
"@ -ForegroundColor Green
