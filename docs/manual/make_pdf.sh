#!/usr/bin/env bash
# 매뉴얼(MANUAL.md)을 PDF 로 만든다.
# 사용: docs/manual/make_pdf.sh [출력 파일 또는 폴더]   (기본: 현재 폴더의 Trip-Tools-매뉴얼.pdf)
# 필요: pandoc, 구글 크롬/크로미움, 한글 글꼴   →  sudo apt install pandoc fonts-noto-cjk
set -euo pipefail
NAME="Trip-Tools-매뉴얼.pdf"
OUT="${1:-$NAME}"
[ -d "$OUT" ] && OUT="${OUT%/}/$NAME"                       # 폴더를 주면 그 안에 만든다
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"  # 실행 위치 기준으로 미리 절대경로화
cd "$(dirname "$0")"

command -v pandoc >/dev/null || { echo "pandoc 이 없어요: sudo apt install pandoc" >&2; exit 1; }
FONTS="$(fc-list 2>/dev/null || true)"
grep -qi "noto sans cjk\|nanum" <<<"$FONTS" || echo "참고: 한글 글꼴이 없어 글자가 깨질 수 있어요 (sudo apt install fonts-noto-cjk)" >&2
BROWSER=""
for b in google-chrome google-chrome-stable chromium chromium-browser; do command -v "$b" >/dev/null && { BROWSER="$b"; break; }; done
[ -n "$BROWSER" ] || { echo "크롬 또는 크로미움이 필요해요 (google-chrome / chromium)" >&2; exit 1; }

# 그림을 상대경로로 읽도록 HTML 을 이 폴더에 잠깐 만든다 (pandoc 구버전에서도 동작)
HTML=".manual-tmp.html"; trap 'rm -f "$HTML"' EXIT
pandoc MANUAL.md -f gfm -t html5 -s --metadata title="Trip Tools 사용 매뉴얼" -c pdf.css -o "$HTML"
"$BROWSER" --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer --print-to-pdf="$OUT_ABS" "file://$PWD/$HTML" >/dev/null 2>&1
[ -s "$OUT_ABS" ] || { echo "PDF 를 만들지 못했어요" >&2; exit 1; }
echo "만들었어요: $OUT_ABS ($(du -h "$OUT_ABS" | cut -f1))"
