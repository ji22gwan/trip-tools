#!/usr/bin/env bash
# 설치/삭제 스크립트 시험 (macOS/Ubuntu용 .sh). Cloudflare 는 가짜 npx 로 대신하고 호출 내용만 확인한다.
# Windows(.ps1)는 이 환경에서 실행해 볼 수 없어 시험에 포함하지 않는다.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/stub" "$T/home"
export LOG="$T/calls.log"; : > "$LOG"
fail() { echo "FAIL: $*"; echo "--- calls.log"; cat "$LOG"; exit 1; }
ok() { echo "ok - $*"; }

cat > "$T/stub/npm" <<'S'
#!/usr/bin/env bash
echo "npm $*" >> "$LOG"
S
cat > "$T/stub/npx" <<'S'
#!/usr/bin/env bash
echo "npx $*" >> "$LOG"
args="$*"
case "$args" in
  *"wrangler whoami"*) exit 0 ;;
  *"pages project create"*) exit 0 ;;
  *"pages project list"*) [ "${STUB_LIST_FAIL:-0}" = "1" ] && exit 1; echo 'Some banner'; echo '[{"Project Name":"trip-field","Project Domains":"trip-field.pages.dev","Git Provider":"No"},{"Project Name":"other","Project Domains":"other.pages.dev"}]'; exit 0 ;;
  *"pages deploy"*) echo "Deployment complete! Take a peek over at https://02b5b7a6.trip-field.pages.dev"; exit 0 ;;
  *"wrangler deploy"*) echo "Published trip-translate https://trip-translate.acct.workers.dev"; exit 0 ;;
  *"secret bulk"*) f="$(echo "$args" | sed -E 's/.*secret bulk ([^ ]+).*/\1/')"; cp "$f" "$LOG.secrets"; exit 0 ;;
  *"wrangler delete"*) cat > "$LOG.stdin"; exit 0 ;;
  *"pages project delete"*) exit 0 ;;
esac
exit 0
S
chmod +x "$T/stub/"*
export PATH="$T/stub:$PATH" HOME="$T/home" TRIP_TOOLS_HOME="$T/home/.trip-tools"

# ---- Worker + Pages 설치 ----
GEMINI_API_KEY="AIza-test-key" GEMINI_MODEL="" bash "$REPO/scripts/install-worker.sh" < /dev/null > "$T/out1.txt" 2>&1 || { cat "$T/out1.txt"; fail "install-worker 실패"; }
grep -q -- '--var GEMINI_MODEL:gemini-3.5-flash-lite' "$LOG" || fail "기본 모델이 전달되지 않음"
grep -q -- '--var ALLOWED_ORIGIN:https://trip-field.pages.dev$' "$LOG" || fail "Pages 고정 주소가 ALLOWED_ORIGIN 으로 들어가지 않음"
sed -n '/설치가 끝났어요/,$p' "$T/out1.txt" > "$T/summary1.txt"
grep -q 'https://trip-field.pages.dev' "$T/summary1.txt" || fail "최종 안내에 고정 주소가 없음"
grep -q '02b5b7a6' "$T/summary1.txt" && fail "최종 안내에 배포용 임시 주소가 나옴"
grep -q 'pages deploy .*field-pwa --project-name trip-field --branch main' "$LOG" || fail "Pages 배포 호출 이상"
node -e '
const s=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));
if(s.GEMINI_API_KEY!=="AIza-test-key") throw new Error("키 불일치");
if(!/^[0-9a-f]{48}$/.test(s.TOKENS)) throw new Error("토큰 형식: "+s.TOKENS);
' "$LOG.secrets" || fail "비밀 값 파일 이상"
TOKEN1="$(grep '^TOKEN=' "$TRIP_TOOLS_HOME/install.env" | cut -d'"' -f2)"
[ "$(stat -c %a "$TRIP_TOOLS_HOME/install.env" 2>/dev/null || stat -f %Lp "$TRIP_TOOLS_HOME/install.env")" = "600" ] || fail "install.env 권한이 600 이 아님"
grep -q "$TOKEN1" "$T/out1.txt" || fail "토큰이 화면에 안내되지 않음"
grep -q 'https://trip-translate.acct.workers.dev' "$T/out1.txt" || fail "Worker 주소 안내 없음"
! ls /tmp/tmp.* 2>/dev/null | grep -q secrets || true
ok "install-worker: 모델·CORS·비밀값·상태 파일"

# 재실행: 같은 토큰 유지
: > "$LOG"
GEMINI_API_KEY="AIza-test-key" bash "$REPO/scripts/install-worker.sh" < /dev/null > "$T/out2.txt" 2>&1 || fail "재실행 실패"
TOKEN2="$(grep '^TOKEN=' "$TRIP_TOOLS_HOME/install.env" | cut -d'"' -f2)"
[ "$TOKEN1" = "$TOKEN2" ] || fail "재실행 시 토큰이 바뀜"
ok "install-worker: 재실행해도 토큰 유지"

# 프로젝트 목록 조회가 실패해도 8자리 배포 코드를 떼어 고정 주소를 쓴다
: > "$LOG"
STUB_LIST_FAIL=1 GEMINI_API_KEY="AIza-test-key" bash "$REPO/scripts/install-worker.sh" < /dev/null > "$T/out2b.txt" 2>&1 || fail "목록 조회 실패 시나리오 실패"
grep -q 'ALLOWED_ORIGIN:https://trip-field.pages.dev$' "$LOG" || fail "폴백이 배포 코드를 떼지 못함"
ok "install-worker: 프로젝트 고정 주소 사용(조회 실패 시 폴백)"

# 키 없이 비대화 실행하면 친절히 실패
if env -u GEMINI_API_KEY bash "$REPO/scripts/install-worker.sh" < /dev/null > "$T/out3.txt" 2>&1; then fail "키 없이 성공해버림"; fi
ok "install-worker: 키가 없으면 실패"

