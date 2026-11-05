"""'PPT용 자료' ZIP(최종보고서_PPT용.md + photos/) → 사내 참관 보고서 모양 PPT 예시를 만든다.
실제로는 이 ZIP 과 요청 프롬프트(ppt_prompt.md)를 AI 에게 주면 같은 모양으로 만들어 준다. 이 스크립트는 매뉴얼 캡처용 예시 생성기다.
실행: python3 make_ppt_sample.py <PPT용.zip> <out.pptx>"""
import io, re, sys, zipfile
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from PIL import Image

OR = RGBColor(0xF3, 0x75, 0x21); OR2 = RGBColor(0xC8, 0x5A, 0x14); PALE = RGBColor(0xFA, 0xD5, 0xC8); LIGHT = RGBColor(0xFC, 0xEB, 0xE5)
GRAY = RGBColor(0xEC, 0xEC, 0xEC); INK = RGBColor(0x1A, 0x1A, 0x1A); MUTE = RGBColor(0x88, 0x88, 0x88)
FONT = "맑은 고딕"
z = zipfile.ZipFile(sys.argv[1]); md = z.read("최종보고서_PPT용.md").decode()

# ---------- md 파싱 ----------
def split(text, mark):
    parts = re.split(rf"(?m)^{mark} (.*)$", text)
    return parts[0], dict(zip(parts[1::2], parts[2::2]))
title = re.match(r"# (.*)", md).group(1).replace(" 출장 결과보고서", "")
_, sec = split(md.split("\n---\n")[0], "##")
attach = md.split("## [별첨] 업체별 자료")[1].split("\n## 확인 필요 항목")[0]
def bullets(t): return [l[2:].strip() for l in t.splitlines() if l.startswith("- ")]
def table(t):
    rows = [[c.strip() for c in l.strip("|").split("|")] for l in t.splitlines() if l.startswith("|")]
    return rows[0], rows[2:]
purpose = sec["목적"].strip()
sch_h, sch = table(sec["일정 및 참석자"])
_, fair = split(sec["박람회 개요"], "###")
conf_h, conf = table(sec["주요 확인 사항"])
aim = re.search(r"확인 목적: (.*)", sec["주요 확인 사항"]).group(1)
legend = re.search(r"※.*", sec["주요 확인 사항"]).group(0)
ins_t, conc_t = sec["시사점 및 결론"].split("### 결론")
def blocks(t):
    out = []
    for m in re.finditer(r"(?ms)^#### \d+\. (.*?)\n(.*?)(?=^####|\Z)", t): out.append((m.group(1), bullets(m.group(2))))
    return out
ins, conc = blocks(ins_t), blocks(conc_t)
comps = []
for m in re.finditer(r"(?ms)^### \d+\. (.*?)\n(.*?)(?=^### \d+\.|\Z)", attach):
    name, body = m.group(1), m.group(2)
    meta = body.splitlines()[0]
    photos = re.findall(r"!\[.*?\]\((.*?)\)", body)
    use = body.split("**시사점 및 활용처**")[1] if "**시사점 및 활용처**" in body else ""
    conf_txt = body.split("**현장에서 확인한 사항**")[1].split("**")[0] if "**현장에서 확인한 사항**" in body else ""
    memo = re.findall(r"^> (.*)$", body, re.M)
    comps.append(dict(name=name, meta=meta[2:], photos=photos, use=use, seen=bullets(conf_txt), memo=memo))

# ---------- 그리기 도우미 ----------
prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]
def tb(s, x, y, w, h, text="", size=14, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    b = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = b.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    p = tf.paragraphs[0]; p.alignment = align; r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = color
    return tf
def add_par(tf, text, size=14, bold=False, color=INK, level=0, bullet=True):
    p = tf.add_paragraph(); r = p.add_run(); r.text = ("• " if bullet and level == 0 else "– " if bullet else "") + text
    r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = color; p.level = level
    p.space_before = Pt(3)
def rect(s, x, y, w, h, fill, line=None):
    r = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h)); r.fill.solid(); r.fill.fore_color.rgb = fill
    if line: r.line.color.rgb = line; r.line.width = Pt(1.5)
    else: r.line.fill.background()
    r.shadow.inherit = False
    return r
