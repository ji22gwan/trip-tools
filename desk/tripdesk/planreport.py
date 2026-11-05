"""출장 계획서(사전 보고서): 출장 정보 · 목표 및 예상 결과 · 방문 후보 업체(선별 사유 포함)를 Markdown 으로 만든다.
1~2쪽 PDF 로 바꿔 쓰는 것을 전제로 짧게 만든다(docs/manual/md2pdf.sh)."""
from datetime import date

from . import booths, travel
from .store import Store

WD = "월화수목금토일"


def _lines(v) -> list[str]:
    if isinstance(v, str):
        v = v.splitlines()
    return [str(x).strip(" -•\t") for x in (v or []) if str(x).strip(" -•\t")][:12]


def load(store: Store, tid: str) -> dict:
    d = store._read(store._dir(tid) / "plan.json", {})
    return {"goals": _lines(d.get("goals")), "expected": _lines(d.get("expected"))}


def save(store: Store, tid: str, data: dict) -> dict:
    cur = load(store, tid)
    for k in ("goals", "expected"):
        if k in data:
            cur[k] = _lines(data[k])
    store._write(store._dir(tid) / "plan.json", cur)
    return cur


def _picked(store: Store, tid: str) -> list[dict]:
    return [c for c in store.get_companies(tid) if c.get("picked") is not False]


def defaults(store: Store, tid: str) -> dict:
    """저장된 값이 없을 때 보여 줄 초안. 출장 목적에서 목표를, 선택한 업체에서 예상 결과를 만든다(수정해서 저장하면 그 내용이 쓰인다)."""
    trip = store.get_trip(tid)
    cs = _picked(store, tid)
    cats: dict[str, int] = {}
    for c in cs:
        cats[c.get("category") or "기타"] = cats.get(c.get("category") or "기타", 0) + 1
    top = ", ".join(k for k, _ in sorted(cats.items(), key=lambda x: -x[1])[:3])
    goals = _lines(trip.get("purpose") or "") or ["(출장 목표를 적어 주세요)"]
    expected = []
    if cs:
        expected.append(f"{top} 분야 {len(cs)}개 업체의 제품·기술 현황과 적용 사례 파악" if top else f"{len(cs)}개 업체의 제품·기술 현황 파악")
    expected += ["업체별 확인 질문에 대한 답변과 담당자 연락처 확보", "출장 종료 후 최종 보고서(PPT)로 정리해 공유"]
    return {"goals": goals, "expected": expected}


def view(store: Store, tid: str) -> dict:
    cur, dft = load(store, tid), defaults(store, tid)
    return {"goals": cur["goals"], "expected": cur["expected"], "defaults": dft, "saved": bool(cur["goals"] or cur["expected"])}


def _cell(s: str) -> str:
    return str(s or "").replace("|", "/").replace("\n", " ").strip()


def _fmt_day(d: str) -> str:
    try:
        y = date.fromisoformat(d)
        return f"{y.month}/{y.day}({WD[y.weekday()]})"
    except ValueError:
        return d


def build_markdown(store: Store, tid: str) -> str:
    trip = store.get_trip(tid)
    cur, dft = load(store, tid), defaults(store, tid)
    goals, expected = cur["goals"] or dft["goals"], cur["expected"] or dft["expected"]
    days = trip.get("days") or []
    cs = _picked(store, tid)
    stops_n = sum(len(booths.stops(c)) for c in cs)
    L = [f"# {trip['name']} 출장 계획서", "", f"작성일 {date.today().isoformat()}", "", "## 1. 출장 정보", "", "| 항목 | 내용 |", "|---|---|",
         f"| 행사 | {_cell(trip['name'])} |", f"| 장소 | {_cell(trip.get('venue')) or '-'} |"]
    if days:
        L.append(f"| 기간 | {days[0]} ~ {days[-1]} ({len(days)}일) |")
    if trip.get("siteUrl"):
        L.append(f"| 공식 사이트 | {_cell(trip['siteUrl'])} |")
    tr = travel.get(store, tid)
    for f in tr["flights"]:
        d = travel.decorate(f)
        segs = f["segments"]
        t0 = segs[0]["depart"].replace("T", " ")
        via = f" (경유 {len(segs) - 1}회)" if len(segs) > 1 else ""
        L.append(f"| {'가는 편' if f['direction'] == 'outbound' else '오는 편' if f['direction'] == 'return' else '항공'} | {' → '.join(d['route'])}{via} · {t0} 출발 |")
    for x in tr["hotels"]:
        L.append(f"| 숙소 | {_cell(x['name'])}{' ' + str(x['stars']) + '성' if x.get('stars') else ''} · {x['checkIn']} ~ {x['checkOut']} |")
    L += ["", "## 2. 출장 목표 및 예상 결과", "", "**목표**", ""] + [f"- {g}" for g in goals] + ["", "**예상 결과**", ""] + [f"- {e}" for e in expected]
    L += ["", f"## 3. 방문 후보 업체 ({len(cs)}곳" + (f", 방문 지점 {stops_n}곳" if stops_n > len(cs) else "") + ")", ""]
    if not cs:
        L.append("선택한 업체가 아직 없어요.")
        return "\n".join(L) + "\n"
    L += ["| 방문일 | 업체 | 분류 | 홀 · 부스 | 선별 사유 |", "|---|---|---|---|---|"]

    def key(c):
        ds = [b["day"] or 99 for b in c["booths"]]
        return (min(ds), c["booths"][0]["hall"], c["name"])

    for c in sorted(cs, key=key):
        bl = c["booths"]
        day = "<br>".join(f"D{b['day']} {_fmt_day(days[b['day'] - 1])}" if b["day"] and b["day"] <= len(days) else "미정" for b in bl)
        loc = "<br>".join(" · ".join(x for x in (b["hall"], b["booth"]) if x) or "미확인" for b in bl)
        why = _cell(c.get("reason") or (c.get("preNotes") or "").split("\n")[0])[:170]
        mark = " ✓" if c.get("source") == "ai" and c.get("verified") else ""
        L.append(f"| {day} | **{_cell(c['name'])}**{mark} | {_cell(c.get('category') or '기타')} | {loc} | {why} |")
    ai = [c for c in cs if c.get("source") == "ai"]
    notes = ["부스가 여러 곳인 업체는 한 줄에 부스를 나란히 적었고, 방문일은 부스별로 정했습니다."] if stops_n > len(cs) else []
    if ai:
        notes.append("✓ = 공식 사이트에서 이번 전시회 참가를 확인한 업체")
    if notes:
        L += [""] + [f"*{n}*" for n in notes]
    return "\n".join(L) + "\n"
