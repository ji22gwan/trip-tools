"""PPT 제작용 최종 자료: 사내 참관 보고서 형식(목적·일정/참석자·박람회 개요·주요 확인 사항·시사점/결론·업체별 별첨)의
Markdown + 사진 ZIP 을 만든다. 이 ZIP 의 md 와 프롬프트를 AI 에게 주면 PPT 로 바꿔 준다."""
import io
import json
import re
import zipfile

from . import daily
from .research import ResearchError, extract_json, norm_name
from .store import Store, StoreError

NEED = "추가 확인 필요"
LEVELS = {1: "단기 적용 가능", 2: "추가 검증 필요", 3: "중·장기 검토"}
FAIR_KEYS = (("name", "명칭"), ("summary", "개요"), ("scale", "규모"), ("halls", "전시관 구성 및 주제"), ("slogan", "슬로건"))


def _s(x, n=300) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


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
            "insights": [], "conclusions": [], "companies": {}}


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
    if isinstance(d.get("companies"), (dict, list)):
        items = d["companies"].items() if isinstance(d["companies"], dict) else [(c.get("id"), c) for c in d["companies"] if isinstance(c, dict)]
        for cid, c in items:
            if not cid or not isinstance(c, dict):
                continue
            cur = out["companies"].setdefault(str(cid), {"group": "", "level": None, "check": "", "usage": []})
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


# ---------------- AI 프롬프트 / 답변 ----------------
def build_prompt(trip: dict, report: dict) -> str:
    L = []
    for d in report["days"]:
        L.append(f"## Day {d['day']} ({d['date']})\nSummary: {d['summary']}")
        for c in d["companies"]:
            pts = " / ".join(c["points"]) or "(no AI points)"
            L.append(f"- id={c['id']} | {c['name']} [{c['category']}] hall {c['hall']} {c['booth']}: {pts}")
            for m in c["memos"]:
                L.append(f"    my memo: {m['text']}")
    return f"""I visited the trade fair "{trip['name']}" ({trip['days'][0]} ~ {trip['days'][-1]}, {trip.get('venue') or 'venue unknown'}).
Purpose (Korean): {trip.get('purpose') or '(not given)'}
Below are my daily summaries and per-company notes. Using ONLY this material (you may use web search for the fair's own overview), organize them for an internal Korean trip report that will become a PowerPoint deck.

{chr(10).join(L)}

Rules:
- Do not invent numbers, prices, customers, certifications or performance. If something is not in the material, write "{NEED}".
- Write in short Korean noun-ending phrases (개조식). No promotional wording: restate from a shipyard (production automation) point of view.
- For every company include at least one limitation or item to verify.
- Levels: 1 = short-term applicable, 2 = needs more verification, 3 = mid/long-term.

Reply with ONLY one JSON object in a ```json code block:
{{"fair":{{"name":"official fair name","summary":["1-2 lines"],"scale":["exhibitors / visitors, only if confirmed"],"halls":["hall/theme composition"],"slogan":["slogan"]}},
"companies":[{{"id":"copy the id above","group":"category group e.g. 용접로봇","level":1,"check":"1-2 Korean sentences: what was confirmed, from a shipyard view","usage":[{{"title":"short heading","points":["bullet","bullet"]}}]}}],
"insights":[{{"title":"short heading","points":["2-3 bullets"]}}],
"conclusions":[{{"title":"short heading","points":["1-3 bullets"]}}]}}
Use exactly 4 insights (e.g. trend change / AI·technology / company trend / shipyard task) and exactly 3 conclusions. At most 3 usage headings per company."""


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
    for k in ("fair", "insights", "conclusions"):
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
    L += ["", "(배치도 이미지는 별도로 첨부)", "", "## 주요 확인 사항"]
    L.append(f"확인 목적: {r['purpose'] or NEED}")
    L += ["", "| 구분 | 업체 | 수준 | 확인 사항 |", "|---|---|---|---|"]
    rows = []
    for c in r["companies"]:
        pc = ppt["companies"].get(c["id"], {})
        rows.append((pc.get("group") or c["category"] or "기타", c["name"], pc.get("level"), pc.get("check") or NEED))
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
    L += ["", "---", "", "## [별첨] 업체별 자료"]
    n = 0
    for c in r["companies"]:
        n += 1
        pc = ppt["companies"].get(c["id"], {})
        place = " ".join(x for x in (c["hall"], c["booth"]) if x)
        L += ["", f"### {n}. {c['name']}", f"- 구분: {pc.get('group') or c['category'] or '기타'} · 수준: {pc.get('level') or '미정'}"
              + (f" · 위치: {place}" if place else "") + (" · 현장 추가" if c["addedOnSite"] else "")]
        if photos.get(c["id"]):
            L += ["", "**사진/동영상** (파일명 기준, 원본 비율 유지)"] + [f"![{c['name']}]({p})" for p in photos[c["id"]]]
        L += ["", "**현장에서 확인한 사항**"]
        any_pt = False
        for v in c["visits"]:
            for p in v["points"]:
                L.append(f"- {plain(p)}")
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
    if r["checks"]:
        L += ["", "## 확인 필요 항목", *[f"- {x['day']}일차 {x['company']}: {x['text']}" for x in r["checks"]]]
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
                    rel = str(ph.get("file", ""))
                    src = ddir / rel
                    if not src.is_file() or ".." in rel:
                        continue
                    arc = f"photos/day{d['day']}_{src.name}"
                    z.write(src, arc)
                    photos.setdefault(c["id"], []).append(arc)
        md = build_markdown(r, ppt, photos)
        z.writestr("최종보고서_PPT용.md", md.encode("utf-8"))
    return buf.getvalue()
