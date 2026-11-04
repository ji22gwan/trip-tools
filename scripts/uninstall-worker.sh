#!/usr/bin/env bash
# 설치한 번역 서버(Worker)와 폰 앱(Pages)을 Cloudflare 에서 삭제한다. macOS / Ubuntu.
# 삭제 대상: Worker(비밀 값 포함), Pages 프로젝트, 로컬 설치 기록(~/.trip-tools/install.env)
# 비대화 실행: YES=1 ./uninstall-worker.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${TRIP_TOOLS_HOME:-$HOME/.trip-tools}"
STATE_FILE="$STATE_DIR/install.env"
WORKER_NAME="${WORKER_NAME:-trip-translate}"
PAGES_NAME="${PAGES_NAME:-trip-field}"
# shellcheck disable=SC1090
[ -f "$STATE_FILE" ] && . "$STATE_FILE" || true

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
command -v npm >/dev/null 2>&1 || { echo "npm 이 없어요. Node.js 를 설치해 주세요." >&2; exit 1; }

cat <<INFO
다음을 Cloudflare 에서 삭제합니다.
  - 번역 서버(Worker): $WORKER_NAME   (등록한 Gemini 키·토큰도 함께 사라져요)
  - 폰 앱(Pages 프로젝트): $PAGES_NAME
  - 로컬 설치 기록: $STATE_FILE
폰에 저장된 출장 데이터(녹음·메모)는 건드리지 않아요. 단, 앱 주소가 사라지면 그 앱은 더 열 수 없어요.
INFO
if [ "${YES:-0}" != "1" ]; then
  printf "계속하려면 '삭제' 를 입력하세요: "
  read -r ANS
  [ "$ANS" = "삭제" ] || { echo "취소했어요."; exit 0; }
fi

( cd "$ROOT/worker" && npm install --no-audit --no-fund --loglevel=error )
WR() { ( cd "$ROOT/worker" && npx --no-install wrangler "$@" ); }
if ! WR whoami >/dev/null 2>&1; then echo "Cloudflare 로그인이 필요해요."; WR login; fi

FAILED=0
say "번역 서버 삭제"
if printf 'y\n' | WR delete "$WORKER_NAME"; then echo "삭제했어요."; else echo "삭제하지 못했어요(이미 없거나 권한 문제)."; FAILED=1; fi
say "폰 앱(Pages) 삭제"
if WR pages project delete "$PAGES_NAME" --yes; then echo "삭제했어요."; else echo "삭제하지 못했어요(이미 없거나 권한 문제)."; FAILED=1; fi

[ "$FAILED" = "0" ] && rm -f "$STATE_FILE"

cat <<DONE

정리할 것이 더 있어요(자동으로 할 수 없어요):
  1. Google AI Studio 에서 이 용도로 만든 Gemini API 키를 삭제(또는 재발급)하세요.
  2. 폰 홈 화면에 추가한 Trip Field 아이콘을 지우세요.
  3. $( [ "$FAILED" = "0" ] && echo "Cloudflare 대시보드에서 남은 항목이 없는지 확인해 보세요." || echo "삭제에 실패한 항목은 Cloudflare 대시보드(Workers & Pages)에서 직접 지워 주세요." )
DONE