# ---- Worker + Pages 삭제 ----
: > "$LOG"
bash "$REPO/scripts/uninstall-worker.sh" < <(echo "취소") > "$T/u0.txt" 2>&1 || true
grep -q "wrangler delete" "$LOG" && fail "확인 문구가 틀렸는데 삭제함"
[ -f "$TRIP_TOOLS_HOME/install.env" ] || fail "취소했는데 상태 파일이 사라짐"
ok "uninstall-worker: 확인 문구가 틀리면 아무것도 안 함"
bash "$REPO/scripts/uninstall-worker.sh" < <(echo "삭제") > "$T/u1.txt" 2>&1 || { cat "$T/u1.txt"; fail "uninstall-worker 실패"; }
grep -q 'wrangler delete trip-translate' "$LOG" || fail "Worker 삭제 호출 없음"
grep -q 'pages project delete trip-field --yes' "$LOG" || fail "Pages 삭제 호출 없음"
[ "$(cat "$LOG.stdin")" = "y" ] || fail "삭제 확인(y)이 전달되지 않음"
[ ! -f "$TRIP_TOOLS_HOME/install.env" ] || fail "삭제 후 상태 파일이 남음"
grep -q 'AI Studio' "$T/u1.txt" || fail "Gemini 키 정리 안내 없음"
ok "uninstall-worker: Worker·Pages 삭제, 기록 정리, 후속 안내"

# ---- Desk 설치 / 실행 / 삭제 (실제 venv) ----
export TRIPDESK_BIN_DIR="$T/home/bin" XDG_DATA_HOME="$T/home/share" TRIPDESK_HOME="$T/home/TripDesk"
unset PATH_STUB; export PATH="${PATH#"$T/stub:"}"   # 가짜 npm/npx 제거
# 이전에 pip 없이 만들어진 반쪽짜리 venv 가 있어도 복구돼야 한다
mkdir -p "$T/home/.trip-tools/desk/venv/bin"; printf '#!/bin/sh\nexit 1\n' > "$T/home/.trip-tools/desk/venv/bin/python"; chmod +x "$T/home/.trip-tools/desk/venv/bin/python"
bash "$REPO/scripts/install-desk.sh" > "$T/d1.txt" 2>&1 || { cat "$T/d1.txt"; fail "install-desk 실패"; }
[ -x "$TRIPDESK_BIN_DIR/tripdesk" ] || fail "실행 파일 없음"
[ -f "$XDG_DATA_HOME/applications/tripdesk.desktop" ] || [ "$(uname)" = "Darwin" ] || fail "데스크톱 항목 없음"
"$T/home/.trip-tools/desk/venv/bin/python" -c "import openpyxl, docx" || fail "openpyxl/python-docx 미설치"
"$TRIPDESK_BIN_DIR/tripdesk" --no-browser --port 0 > "$T/run.txt" 2>&1 &
PID=$!; for _ in $(seq 1 40); do grep -q "http://127.0.0.1:" "$T/run.txt" && break; sleep 0.25; done
URL="$(grep -Eo 'http://127.0.0.1:[0-9]+/' "$T/run.txt" | head -1)"
[ -n "$URL" ] || { kill $PID 2>/dev/null; fail "Desk 가 시작되지 않음: $(cat "$T/run.txt")"; }
HOSTP="${URL#http://}"
curl -s -H "Host: ${HOSTP%/}" "${URL}api/trips" | grep -q '"trips"' || { R="$(curl -s -i -H "Host: ${HOSTP%/}" "${URL}api/trips" 2>&1 | head -5)"; kill $PID; fail "Desk API 응답 없음: $URL / $R"; }
kill $PID 2>/dev/null; wait $PID 2>/dev/null || true
grep -q "Terminal=false" "$XDG_DATA_HOME/applications/tripdesk.desktop" || [ "$(uname)" = "Darwin" ] || fail "데스크톱 항목이 터미널을 띄움"
grep -q "Exec=.*tripdesk --app" "$XDG_DATA_HOME/applications/tripdesk.desktop" || [ "$(uname)" = "Darwin" ] || fail "앱 창 실행 옵션 없음"
[ -f "$XDG_DATA_HOME/icons/hicolor/256x256/apps/tripdesk.png" ] || [ "$(uname)" = "Darwin" ] || fail "아이콘 설치 안 됨"
ok "install-desk: 설치·실행·응답·아이콘"

mkdir -p "$TRIPDESK_HOME/trips"; echo x > "$TRIPDESK_HOME/settings.json"
YES=1 bash "$REPO/scripts/uninstall-desk.sh" > "$T/d2.txt" 2>&1 || fail "uninstall-desk 실패"
[ ! -d "$T/home/.trip-tools/desk" ] && [ ! -e "$TRIPDESK_BIN_DIR/tripdesk" ] || fail "프로그램이 남음"
[ -f "$TRIPDESK_HOME/settings.json" ] || fail "데이터가 기본으로 지워짐"
[ ! -e "$XDG_DATA_HOME/icons/hicolor/256x256/apps/tripdesk.png" ] || fail "아이콘이 남음"
ok "uninstall-desk: 프로그램만 삭제, 데이터는 보존"
bash "$REPO/scripts/install-desk.sh" > /dev/null 2>&1
YES=1 PURGE_DATA=1 bash "$REPO/scripts/uninstall-desk.sh" > "$T/d3.txt" 2>&1 || fail "purge 실패"
[ ! -d "$TRIPDESK_HOME" ] || fail "PURGE_DATA=1 인데 데이터가 남음"
ok "uninstall-desk: 데이터까지 삭제 옵션"
echo "ALL OK"
