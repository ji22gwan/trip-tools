#!/usr/bin/env bash
# 노트북 앱 Trip Desk 설치. macOS / Ubuntu.  ~/.trip-tools/desk 에 설치하고 실행 아이콘을 만든다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${TRIP_TOOLS_HOME:-$HOME/.trip-tools}"
DEST="$HOME_DIR/desk"
BIN_DIR="${TRIPDESK_BIN_DIR:-$HOME/.local/bin}"
LAUNCHER="$BIN_DIR/tripdesk"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31m오류: %s\033[0m\n' "$*" >&2; exit 1; }

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "Python 3.10 이상이 필요해요. Ubuntu: sudo apt install python3 python3-venv / macOS: https://www.python.org 또는 brew install python"

say "1/3 파일 복사 → $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/tripdesk"
cp -R "$ROOT/desk/tripdesk" "$DEST/tripdesk"
cp "$ROOT/desk/requirements.txt" "$ROOT/desk/requirements-whisper.txt" "$DEST/"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

say "2/3 실행 환경 만들기 (venv + openpyxl + python-docx)"
VPY="$DEST/venv/bin/python"
# 이전 시도에서 pip 없이 만들어진 반쪽짜리 venv 가 남아 있을 수 있어, pip 가 되는지 확인하고 아니면 새로 만든다
if ! { [ -x "$VPY" ] && "$VPY" -m pip --version >/dev/null 2>&1; }; then
  rm -rf "$DEST/venv"
  VENV_PKG="$("$PY" -c 'import sys; print("python%d.%d-venv" % sys.version_info[:2])')"
  "$PY" -m venv "$DEST/venv" >/dev/null 2>&1 || { rm -rf "$DEST/venv"; die "venv 를 만들 수 없어요. Ubuntu 라면: sudo apt install python3-venv $VENV_PKG  후 다시 실행하세요."; }
  "$VPY" -m pip --version >/dev/null 2>&1 || "$VPY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$VPY" -m pip --version >/dev/null 2>&1 || { rm -rf "$DEST/venv"; die "venv 에 pip 가 없어요. Ubuntu 라면: sudo apt install python3-venv python3-pip $VENV_PKG  후 다시 실행하세요."; }
fi
"$DEST/venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$DEST/requirements.txt" || die "패키지 설치에 실패했어요(인터넷 연결 확인)."

if [ "${WHISPER:-0}" = "1" ]; then
  say "   음성 인식 엔진(faster-whisper) 설치 중… 용량이 커서 몇 분 걸릴 수 있어요"
  "$DEST/venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$DEST/requirements-whisper.txt" || die "음성 인식 엔진 설치에 실패했어요(인터넷 연결 확인). WHISPER 없이 다시 실행하면 나머지 기능은 쓸 수 있어요."
fi

say "3/3 실행 아이콘 만들기"
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
cd "$DEST" && exec "$DEST/venv/bin/python" -m tripdesk "\$@"
LAUNCH
chmod +x "$LAUNCHER"

case "$(uname -s)" in
  Darwin)
    CMD="$HOME/Desktop/Trip Desk.command"
    printf '#!/usr/bin/env bash\n"%s"\n' "$LAUNCHER" > "$CMD"; chmod +x "$CMD"
    ICON_NOTE="바탕화면의 'Trip Desk.command' 를 더블클릭하세요(처음엔 우클릭 → 열기)."
    ;;
  *)
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APPS"
    cat > "$APPS/tripdesk.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Trip Desk
Comment=출장 패키지 만들기
Exec=$LAUNCHER
Terminal=true
Categories=Office;
ENTRY
    ICON_NOTE="앱 목록에서 'Trip Desk' 를 찾거나 터미널에서 tripdesk 를 실행하세요."
    ;;
esac

cat <<DONE

설치가 끝났어요.
  실행: $LAUNCHER   (또는 아이콘)
  $ICON_NOTE
  데이터 폴더: ~/TripDesk (삭제해도 이 폴더는 남겨 둬요)
DONE
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "  참고: $BIN_DIR 가 PATH 에 없어요. 'tripdesk' 명령 대신 위 전체 경로로 실행하세요." ;; esac