def frame(s, page, head, sub=None):
    tb(s, 0.5, 0.15, 9, 0.4, head, 16, True, OR)
    tb(s, 0.5, 0.5, 12, 0.7, sub, 30, True, OR) if sub else None
    tb(s, 0.5, 7.02, 3, 0.3, "가상 데이터 예시 · 사외 유출 금지", 10, False, MUTE)
    tb(s, 6.3, 7.0, 0.8, 0.3, str(page), 12, False, MUTE, PP_ALIGN.CENTER)
    tb(s, 9.3, 7.0, 3.6, 0.3, "Copyright ⓒ 2026 Hanwha Ocean", 11, False, MUTE, PP_ALIGN.RIGHT)
def make_table(s, x, y, w, colw, header, rows, size=12, rowh=0.36):
    shp = s.shapes.add_table(len(rows) + 1, len(header), Inches(x), Inches(y), Inches(w), Inches(rowh * (len(rows) + 1)))
    t = shp.table
    tblPr = shp._element.graphic.graphicData.tbl.tblPr; tblPr.set("bandRow", "0"); tblPr.set("firstRow", "0")
    for i, cw in enumerate(colw): t.columns[i].width = Inches(cw)
    def cell(c, text, fill, color, bold, center):
        c.fill.solid(); c.fill.fore_color.rgb = fill; c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.margin_left = c.margin_right = Inches(0.08); c.margin_top = c.margin_bottom = Inches(0.03)
        tf = c.text_frame; tf.word_wrap = True; p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER if center else PP_ALIGN.LEFT
        r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = color
    for j, hd in enumerate(header): cell(t.cell(0, j), hd, OR, RGBColor(255, 255, 255), True, True)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row): cell(t.cell(i, j), v, PALE if i % 2 else LIGHT, INK, False, j < 3 and len(row) == 4 and j != 3 or len(row) == 4 and j == 2)
    return t

# ---------- 슬라이드 1: 목적 · 일정 · 개요 ----------
s = prs.slides.add_slide(blank); frame(s, 1, title)
tb(s, 0.5, 0.5, 5, 0.6, "목적", 28, True, OR); tb(s, 0.5, 1.1, 12.3, 0.5, purpose, 17, True)
tb(s, 0.5, 1.6, 8, 0.6, "일정 및 참석자", 28, True, OR)
make_table(s, 0.5, 2.25, 12.3, [2.4, 2.8, 4.6, 2.5], sch_h, sch, 13, 0.4)
tb(s, 0.5, 3.4, 6, 0.6, "박람회 개요", 28, True, OR)
tf = tb(s, 0.5, 3.95, 7.4, 2.9, "", 12)
for k in ("명칭", "개요", "규모", "전시관 구성 및 주제", "슬로건"):
    add_par(tf, k + ": " + " / ".join(bullets(fair[k])), 13, False, INK, bullet=True)
rect(s, 8.2, 3.5, 4.6, 3.3, GRAY); tb(s, 8.2, 4.8, 4.6, 0.6, "박람회 배치도 이미지 자리\n(별도 첨부)", 13, False, MUTE, PP_ALIGN.CENTER)

# ---------- 슬라이드 2: 주요 확인 사항 ----------
s = prs.slides.add_slide(blank); frame(s, 2, title, "주요 확인 사항")
tb(s, 0.5, 1.15, 12.3, 0.5, "1) " + aim, 16, True)
rows = [[r[0], r[1], r[2], r[3]] for r in conf]
make_table(s, 0.5, 1.8, 12.3, [1.9, 2.2, 0.9, 7.3], conf_h, rows, 12, 0.5)
tb(s, 7.5, 6.55, 5.3, 0.3, legend, 11, False, INK, PP_ALIGN.RIGHT)

