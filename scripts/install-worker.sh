#!/usr/bin/env bash
# 번역 서버(Cloudflare Worker)와 폰 앱(Cloudflare Pages)을 내 Cloudflare 계정에 설치한다. macOS / Ubuntu.
# 다시 실행해도 안전하다(같은 토큰을 유지하고 코드만 갱신한다).
#
# 미리 준비: Node.js 18+, Cloudflare 계정(무료), Gemini API 키
# 비대화 실행용 환경변수: GEMINI_API_KEY, GEMINI_MODEL, SKIP_PAGES=1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_NAME="${WORKER_NAME:-trip-translate}"
PAGES_NAME="${PAGES_NAME:-trip-field}"
STATE_DIR="${TRIP_TOOLS_HOME:-$HOME/.trip-tools}"
STATE_FILE="$STATE_DIR/install.env"
DEFAULT_MODEL="gemini-3.5-flash-lite"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m오류: %s\033[0m\n' "$*" >&2; exit 1; }

command -v node >/dev/null 2>&1 || die "Node.js 가 없어요. https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해 주세요."
command -v npm  >/dev/null 2>&1 || die "npm 이 없어요. Node.js 를 다시 설치해 주세요."
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 18 ] || die "Node.js 18 이상이 필요해요(현재 $(node -v))."

mkdir -p "$STATE_DIR"; chmod 700 "$STATE_DIR" 2>/dev/null || true
HAD_STATE=0; [ -f "$STATE_FILE" ] && HAD_STATE=1
# shellcheck disable=SC1090
[ -f "$STATE_FILE" ] && . "$STATE_FILE" || true

# 내 ID: 서버·폰 앱 이름에 붙어 나만의 주소가 된다(trip-field-ID.pages.dev). 각자 자기 Cloudflare 계정에 설치하므로 저장공간도 사람마다 따로예요.
ID="${TRIP_ID:-${ID:-}}"
if [ -z "$ID" ] && [ "$HAD_STATE" = "0" ] && [ -t 0 ]; then
  say "내 ID 정하기"
  echo "영문 소문자·숫자·하이픈만, 2~20자 (예: ji). 이 ID 로 나만의 주소가 만들어져요."
  while :; do
    printf 'ID: '; read -r ID || true
    ID="$(printf '%s' "$ID" | tr 'A-Z' 'a-z')"
    if printf '%s' "$ID" | grep -Eq '^[a-z][a-z0-9-]{1,19}$'; then break; fi
    echo "형식이 맞지 않아요. 영문 소문자로 시작하고 영문 소문자·숫자·하이픈만 쓸 수 있어요."
  done
fi
if [ -n "$ID" ]; then
  printf '%s' "$ID" | grep -Eq '^[a-z][a-z0-9-]{1,19}$' || die "ID 형식이 맞지 않아요(영문 소문자로 시작, 영문 소문자·숫자·하이픈, 2~20자)."
  WORKER_NAME="trip-translate-$ID"; PAGES_NAME="trip-field-$ID"
fi

say "1/6 도구 설치 (wrangler)"
( cd "$ROOT/worker" && npm install --no-audit --no-fund --loglevel=error )
WR() { ( cd "$ROOT/worker" && npx --no-install wrangler "$@" ); }

say "2/6 Cloudflare 로그인 확인"
if ! WR whoami >/dev/null 2>&1; then
  echo "브라우저가 열리면 Cloudflare 계정으로 로그인하고 '허용'을 눌러 주세요."
  WR login
fi

say "3/6 Gemini 설정"
if [ -z "${GEMINI_API_KEY:-}" ]; then
  printf 'Gemini API 키를 붙여 넣고 Enter (화면에 보이지 않아요): '
  read -rs GEMINI_API_KEY; echo
fi
[ -n "$GEMINI_API_KEY" ] || die "Gemini API 키가 비어 있어요."
if [ -z "${GEMINI_MODEL:-}" ]; then
  printf '사용할 모델 ID [기본: %s]: ' "$DEFAULT_MODEL"
  read -r GEMINI_MODEL || true
