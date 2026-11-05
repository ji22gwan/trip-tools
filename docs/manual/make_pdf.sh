#!/usr/bin/env bash
# 매뉴얼(MANUAL.md)을 PDF 로 만든다.  사용: docs/manual/make_pdf.sh [출력파일]   (기본: Trip-Tools-매뉴얼.pdf)
# 필요: pandoc, 구글 크롬 또는 크롬계 브라우저, 한글 글꼴(fonts-noto-cjk)
#   sudo apt install pandoc fonts-noto-cjk
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-Trip-Tools-매뉴얼.pdf}"
command -v pandoc >/dev/null || { echo "pandoc 이 없어요: sudo apt install pandoc" >&2; exit 1; }
fc-list | grep -qi "noto sans cjk\|nanum" || echo "참고: 한글 글꼴이 없어 글자가 깨질 수 있어요 (sudo apt install fonts-noto-cjk)" >&2
BROWSER=""
for b in google-chrome google-chrome-stable chromium chromium-browser; do command -v "$b" >/dev/null && { BROWSER="$b"; break; }; done
[ -n "$BROWSER" ] || { echo "크롬 또는 크롬계 브라우저가 필요해요 (google-chrome / chromium)" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pandoc MANUAL.md -f gfm -t html5 -s --embed-resources --metadata title="Trip Tools 사용 매뉴얼" -c pdf.css -o "$TMP/manual.html"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
"$BROWSER" --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer --print-to-pdf="$OUT_ABS" "file://$TMP/manual.html" >/dev/null 2>&1
[ -s "$OUT_ABS" ] || { echo "PDF 를 만들지 못했어요" >&2; exit 1; }
echo "만들었어요: $OUT_ABS ($(du -h "$OUT_ABS" | cut -f1))"
