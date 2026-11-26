"""PPT 제작용 최종 자료: 사내 참관 보고서 형식(목적·일정/참석자·박람회 개요·주요 확인 사항·시사점/결론·업체별 별첨)의
Markdown + 사진 ZIP 을 만든다. 이 ZIP 의 md 와 프롬프트를 AI 에게 주면 PPT 로 바꿔 준다."""
import io
import json
import re
import zipfile

from . import booths, daily
from .research import ResearchError, extract_json, norm_name
from .store import Store, StoreError

NEED = "추가 확인 필요"
LEVELS = {1: "단기 적용 가능", 2: "추가 검증 필요", 3: "중·장기 검토"}
FAIR_KEYS = (("name", "명칭"), ("summary", "개요"), ("scale", "규모"), ("halls", "전시관 구성 및 주제"), ("slogan", "슬로건"))


LABEL = re.compile(r"(^|\n)\s*(면담|조사|현장|전시|적용|확인|시사점)\s*[:：]\s*")
TERMS = {"단기": 1, "중기": 2, "장기": 3}


def nolabel(x) -> str:
    """'면담:', '조사:' 같은 구분어는 슬라이드에서 쓰지 않는다."""
    return LABEL.sub(r"\1", str(x or ""))


def _s(x, n=300) -> str:
    return re.sub(r"\s+", " ", nolabel(x)).strip()[:n]


def _lines(v, n=10) -> list[str]:
    if isinstance(v, str):
        v = v.split("\n")
    return [_s(x, 200) for x in (v or []) if _s(x, 200)][:n]


def _blocks(v, n=6) -> list[dict]:
    out = []
    for b in v or []:
        if isinstance(b, dict) and (_s(b.get("title")) or _lines(b.get("points"))):
            out.append({"title": _s(b.get("title"), 60), "points": _lines(b.get("points"), 6)})
    return out[:n]


def empty() -> dict:
    return {"attendees": "", "remark": "", "fair": {k: [] if k in ("summary", "scale", "halls", "slogan") else "" for k, _ in FAIR_KEYS},
            "insights": [], "conclusions": [], "followups": [], "companies": {}}


def clean(d: dict, base: dict | None = None) -> dict:
    """들어온 값을 정리해 base 위에 덮어쓴다(주어진 키만 바뀜)."""
    out = json.loads(json.dumps(base or empty()))
    for k in ("attendees", "remark"):
        if k in d:
            out[k] = _s(d[k])
    if isinstance(d.get("fair"), dict):
        for k, _ in FAIR_KEYS:
            if k in d["fair"]:
                out["fair"][k] = _s(d["fair"][k], 120) if k == "name" else _lines(d["fair"][k])
    for k, n in (("insights", 4), ("conclusions", 3)):
        if k in d:
            out[k] = _blocks(d[k], n)
    if "followups" in d:
        out["followups"] = [{"term": _s(f.get("term"), 4) if _s(f.get("term"), 4) in TERMS else "중기", "title": _s(f.get("title"), 80), "detail": _s(f.get("detail"), 240)}
                            for f in d["followups"] or [] if isinstance(f, dict) and _s(f.get("title"), 80)][:6]
    if isinstance(d.get("companies"), (dict, list)):
        items = d["companies"].items() if isinstance(d["companies"], dict) else [(c.get("id"), c) for c in d["companies"] if isinstance(c, dict)]
        for cid, c in items:
            if not cid or not isinstance(c, dict):
                continue
            cur = out["companies"].setdefault(str(cid), {"group": "", "level": None, "check": "", "usage": [], "summary": [], "apply": [], "diff": "", "sources": [], "tier": "", "short": "", "photos": []})
            cur.setdefault("tier", "")
            cur.setdefault("short", "")
            cur.setdefault("photos", [])
            if "tier" in c:
                cur["tier"] = c["tier"] if c["tier"] in ("core", "brief", "hide") else ""
            if "short" in c:
                cur["short"] = _s(c["short"], 40)
            if "photos" in c:
                cur["photos"] = [{"day": int(x["day"]), "file": _s(x["file"], 200)} for x in c["photos"] or []
                                 if isinstance(x, dict) and str(x.get("day", "")).isdigit() and _s(x.get("file")) and ".." not in str(x["file"])][:8]
            for k in ("summary", "apply", "sources"):
                cur.setdefault(k, [])
            cur.setdefault("diff", "")
            for k, n in (("summary", 4), ("apply", 3), ("sources", 4)):
                if k in c:
                    cur[k] = _lines(c[k], n)
            if "diff" in c:
                cur["diff"] = _s(c["diff"], 200)
            if "group" in c:
                cur["group"] = _s(c["group"], 40)
            if "level" in c:
                cur["level"] = int(c["level"]) if str(c["level"]) in ("1", "2", "3") else None
            if "check" in c:
                cur["check"] = _s(c["check"], 400)
            if "usage" in c:
                cur["usage"] = _blocks(c["usage"], 4)
    return out