fi
GEMINI_MODEL="${GEMINI_MODEL:-$DEFAULT_MODEL}"
echo "모델: $GEMINI_MODEL (바꾸려면 GEMINI_MODEL=... 환경변수로 실행)"

# 접근 토큰: 이미 만든 게 있으면 그대로 쓴다
if [ -z "${TOKEN:-}" ]; then
  if command -v openssl >/dev/null 2>&1; then TOKEN="$(openssl rand -hex 24)"
  else TOKEN="$(node -e 'process.stdout.write(require("crypto").randomBytes(24).toString("hex"))')"; fi
fi

PAGES_URL=""
if [ "${SKIP_PAGES:-0}" != "1" ]; then
  say "4/6 폰 앱 배포 (Cloudflare Pages)"
  WR pages project create "$PAGES_NAME" --production-branch main >/dev/null 2>&1 || true   # 이미 있으면 무시
  OUT="$(cd "$ROOT/worker" && npx --no-install wrangler pages deploy "$ROOT/field-pwa" --project-name "$PAGES_NAME" --branch main 2>&1)" || { echo "$OUT"; die "폰 앱 배포에 실패했어요."; }
  echo "$OUT" | tail -5
  # 배포 한 번마다 붙는 주소(8자리코드.이름.pages.dev)가 아니라 프로젝트 고정 주소(이름.pages.dev)를 쓴다.
  # 1순위: Cloudflare 에 프로젝트의 실제 주소를 물어본다 / 2순위: 출력에서 앞의 8자리 코드를 뗀다
  PAGES_URL="$(WR pages project list --json 2>/dev/null | node -e '
    const name = process.argv[1]; let t = require("fs").readFileSync(0, "utf8");
    try {
      const rows = JSON.parse(t.slice(t.indexOf("[")));
      for (const r of rows) {
        const vals = Object.values(r).map(String);
        if (!vals.includes(name)) continue;
        const doms = vals.join(",").match(/[a-z0-9-]+\.pages\.dev/g) || [];
        const d = doms.find((x) => x === name + ".pages.dev") || doms.find((x) => x.startsWith(name)) || doms[0];
        if (d) { process.stdout.write("https://" + d); break; }
      }
    } catch (e) {}
  ' "$PAGES_NAME" || true)"
  if [ -z "$PAGES_URL" ]; then
    PAGES_URL="$(echo "$OUT" | grep -Eo "https://[a-z0-9.-]+\.pages\.dev" | tail -1 | sed -E 's#^https://[0-9a-f]{8}\.#https://#' || true)"
  fi
else
  say "4/6 폰 앱 배포 건너뜀 (SKIP_PAGES=1)"
fi

