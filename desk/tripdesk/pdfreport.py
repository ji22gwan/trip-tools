"""일간 보고서(.md + 사진)를 PDF 로 바꾼다. 사진은 용량을 줄이려고 줄여서 넣는다. 크롬 계열 브라우저(헤드리스)를 쓰므로 추가 설치가 없다."""
import hashlib
import html
import re
import subprocess
import tempfile
from pathlib import Path

from . import daily
from .launcher import find_browser
from .store import Store, StoreError

PHOTO_PX = 560  # 한 줄 3장 기준 가로 길이. 여기까지 줄여서 PDF 에 넣는다
JPEG_Q = 0.72

CSS = """
@page{size:A4;margin:14mm}
body{font-family:"Noto Sans CJK KR","Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:10.5pt;line-height:1.55;color:#1d232b}
h1{font-size:19pt;margin:0 0 6px}h2{font-size:14pt;margin:20px 0 6px;border-bottom:1px solid #ccd;padding-bottom:3px}
h3{font-size:12pt;margin:14px 0 4px}h4{font-size:11pt;margin:12px 0 3px}
ul{margin:4px 0 8px;padding-left:20px}li{margin:1px 0}
table{border-collapse:collapse;width:100%;margin:6px 0;break-inside:avoid}th,td{border:1px solid #cfd5dc;padding:4px 7px;text-align:left;vertical-align:top;font-size:9.5pt}
table.photos{table-layout:fixed}table.photos td{border:0;text-align:center;padding:3px;width:33.3%}
img{max-width:100%;height:auto;display:block;margin:0 auto}
blockquote{margin:6px 0;padding:2px 10px;border-left:3px solid #c9a227;background:#faf6e8}
h2,h3,h4{break-after:avoid}p{margin:4px 0}
"""

# 사진을 캔버스로 줄여 JPEG 로 바꿔 넣는다(원본은 건드리지 않는다). 다 끝나면 body 에 done 표시.
SCRIPT = """
const MAXW=%d,Q=%s;
const imgs=[...document.images];
let left=imgs.length;
const fin=()=>{if(--left<=0)document.body.setAttribute('data-done','1')};
if(!left)document.body.setAttribute('data-done','1');
imgs.forEach(im=>{
  const go=()=>{try{
    const k=Math.min(1,MAXW/im.naturalWidth),c=document.createElement('canvas');
    c.width=Math.max(1,Math.round(im.naturalWidth*k));c.height=Math.max(1,Math.round(im.naturalHeight*k));
    const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.drawImage(im,0,0,c.width,c.height);
    im.src=c.toDataURL('image/jpeg',Q);
  }catch(e){}fin()};
  im.decode?im.decode().then(go,fin):(im.complete?go():im.onload=go)
});
""" % (PHOTO_PX, JPEG_Q)


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: f'<img alt="{html.escape(m.group(1))}" src="{html.escape(m.group(2))}">', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html(md: str) -> str:
    """보고서에 쓰는 Markdown 만 다룬다: 제목, 목록, 표, 인용, 굵게, 이미지. 사진 표(3열)는 보이는 테두리를 없앤다."""
    out, lines, i = [], md.splitlines(), 0
    ul = False
    def close_ul():
        nonlocal ul
        if ul:
            out.append("</ul>")
            ul = False
    while i < len(lines):
        s = lines[i].rstrip()
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            close_ul()
            head = _cells(s)
            rows, i = [], i + 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            photos = not any(head) and any("![" in c for r in rows for c in r)
            if photos:
                out.append('<table class="photos">' + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
            else:
                out.append("<table><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr>"
                           + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            close_ul()
            out.append(f"<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"^\s*[-*]\s+", s):
            if not ul:
                out.append("<ul>")
                ul = True
            item = re.sub(r"^\s*[-*]\s+", "", s)
            out.append(f"<li>{_inline(item)}</li>")
        elif s.startswith(">"):
            close_ul()
            out.append(f"<blockquote>{_inline(s.lstrip('> ').strip())}</blockquote>")
        elif s.strip() and not s.strip().startswith("<!--"):
            close_ul()
            out.append(f"<p>{_inline(s)}</p>")
        i += 1
    close_ul()
    return "".join(out)


def make_pdf(md: str, base_dir: Path, out: Path, browser: list[str] | None) -> None:
    """md 를 PDF 로 저장한다. 사진 경로는 base_dir 기준 상대 경로다."""
    if not browser:
        raise StoreError("PDF 를 만들려면 크롬(또는 엣지·크로미움)이 필요해요.")
    doc = f'<!doctype html><html lang="ko"><meta charset="utf-8"><style>{CSS}</style><body>{md_to_html(md)}<script>{SCRIPT}</script></body></html>'
    with tempfile.TemporaryDirectory() as td:
        # base_dir 안에 임시 html 을 두어야 상대 경로가 그대로 맞는다
        page = Path(td) / "r.html"
        page.write_text(doc.replace('src="', f'src="{base_dir.resolve().as_uri()}/'), encoding="utf-8")
        cmd = [*browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files", "--no-pdf-header-footer",
               f"--user-data-dir={td}/prof", "--virtual-time-budget=60000", f"--print-to-pdf={out}", page.as_uri()]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except (subprocess.SubprocessError, OSError) as e:
            raise StoreError(f"PDF 를 만들지 못했어요: {e}") from e
    if not out.is_file() or out.stat().st_size < 500:
        raise StoreError("PDF 를 만들지 못했어요.")


def day_report_pdf(store: Store, tid: str, n: int) -> bytes | None:
    """수정본(final/보고서.md)을 올린 일차의 PDF. 적어 둔 '미흡한 부분'이 본문에 없으면 끝에 붙인다.
    내용이 같으면 전에 만든 PDF 를 재사용한다. 수정본이 없거나 브라우저가 없으면 None."""
    d = daily.day_dir(store, tid, n) / "final"
    src = d / "보고서.md"
    if not src.is_file():
        return None
    browser = find_browser()
    if not browser:
        return None
    md = src.read_text(encoding="utf-8", errors="replace")
    gaps = daily.get_state(store, tid, n).get("gaps", "")
    if gaps and "미흡한 부분" not in md:
        md += f"\n\n## 오늘 미흡한 부분\n\n{gaps}\n"
    files = [f"{p.relative_to(d)}:{p.stat().st_size}" for p in sorted(d.rglob("*")) if p.is_file() and p.name not in ("report.pdf", "report.key")]
    key = hashlib.sha1("\n".join([md, *files, f"{PHOTO_PX}/{JPEG_Q}"]).encode("utf-8")).hexdigest()
    pdf, keyf = d / "report.pdf", d / "report.key"
    if not (pdf.is_file() and keyf.is_file() and keyf.read_text() == key):
        make_pdf(md, d, pdf, browser)
        keyf.write_text(key)
    return pdf.read_bytes()