def load(store: Store, tid: str) -> dict:
    raw = daily._read(store._dir(tid) / "final.json", {})
    return clean(raw.get("ppt") or {})


def save(store: Store, tid: str, patch: dict) -> dict:
    p = store._dir(tid) / "final.json"
    raw = daily._read(p, {})
    raw["ppt"] = clean(patch, clean(raw.get("ppt") or {}))
    daily._write(p, raw)
    return raw["ppt"]


# ---------------- 핵심 / 비교 업체 판정 ----------------
# shortcut: 점수 기준은 경험값(말한 양 위주), 실제 데이터를 보며 조정한다.
CORE_MIN = 12   # 이 점수 이상이면 핵심 업체 후보
CORE_MAX = 2    # 카테고리당 핵심 업체 최대 수
THIN_MAX = 3    # 이 점수 이하이면 자료 부족(웹 보완 대상)


def info_score(c: dict) -> int:
    """현장에서 얻은 정보량: 개조식 항목·메모·녹음·사진 수로 가늠한다."""
    vs = c.get("visits", [])
    pts = sum(1 for v in vs for p in v.get("points", []) if str(p).strip())
    memo = sum(len(m.get("text", "")) for v in vs for m in v.get("memos", []))
    recs = sum(len(v.get("recordings", [])) if isinstance(v.get("recordings"), list) else int(v.get("recordings") or 0) for v in vs)
    ph = sum(v.get("photos", 0) if isinstance(v.get("photos"), int) else len(v.get("photos") or []) for v in vs)
    return pts * 3 + min(memo, 600) // 40 + recs * 2 + min(ph, 6)


def tiers(r: dict, ppt: dict) -> list[dict]:
    """카테고리별로 [{category, core:[c], brief:[[c,c],...], thin:[c]}]. 핵심은 정보가 충분한 업체, 나머지는 2개씩 묶는다."""
    cats: dict[str, list] = {}
    for c in r["companies"]:
        pc = ppt["companies"].get(c["id"], {})
        if pc.get("tier") == "hide":
            continue
        cats.setdefault(pc.get("group") or c["category"] or "기타", []).append((info_score(c) + (99 if pc.get("tier") == "core" else 0), c))
    out = []
    for g, items in sorted(cats.items()):
        items.sort(key=lambda x: (-x[0], x[1]["name"]))
        pinned = [c for sc, c in items if ppt["companies"].get(c["id"], {}).get("tier") == "core"]
        forced = {c["id"] for sc, c in items if ppt["companies"].get(c["id"], {}).get("tier") == "brief"}
        auto = [c for sc, c in items if sc >= CORE_MIN and c["id"] not in forced and c not in pinned]
        core = pinned + (auto[:CORE_MAX] if not pinned else [])
        if not core and items and items[0][0] > THIN_MAX and items[0][1]["id"] not in forced:
            core = [items[0][1]]
        ids = {c["id"] for c in core}
        rest = [c for _, c in items if c["id"] not in ids]
        brief = [c for c in rest if info_score(c) > 0 or c["id"] in forced]
        thin = [c for c in rest if info_score(c) == 0 and c["id"] not in forced]
        out.append({"category": g, "core": core, "brief": [brief[i:i + 2] for i in range(0, len(brief), 2)], "thin": thin})
    return out


def tier_map(r: dict, ppt: dict) -> dict[str, str]:
    m = {}
    for t in tiers(r, ppt):
        for c in t["core"]:
            m[c["id"]] = "core"
        for pair in t["brief"]:
            for c in pair:
                m[c["id"]] = "brief"
        for c in t["thin"]:
            m[c["id"]] = "thin"
    return m


def disp(c: dict, ppt: dict) -> str:
    return ppt["companies"].get(c["id"], {}).get("short") or c["name"]


def chosen_photos(c: dict, ppt: dict, auto: list[str]) -> list[str]:
    """편집기에서 고른 사진(대표가 맨 앞). 고르지 않았으면 자동 순서."""
    sel = [f"photos/day{x['day']}_{x['file'].rsplit('/', 1)[-1]}" for x in ppt["companies"].get(c["id"], {}).get("photos", [])]
    return sel or auto