# ---------- 슬라이드 3: 시사점 및 결론 ----------
s = prs.slides.add_slide(blank); frame(s, 3, title, "시사점 및 결론")
tb(s, 0.5, 1.2, 4, 0.4, "시사점", 20, True)
w = 3.0
for i, (t, pts) in enumerate(ins):
    x = 0.5 + i * (w + 0.1)
    r = rect(s, x, 1.65, w, 0.45, RGBColor(0xF6, 0xB3, 0x8C)); tb(s, x, 1.65, w, 0.45, f"{i+1}. {t}", 13, True, INK, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    rect(s, x, 2.1, w, 1.9, GRAY); tf = tb(s, x + 0.05, 2.15, w - 0.1, 1.8, "", 12)
    tf.paragraphs[0].runs[0].text = ""
    for b in pts: add_par(tf, b, 12)
tb(s, 0.5, 4.2, 4, 0.4, "결론", 20, True)
w = 4.0
for i, (t, pts) in enumerate(conc):
    x = 0.5 + i * (w + 0.15)
    rect(s, x, 4.65, w, 0.5, OR2); tb(s, x, 4.65, w, 0.5, f"{i+1}. {t}", 14, True, RGBColor(255, 255, 255), PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    rect(s, x, 5.15, w, 1.7, GRAY); tf = tb(s, x + 0.05, 5.2, w - 0.1, 1.6, "", 12)
    for b in pts: add_par(tf, b, 12)

# ---------- 별첨: 업체별 1장 ----------
for n, c in enumerate(comps, 1):
    s = prs.slides.add_slide(blank); frame(s, 3 + n, "[별첨] " + title + " 참가 업체 자료")
    group = re.search(r"구분: (.*?) ·", c["meta"]); tb(s, 0.5, 0.5, 11, 0.6, f"{n}. {c['name']}", 28, True, OR)
    tb(s, 0.5, 1.1, 12, 0.4, c["meta"], 13, False, MUTE)
    rect(s, 0.5, 1.6, 6.5, 0.5, OR); tb(s, 0.5, 1.6, 6.5, 0.5, "사진/현장 확인", 16, True, RGBColor(255, 255, 255), PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    rect(s, 0.5, 2.1, 6.5, 4.75, RGBColor(255, 255, 255), INK)
    for i, ph in enumerate(c["photos"][:4]):
        im = Image.open(io.BytesIO(z.read(ph))); ar = im.width / im.height; bw = 3.0; bh = bw / ar
        s.shapes.add_picture(io.BytesIO(z.read(ph)), Inches(0.65 + (i % 2) * 3.15), Inches(2.25 + (i // 2) * 2.3), Inches(bw), Inches(bh))
        tb(s, 0.65 + (i % 2) * 3.15, 2.25 + (i // 2) * 2.3 + bh, 3.0, 0.3, f"[사진 {i+1}] {c['name']} 부스 · 출처: 현장 촬영", 9, False, MUTE)
    tf = tb(s, 0.65, 4.95 if len(c["photos"]) > 2 else 4.3, 6.2, 1.8, "", 12)
    add_par(tf, "현장에서 확인한 사항", 13, True, INK, bullet=False)
    for b in c["seen"][:4]: add_par(tf, b, 12)
    for m_ in c["memo"][:1]: add_par(tf, "내 메모: " + m_.replace("★ ", ""), 11, False, MUTE)
    rect(s, 7.2, 1.6, 5.6, 0.5, OR); tb(s, 7.2, 1.6, 5.6, 0.5, "시사점 및 활용처", 16, True, RGBColor(255, 255, 255), PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    rect(s, 7.2, 2.1, 5.6, 4.75, RGBColor(255, 255, 255), INK); tf = tb(s, 7.3, 2.2, 5.4, 4.5, "", 13)
    lines = [l for l in c["use"].splitlines() if l.strip()]
    for l in lines:
        if l.startswith("- "): add_par(tf, l[2:], 15, True, INK)
        elif l.startswith("  - "): add_par(tf, l[4:], 13, False, INK, 1)
prs.save(sys.argv[2]); print("slides:", len(prs.slides))