say "5/6 번역 서버 배포 (Cloudflare Worker)"
ORIGIN="${PAGES_URL:-*}"
# 출장 패키지 보관함(KV). 만들지 못해도 번역은 그대로 쓸 수 있고, 패키지는 ZIP 파일로 옮기면 된다.
DEPLOY_CFG="wrangler.toml"
if [ -z "${KV_ID:-}" ]; then
  KV_OUT="$(WR kv namespace create TRIP_PACKAGES 2>&1 || true)"
  KV_ID="$(echo "$KV_OUT" | grep -Eo '[0-9a-f]{32}' | head -1 || true)"
  if [ -z "$KV_ID" ]; then   # 이미 만들어져 있으면 목록에서 찾는다
    KV_ID="$(WR kv namespace list 2>/dev/null | node -e 'let t=require("fs").readFileSync(0,"utf8");try{const r=JSON.parse(t.slice(t.indexOf("[")));const x=r.find(n=>/TRIP_PACKAGES$/.test(n.title||""));if(x)process.stdout.write(x.id)}catch(e){}' || true)"
  fi
fi
if [ -n "${KV_ID:-}" ]; then
  { cat "$ROOT/worker/wrangler.toml"; printf '\n[[kv_namespaces]]\nbinding = "PACKAGES"\nid = "%s"\n' "$KV_ID"; } > "$ROOT/worker/.deploy.toml"
  DEPLOY_CFG=".deploy.toml"
else
  echo "참고: 패키지 보관함(KV)을 만들지 못했어요. 번역은 정상이고, 출장 패키지는 ZIP 파일로 옮겨 주세요."
fi
OUT="$(cd "$ROOT/worker" && npx --no-install wrangler deploy -c "$DEPLOY_CFG" --name "$WORKER_NAME" --var "GEMINI_MODEL:$GEMINI_MODEL" --var "ALLOWED_ORIGIN:$ORIGIN" 2>&1)" || { echo "$OUT"; die "번역 서버 배포에 실패했어요."; }
echo "$OUT" | tail -5
WORKER_URL="$(echo "$OUT" | grep -Eo "https://[a-z0-9.-]+\.workers\.dev" | head -1 || true)"

say "6/6 비밀 값 등록 (Gemini 키, 접근 토큰)"
SECRETS="$(mktemp)"; trap 'rm -f "$SECRETS"' EXIT; chmod 600 "$SECRETS"
node -e 'process.stdout.write(JSON.stringify({GEMINI_API_KEY:process.argv[1],TOKENS:process.argv[2]}))' "$GEMINI_API_KEY" "$TOKEN" > "$SECRETS"
( cd "$ROOT/worker" && npx --no-install wrangler secret bulk "$SECRETS" --name "$WORKER_NAME" ) >/dev/null || die "비밀 값 등록에 실패했어요."

# 폰 앱에 내 서버 주소를 미리 넣어 다시 배포한다(폰에서는 토큰만 입력하면 되도록)
if [ "${SKIP_PAGES:-0}" != "1" ] && [ -n "$WORKER_URL" ]; then
  printf '{"workerUrl":"%s"}\n' "$WORKER_URL" > "$ROOT/field-pwa/config.json"
  ( cd "$ROOT/worker" && npx --no-install wrangler pages deploy "$ROOT/field-pwa" --project-name "$PAGES_NAME" --branch main >/dev/null 2>&1 ) || echo "참고: 서버 주소를 앱에 미리 넣지 못했어요. 폰 설정에서 직접 입력해 주세요."
fi

umask 077
cat > "$STATE_FILE" <<STATE
ID="$ID"
WORKER_NAME="$WORKER_NAME"
PAGES_NAME="$PAGES_NAME"
WORKER_URL="$WORKER_URL"
PAGES_URL="$PAGES_URL"
GEMINI_MODEL="$GEMINI_MODEL"
KV_ID="${KV_ID:-}"
TOKEN="$TOKEN"
STATE
chmod 600 "$STATE_FILE"

cat <<DONE

=====================================================
설치가 끝났어요.

  폰 앱 주소      : ${PAGES_URL:-(건너뜀)}
  번역 서버 주소  : ${WORKER_URL:-(주소를 찾지 못했어요. Cloudflare 대시보드에서 확인하세요)}
  접근 토큰       : $TOKEN
  모델            : $GEMINI_MODEL

폰에서: 아래 '설정 링크'를 폰으로 보내(카톡 나에게 보내기·메일·AirDrop) 폰에서 열면 서버 주소와 토큰이 자동으로 저장돼요.
        그 화면에서 바로 '홈 화면에 추가'를 하세요(iPhone 은 이렇게 해야 설정이 앱에 따라가요). 직접 입력하지 않아도 돼요.
  설정 링크       : ${PAGES_URL:-(폰 앱 주소)}/?t=$TOKEN
        ※ 이 링크는 내 비밀번호와 같아요. 나에게만 보내고, 다른 사람에게 주지 마세요.
출장 패키지 보관함: $( [ -n "${KV_ID:-}" ] && echo "사용 가능 (Desk 에서 바로 보내기)" || echo "만들지 못함 (ZIP 으로 옮기기)" )
토큰은 $STATE_FILE 에도 저장돼 있어요(본인만 읽을 수 있음).
번역이 느리면 번역 팝업 아래의 시간 표시를 확인하세요.
=====================================================
DONE
