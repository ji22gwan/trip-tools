#!/usr/bin/env bash
# Markdown(출장 계획서 등)을 A4 1~2쪽 PDF 로 만든다.
# 사용: docs/manual/md2pdf.sh 파일.md [출력.pdf]     필요: pandoc, 구글 크롬/크로미움, 한글 글꼴(sudo apt install pandoc fonts-noto-cjk)
set -euo pipefail
IN="${1:?사용법: md2pdf.sh 파일.md [출력.pdf]}"
[ -f "$IN" ] || { echo "파일이 없어요: $IN" >&2; exit 1; }
OUT="${2:-${IN%.md}.pdf}"
IN_ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
HERE="$(cd "$(dirname "$0")" && pwd)"
command -v pandoc >/dev/null || { echo "pandoc 이 없어요: sudo apt install pandoc" >&2; exit 1; }
FONTS="$(fc-list 2>/dev/null || true)"
grep -qi "noto sans cjk\|nanum" <<<"$FONTS" || echo "참고: 한글 글꼴이 없어 글자가 깨질 수 있어요 (sudo apt install fonts-noto-cjk)" >&2
BROWSER=""
for b in google-chrome google-chrome-stable chromium chromium-browser; do command -v "$b" >/dev/null && { BROWSER="$b"; break; }; done
[ -n "$BROWSER" ] || { echo "크롬 또는 크로미움이 필요해요" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp "$HERE/plan-pdf.css" "$TMP/"
pandoc "$IN_ABS" -f gfm -t html5 -s --metadata title=" " -c plan-pdf.css -o "$TMP/p.html"
"$BROWSER" --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer --print-to-pdf="$OUT_ABS" "file://$TMP/p.html" >/dev/null 2>&1
[ -s "$OUT_ABS" ] || { echo "PDF 를 만들지 못했어요" >&2; exit 1; }
PAGES=""; command -v pdfinfo >/dev/null && PAGES=" · $(pdfinfo "$OUT_ABS" | awk '/^Pages:/{print $2}')쪽"
echo "만들었어요: $OUT_ABS$PAGES"
