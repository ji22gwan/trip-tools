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
cp "$ROOT/desk/requirements.txt" "$ROOT/desk/requirements-whisper.txt" "$ROOT/desk/requirements-qt.txt" "$DEST/"
rm -rf "$DEST/assets"; cp -R "$ROOT/desk/assets" "$DEST/assets"
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

if [ "${QT:-0}" = "1" ]; then
  say "   전용 창(PyQt6 WebEngine) 설치 중… 용량이 커서(약 500MB) 몇 분 걸릴 수 있어요"
  "$DEST/venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$DEST/requirements-qt.txt" || die "전용 창 설치에 실패했어요(인터넷 연결 확인). QT 없이 다시 실행하면 크롬 앱 창으로 쓸 수 있어요."
  if [ "$(uname -s)" = "Linux" ] && ! ldconfig -p 2>/dev/null | grep -q libxcb-cursor; then
    QT_NOTE="※ Ubuntu 에서는 전용 창에 라이브러리가 하나 더 필요해요:  sudo apt install libxcb-cursor0   (설치 전에는 자동으로 크롬 앱 창으로 떠요)"
  fi
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
    # 터미널 없이 뜨는 앱: ~/Applications/Trip Desk.app (아이콘 포함). 직접 실행해 보지 못한 부분이라 안 되면 알려 주세요.
    APP="$HOME/Applications/Trip Desk.app"
    rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
    cp "$DEST/assets/icon.icns" "$APP/Contents/Resources/icon.icns"
    printf '#!/usr/bin/env bash\nexec "%s" --app\n' "$LAUNCHER" > "$APP/Contents/MacOS/TripDesk"; chmod +x "$APP/Contents/MacOS/TripDesk"
    cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Trip Desk</string>
<key>CFBundleExecutable</key><string>TripDesk</string>
<key>CFBundleIdentifier</key><string>local.tripdesk</string>
<key>CFBundleIconFile</key><string>icon</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
    ICON_NOTE="'응용 프로그램' 옆 ~/Applications 의 'Trip Desk' 를 실행하세요(처음엔 우클릭 → 열기). Dock 에 끌어다 두면 편해요."
    ;;
  *)
    DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
    APPS="$DATA_HOME/applications"
    mkdir -p "$APPS"
    for sz in 48 128 256; do
      mkdir -p "$DATA_HOME/icons/hicolor/${sz}x${sz}/apps"
      cp "$DEST/assets/icon-$sz.png" "$DATA_HOME/icons/hicolor/${sz}x${sz}/apps/tripdesk.png"
    done
    cat > "$APPS/tripdesk.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Trip Desk
GenericName=출장 데이터 정리
Comment=출장 준비부터 보고서까지
Exec=$LAUNCHER --app
Icon=tripdesk
Terminal=false
StartupWMClass=tripdesk
Categories=Office;
ENTRY
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
    ICON_NOTE="앱 목록(Super 키 → 'Trip Desk')에서 실행하세요. 창을 닫으면 프로그램도 같이 꺼져요. 즐겨찾기(Dock)에 고정해 두면 편해요."
    ;;
esac

cat <<DONE

설치가 끝났어요.
  실행: 아이콘을 누르면 앱 창으로 떠요(터미널 없음). 문제가 생기면 ~/TripDesk/tripdesk.log 를 보세요.
  $ICON_NOTE
  ${QT_NOTE:-}
  데이터 폴더: ~/TripDesk (삭제해도 이 폴더는 남겨 둬요)
DONE
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "  참고: $BIN_DIR 가 PATH 에 없어요. 'tripdesk' 명령 대신 위 전체 경로로 실행하세요." ;; esac
