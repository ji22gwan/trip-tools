#!/usr/bin/env bash
# Trip Desk 삭제. 설치한 프로그램과 실행 아이콘만 지우고, 출장 데이터(~/TripDesk)는 물어본 뒤에만 지운다.
# 비대화 실행: YES=1 [PURGE_DATA=1] ./uninstall-desk.sh
set -euo pipefail
HOME_DIR="${TRIP_TOOLS_HOME:-$HOME/.trip-tools}"
BIN_DIR="${TRIPDESK_BIN_DIR:-$HOME/.local/bin}"
DATA="${TRIPDESK_HOME:-$HOME/TripDesk}"

if [ "${YES:-0}" != "1" ]; then
  printf "Trip Desk 프로그램을 삭제할까요? [y/N] "; read -r A
  [ "$A" = "y" ] || [ "$A" = "Y" ] || { echo "취소했어요."; exit 0; }
fi
rm -rf "$HOME_DIR/desk"
DH="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$BIN_DIR/tripdesk" "$HOME/Desktop/Trip Desk.command" "$DH/applications/tripdesk.desktop" "$DH"/icons/hicolor/*/apps/tripdesk.png
rm -rf "$HOME/Applications/Trip Desk.app"
rmdir "$HOME_DIR" 2>/dev/null || true   # 다른 설치 기록(install.env)이 남아 있으면 그대로 둔다
echo "프로그램을 삭제했어요."

if [ -d "$DATA" ]; then
  echo "출장 데이터 폴더가 남아 있어요: $DATA  (지도, 업체 목록, AI 설정과 API 키 포함)"
  if [ "${YES:-0}" = "1" ]; then ANS="${PURGE_DATA:-0}"; [ "$ANS" = "1" ] && ANS=y || ANS=n
  else printf "이 데이터도 삭제할까요? 되돌릴 수 없어요. [y/N] "; read -r ANS; fi
  if [ "$ANS" = "y" ] || [ "$ANS" = "Y" ]; then rm -rf "$DATA"; echo "데이터도 삭제했어요."; else echo "데이터는 그대로 뒀어요."; fi
fi