# ---------------- AI 프롬프트 / 답변 ----------------
VOICE = """Voice and viewpoint (very important):
- Write as a 20-year field engineer who also writes the control software, reporting to colleagues who build shipyard welding robots. Plain, specific, a little skeptical. Never sound like a brochure or an AI summary.
- For every company say what it would take to use it on our line (interface, SDK, I/O, calibration, cycle time, arc/fume/spatter, weight, price, lead time) and what is DIFFERENT from the technology we already know (e.g. contact touch sensing, a fixed-position laser line sensor, teach-pendant wired keys). If there is no real difference, say so honestly.
- Prefer measurable facts from the interview. Mark anything not confirmed as "검증 필요". Never invent numbers, models, prices, customers or certifications.
- Korean 개조식 (noun-ending short phrases). Do NOT start lines with labels such as "면담:", "조사:", "현장:", "전시:", "적용:"."""

WEB = """Gaps: when a company has little or no interview material (tier = thin, or a field you cannot fill), search the web. Prefer first-hand visit reports (blogs, Instagram, LinkedIn posts, YouTube by people who actually attended SPS 2026 or the same booth), then the maker's own datasheet. Put every URL you used in "sources" and prefix such lines with "(웹)" so I can tell them from what was said at the booth. Never mix web facts into interview facts without the "(웹)" mark."""


def _line(c: dict, d_pts: list[str], d_memos: list[dict], sc: int, tier: str) -> list[str]:
    pts = " / ".join(d_pts) or "(no AI points)"
    L = [f"- id={c['id']} | {c['name']} [{c['category']}] hall {c['hall']} {c['booth']} | info={sc} tier={tier}: {pts}"]
    L += [f"    my memo: {m['text']}" for m in d_memos]
    return L


def build_prompt(trip: dict, report: dict) -> str:
    from . import booths

    ppt = report.get("ppt") or empty()
    tier_of: dict[str, tuple[str, int]] = {}
    for t in tiers(report, ppt):
        for c in t["core"]:
            tier_of[c["id"]] = ("core", info_score(c))
        for pair in t["brief"]:
            for c in pair:
                tier_of[c["id"]] = ("brief", info_score(c))
        for c in t["thin"]:
            tier_of[c["id"]] = ("thin", 0)
    L = []
    for d in report["days"]:
        L.append(f"## Day {d['day']} ({d['date']})\nSummary: {d['summary']}")
        for c in d["companies"]:
            tr, sc = tier_of.get(booths.base_id(c["id"]), ("brief", 0))
            L += _line(c, c["points"], c["memos"], sc, tr)
    return f"""I visited the trade fair "{trip['name']}" ({trip['days'][0]} ~ {trip['days'][-1]}, {trip.get('venue') or 'venue unknown'}).
Purpose (Korean): {trip.get('purpose') or '(not given)'}
Below are my daily summaries and per-company notes (already corrected by me day by day). Using this material first, organize them for an internal Korean trip report that will become a PowerPoint deck.

{chr(10).join(L)}

Deck structure I want: fair overview -> company table by category -> per category: core companies get a full page each (big key photo), the other companies are paired two per page -> overall implications -> follow-up plan (short / mid / long term).
Tiers: core = plenty of interview material, put in front. brief = shown two per page. thin = hardly any material, keep it to one line unless you can fill it from the web.

{VOICE}

{WEB}

Rules:
- Do not invent numbers, prices, customers, certifications or performance. If something is not in the material (or the web), write "{NEED}".
- Restate from a shipyard (production automation) point of view, not the vendor's promotion.
- Every company needs at least one limitation or item to verify.
- Levels: 1 = short-term applicable, 2 = needs more verification, 3 = mid/long-term.

Reply with ONLY one JSON object in a ```json code block:
{{"fair":{{"name":"official fair name","summary":["1-2 lines"],"scale":["exhibitors / visitors, only if confirmed"],"halls":["hall/theme composition"],"slogan":["slogan"]}},
"companies":[{{"id":"copy the id above","group":"category group e.g. Vision & Sensor","level":1,"check":"1-2 Korean sentences: what was confirmed, from a shipyard view","summary":["core/brief: 2-3 fact bullets of what the product is and how it works"],"apply":["1-3 bullets: what it takes to use it on our line, and what to verify first"],"diff":"one sentence: what is different from the technology we already use (or 'no real difference')","sources":["urls used, only for web material"],"usage":[{{"title":"short heading","points":["bullet"]}}]}}],
"insights":[{{"title":"short heading","points":["2-3 bullets"]}}],
"conclusions":[{{"title":"short heading","points":["1-3 bullets"]}}],
"followups":[{{"term":"단기 or 중기 or 장기","title":"task","detail":"what to compare/measure and with which companies"}}]}}
Use exactly 4 insights (e.g. trend change / AI·technology / company trend / shipyard task), exactly 3 conclusions, and 3-4 followups (at least one per term). At most 3 usage headings per company."""


def apply_reply(text: str, store: Store, tid: str, known: set[str], names: dict[str, str]) -> dict:
    d = extract_json(text)
    by_name = {norm_name(n): i for i, n in names.items()}
    comps = []
    for c in d.get("companies") or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") if c.get("id") in known else by_name.get(norm_name(c.get("name", "")))
        if cid:
            comps.append({**c, "id": cid})
    patch = {"companies": comps}
    for k in ("fair", "insights", "conclusions", "followups"):
        if d.get(k):
            patch[k] = d[k]
    if not (comps or d.get("insights") or d.get("conclusions") or d.get("fair")):
        raise ResearchError("답변에서 반영할 내용을 찾지 못했어요. 프롬프트의 id 값이 그대로 들어 있는지 확인해 주세요.")
    return save(store, tid, patch)


# ---------------- Markdown / ZIP ----------------
def _bul(items, ind=""):
    return [f"{ind}- {x}" for x in items]


def _cell(s) -> str:
    return (s or "").replace("|", "/").replace("\n", " ") or NEED


def _page(c: dict, ppt: dict, photos: dict, big: bool) -> list[str]:
    """핵심 업체는 대표 사진을 크게 + 나머지 작게, 비교 업체는 중요 사진 2장."""
    from .reports import plain

    pc = ppt["companies"].get(c["id"], {})
    ph = chosen_photos(c, ppt, photos.get(c["id"], []))
    pts = [plain(p) for v in c["visits"] for p in v["points"]]
    L = ["", f"**{disp(c, ppt)}**" + (f" – {pc['check']}" if pc.get("check") else "")]
    if ph:
        L.append("사진(대표·크게): " + f"![{c['name']}]({ph[0]})")
        rest = ph[1:4] if big else ph[1:2]
        if rest:
            L.append("사진(보조·작게): " + " ".join(f"![{c['name']}]({x})" for x in rest))
    L.append("기술 요약")
    L += _bul(pc.get("summary") or pts[:3] or [NEED])
    if pc.get("diff"):
        L.append(f"- 기존 대비 차이: {pc['diff']}")
    L.append("당사 적용 및 시사점")
    L += _bul(pc.get("apply") or [NEED])
    if pc.get("sources"):
        L.append("출처: " + ", ".join(pc["sources"]))
    return L


def build_markdown(r: dict, ppt: dict, photos: dict[str, list[str]]) -> str:
    from .reports import plain

    dates = r["dates"]
    span = f"{dates[0].replace('-', '.')}~{dates[-1][5:].replace('-', '.')}" if len(dates) > 1 else dates[0].replace("-", ".")
    L = [f"# {r['tripName']} 출장 결과보고서", "", "## 목적", r["purpose"] or NEED, "",
         "## 일정 및 참석자", "| 일정 | 장소 | 출장자 | 비고 |", "|---|---|---|---|",
         f"| {span} | {_cell(r['venue'])} | {_cell(ppt['attendees'])} | {ppt['remark'] or ''} |", "", "## 박람회 개요"]
    f = ppt["fair"]
    for k, label in FAIR_KEYS:
        v = f[k]
        L.append(f"### {label}")
        if k == "name":
            L.append(f"- {v or r['tripName']}")
        else:
            L += _bul(v) if v else [f"- {NEED}"]
    ss = r.get("sessions", [])
    if ss:
        L += ["", "### 참관한 세션", "| 일시 | 세션 | 장소 | 비고 |", "|---|---|---|---|"]
        for x in ss:
            L.append(f"| {x['date'][5:]} {x.get('start', '')}{('~' + x['end']) if x.get('end') else ''} | {_cell(x['title'])} | {_cell(' · '.join(y for y in (x.get('place'), x.get('hall') and '홀 ' + x['hall']) if y))} | {x.get('speaker') or ''} |")
    L += ["", "(배치도 이미지는 별도로 첨부)", "", "## 주요 확인 사항"]
    L.append(f"확인 목적: {r['purpose'] or NEED}")
    L += ["", "| 구분 | 업체 | 수준 | 확인 사항 |", "|---|---|---|---|"]
    rows = []
    for c in r["companies"]:
        pc = ppt["companies"].get(c["id"], {})
        if pc.get("tier") == "hide":
            continue
        rows.append((pc.get("group") or c["category"] or "기타", disp(c, ppt), pc.get("level"), pc.get("check") or NEED))
    for g, n, lv, ck in sorted(rows, key=lambda x: x[0]):
        L.append(f"| {_cell(g)} | {_cell(n)} | {lv or '미정'} | {_cell(ck)} |")
    L += ["", "※ 1: 단기 적용 가능 / 2: 추가 검증 필요 / 3: 중·장기 검토", "", "## 시사점 및 결론", "### 시사점"]
    for i, b in enumerate(ppt["insights"], 1):
        L += [f"#### {i}. {b['title']}"] + _bul(b["points"])
    if not ppt["insights"]:
        L.append(f"- {NEED}")
    L += ["", "### 결론"]
    for i, b in enumerate(ppt["conclusions"], 1):
        L += [f"#### {i}. {b['title']}"] + _bul(b["points"])
    if not ppt["conclusions"]:
        L.append(f"- {NEED}")
    L += ["", "## 카테고리별 상세 (슬라이드 구성)"]
    for t in tiers(r, ppt):
        L += ["", f"### {t['category']}"]
        for c in t["core"]:
            L += _page(c, ppt, photos, big=True)
        for pair in t["brief"]:
            L += ["", "#### [비교] 1페이지에 2개 업체"]
            for c in pair:
                L += _page(c, ppt, photos, big=False)
        if t["thin"]:
            L += ["", "- 현장 자료 부족(표에만 표기): " + ", ".join(c["name"] for c in t["thin"])]
    L += ["", "## 후속 추진 방향"]
    for f in sorted(ppt.get("followups", []), key=lambda x: TERMS.get(x["term"], 2)):
        L.append(f"- **{f['term']}** {f['title']}" + (f": {f['detail']}" if f["detail"] else ""))
    if not ppt.get("followups"):
        L.append(f"- {NEED}")
    L += ["", "---", "", "## [별첨] 업체별 자료"]
    n = 0
    for c in r["companies"]:
        if ppt["companies"].get(c["id"], {}).get("tier") == "hide":
            continue
        n += 1
        pc = ppt["companies"].get(c["id"], {})
        place = " ".join(x for x in (c["hall"], c["booth"]) if x)
        L += ["", f"### {n}. {disp(c, ppt)}", f"- 구분: {pc.get('group') or c['category'] or '기타'} · 수준: {pc.get('level') or '미정'}"
              + (f" · 위치: {place}" if place else "") + (" · 현장 추가" if c["addedOnSite"] else "")]
        if photos.get(c["id"]):
            L += ["", "**사진/동영상** (파일명 기준, 원본 비율 유지)"] + [f"![{c['name']}]({p})" for p in photos[c["id"]]]
        L += ["", "**현장에서 확인한 사항**"]
        any_pt = False
        for v in c["visits"]:
            for p in v["points"]:
                L.append(f"- {nolabel(plain(p))}")
                any_pt = True
        if not any_pt:
            L.append(f"- {NEED}")
        memos = [m for v in c["visits"] for m in v["memos"]]
        if memos:
            L += ["", "**내 메모 (원문)**"] + [f"> {'★ ' if m.get('important') else ''}{m['text']}" for m in memos]
        L += ["", "**시사점 및 활용처**"]
        if pc.get("usage"):
            for b in pc["usage"]:
                L.append(f"- {b['title']}")
                L += _bul(b["points"], "  ")
        else:
            L.append(f"- {NEED}")
    return "\n".join(L) + "\n"


def build_zip(store: Store, tid: str, r: dict) -> bytes:
    ppt = load(store, tid)
    photos: dict[str, list[str]] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for d in r["days"]:
            ddir = daily.day_dir(store, tid, d["day"])
            for c in d["companies"]:
                for ph in c["photos"]:
                    rel = str(ph.get("file") or ph.get("src") or "")
                    src = ddir / rel
                    if not src.is_file() or ".." in rel:
                        continue
                    arc = f"photos/day{d['day']}_{src.name}"
                    z.write(src, arc)
                    photos.setdefault(booths.base_id(c["id"]), []).append(arc)
        md = build_markdown(r, ppt, photos)
        z.writestr("최종보고서_PPT용.md", md.encode("utf-8"))
    return buf.getvalue()
