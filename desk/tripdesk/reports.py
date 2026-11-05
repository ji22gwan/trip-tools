"""일간·최종 보고서 만들기(화면 미리보기용 데이터, Markdown, Word)."""
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import daily, pptdata
from .store import Store, StoreError

MARK_BRACES = re.compile(r"\{\{(.*?)\}\}", re.S)


def plain(text: str) -> str:
    """교정 표시({{ }})는 지우고 [확인필요] 는 그대로 둔다(보고서에 사람이 확인할 곳을 남긴다)."""
    return MARK_BRACES.sub(r"\1", text or "")


def _plan(store, tid) -> list[dict]:
    return [c for c in store.get_companies(tid) if c.get("picked") is not False]


def build_day(store: Store, tid: str, n: int) -> dict:
    trip = store.get_trip(tid)
    v = daily.get_visits(store, tid, n)
    if not v:
        raise StoreError(f"{n}일차 데이터를 아직 가져오지 않았어요.")
    st = daily.get_state(store, tid, n)
    comps_out, checks = [], []
    off = v.get("tzOffsetMin")
    for c in v.get("companies", []):
        recs = []
        for r in c.get("recordings", []):
            s = st["recordings"].get(r["file"], {})
            corrected = s.get("corrected", "")
            flags = daily.check_marks(corrected)
            recs.append({"file": r["file"], "at": r.get("at", ""), "time": local_hm(r.get("at", ""), off), "durationSec": r.get("durationSec", 0),
                         "text": s.get("text", ""), "corrected": corrected, "engine": s.get("engine", ""), "flags": flags})
            checks += [{"company": c["name"], "text": f} for f in flags]
        points = st["points"].get(c["id"], [])
        for p in points:
            checks += [{"company": c["name"], "text": f} for f in daily.check_marks(p)]
        comps_out.append({
            "id": c["id"], "name": c["name"], "category": c.get("category", ""), "hall": c.get("hall", ""), "booth": c.get("booth", ""),
            "addedOnSite": bool(c.get("addedOnSite")), "visited": bool(c.get("visited")), "visitedAt": c.get("visitedAt"),
            "points": points, "recordings": recs, "photos": c.get("photos", []),
            "memos": [{**m, "time": local_hm(m.get("at", ""), off)} for m in c.get("memos", [])],
        })
    summary = daily.day_summary(store, tid, n)
    auto = (f"{summary['visited'] or summary['companies']}곳 방문" + (f"(현장 추가 {summary['newCompanies']}곳)" if summary["newCompanies"] else "")
            + f". 녹음 {summary['recordings']}건, 메모 {summary['memos']}건, 사진 {summary['photos']}장.")
    # 내일 계획: 계획표(일차 배정)에서 가져온다. 사용자가 고친 문장이 있으면 그것을 쓴다.
    visited_ids = {c["id"] for c in v.get("companies", []) if c.get("visited")}
    plan = _plan(store, tid)
    next_up = [c["name"] for c in plan if c.get("day") == n + 1]
    missed = [c["name"] for c in plan if c.get("day") == n and c["id"] not in visited_ids]
    bits = []
    if next_up:
        bits.append("방문 예정: " + ", ".join(next_up))
    if missed:
        bits.append("오늘 못 간 업체(일정 재조정): " + ", ".join(missed))
    return {
        "tripName": trip["name"], "venue": trip.get("venue", ""), "day": n, "date": v.get("date") or trip["days"][n - 1],
        "summary": st.get("summary") or auto, "summaryIsAi": bool(st.get("summary")), "stats": summary,
        "companies": comps_out, "checks": checks,
        "tomorrow": st["tomorrow"] if st.get("tomorrow") is not None else " · ".join(bits),
        "tomorrowIsAuto": st.get("tomorrow") is None,
    }


def build_final(store: Store, tid: str) -> dict:
    trip = store.get_trip(tid)
    days = []
    for i in range(1, len(trip["days"]) + 1):
        if daily.get_visits(store, tid, i):
            days.append(build_day(store, tid, i))
    merged: dict[str, dict] = {}
    for d in days:
        for c in d["companies"]:
            m = merged.setdefault(c["id"], {"id": c["id"], "name": c["name"], "category": c["category"], "hall": c["hall"],
                                           "booth": c["booth"], "addedOnSite": c["addedOnSite"], "visits": []})
            m["visits"].append({"day": d["day"], "date": d["date"], "points": c["points"], "memos": c["memos"],
                                "recordings": c["recordings"], "photos": len(c["photos"])})
    visited = {i for i, m in merged.items() if any(x for x in m["visits"])}
    not_visited = [c["name"] for c in _plan(store, tid) if c["id"] not in visited]
    final = daily._read(store._dir(tid) / "final.json", {})
    return {
        "tripName": trip["name"], "venue": trip.get("venue", ""), "purpose": trip.get("purpose", ""), "dates": trip["days"],
        "days": days, "companies": sorted(merged.values(), key=lambda m: (m["category"], m["name"])),
        "travel": _travel(store, tid, trip),
        "ppt": pptdata.load(store, tid),
        "notVisited": not_visited, "checks": [dict(x, day=d["day"]) for d in days for x in d["checks"]],
        "final": {"overview": final.get("overview", ""), "highlights": final.get("highlights", []), "followups": final.get("followups", [])},
        "totals": {k: sum(d["stats"].get(k, 0) for d in days) for k in ("recordings", "memos", "photos", "audioSeconds")}
        | {"companies": len(merged), "newCompanies": sum(1 for m in merged.values() if m["addedOnSite"]), "days": len(days)},
    }


def _travel(store: Store, tid: str, trip: dict) -> dict:
    from . import travel

    tr = travel.get(store, tid)
    return {"flights": tr["flights"], "hotels": tr["hotels"], "totals": travel.summary(tr, trip)["totals"]}


def fmt_money(totals: dict) -> str:
    return " + ".join(f"{v:,.0f} {k}" if float(v).is_integer() else f"{v:,.2f} {k}" for k, v in totals.items()) or "기록 없음"


def travel_lines(tv: dict) -> list[str]:
    """보고서에 넣을 이동·숙소·비용 줄. 기록이 없으면 빈 목록."""
    L = []
    for f in tv["flights"]:
        amt = f" · {f['amount']:,.0f} {f['currency']}" if f.get("amount") is not None else ""
        L.append(f"항공 {f['flightNo']} {f['airline']} {f['from']}→{f['to']} {f['depart'].replace('T', ' ')}{amt}".replace("  ", " ").strip())
    for x in tv["hotels"]:
        amt = f" · {x['amount']:,.0f} {x['currency']}" if x.get("amount") is not None else ""
        L.append(f"숙소 {x['name']} {x['checkIn']}~{x['checkOut']}{amt}".strip())
    if L and tv["totals"]:
        L.append("합계 " + fmt_money(tv["totals"]))
    return L


def local_hm(iso: str, offset_min) -> str:
    """폰이 기록한 UTC 시각을 폰이 있던 곳의 시각(HH:MM)으로. 오프셋 기록이 없는 예전 파일은 UTC 로 표시한다."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if offset_min is None:
        return t.astimezone(timezone.utc).strftime("%H:%M") + " UTC"
    return t.astimezone(timezone(timedelta(minutes=int(offset_min)))).strftime("%H:%M")


def _hm(x) -> str:
    return x["time"] if isinstance(x, dict) else ""


# ---------------- Markdown ----------------
def day_markdown(r: dict) -> str:
    L = [f"# {r['tripName']} · {r['day']}일차 보고서", f"{r['date']} · {r['venue']}".strip(" ·"), "", "## 오늘 요약", r["summary"], ""]
    for c in r["companies"]:
        tag = " (현장 추가)" if c["addedOnSite"] else ""
        L.append(f"## {c['name']}{tag} · {c['category']}" + (f" · {c['hall']} {c['booth']}".rstrip() if c["hall"] or c["booth"] else ""))
        if c["points"]:
            L += [f"- {p}" for p in c["points"]]
        else:
            for rec in c["recordings"]:
                t = plain(rec["corrected"] or rec["text"])
                if t:
                    L.append(f"- ({_hm(rec)} 녹음, {'교정본' if rec['corrected'] else '전사 원문'}) {t}")
        if c["memos"]:
            L += ["", "**내 메모 (원문)**"] + [f"> {'★ ' if m.get('important') else ''}{m['text']}" for m in c["memos"]]
        if c["photos"]:
            L.append(f"\n사진 {len(c['photos'])}장")
        L.append("")
    if r["tomorrow"]:
        L += ["## 내일 계획", r["tomorrow"], ""]
    if r["checks"]:
        L += ["## 확인 필요", *[f"- {x['company']}: {x['text']}" for x in r["checks"]], ""]
    return "\n".join(L)


def final_markdown(r: dict) -> str:
    t = r["totals"]
    L = [f"# {r['tripName']} 출장 최종 보고서", f"{r['dates'][0]} ~ {r['dates'][-1]} · {r['venue']}".strip(" ·"), ""]
    if r["purpose"]:
        L += ["## 출장 목적", r["purpose"], ""]
    L += ["## 개요", f"방문 업체 {t['companies']}곳(현장 추가 {t['newCompanies']}곳), 녹음 {t['recordings']}건, 메모 {t['memos']}건, 사진 {t['photos']}장.", ""]
    tl = travel_lines(r["travel"])
    if tl:
        L += ["## 이동·숙소·비용", *[f"- {x}" for x in tl], ""]
    f = r["final"]
    if f["overview"]:
        L += ["## 총평", f["overview"], ""]
    if f["highlights"]:
        L += ["## 주요 발견", *[f"- {x}" for x in f["highlights"]], ""]
    if f["followups"]:
        L += ["## 후속 조치", *[f"- {x}" for x in f["followups"]], ""]
    L.append("## 일자별 요약")
    for d in r["days"]:
        L += [f"### {d['day']}일차 · {d['date']}", d["summary"], ""]
    L.append("## 업체별 정리")
    for c in r["companies"]:
        L.append(f"### {c['name']} · {c['category']}")
        for v in c["visits"]:
            L.append(f"**{v['day']}일차**")
            for p in v["points"]:
                L.append(f"- {p}")
            for m in v["memos"]:
                L.append(f"> 메모: {m['text']}")
        L.append("")
    if r["notVisited"]:
        L += ["## 방문하지 못한 계획 업체", ", ".join(r["notVisited"]), ""]
    if r["checks"]:
        L += ["## 확인 필요 항목", *[f"- {x['day']}일차 {x['company']}: {x['text']}" for x in r["checks"]], ""]
    return "\n".join(L)


# ---------------- Word ----------------
def _docx():
    try:
        import docx
        from docx.shared import Cm, Pt, RGBColor
    except ImportError as e:
        raise StoreError("Word 파일을 만들려면 python-docx 가 필요해요. install-desk 를 다시 실행하거나, Markdown 으로 저장해 주세요.") from e
    return docx, Cm, Pt, RGBColor


def _new_doc(title: str, sub: str):
    docx, Cm, Pt, RGBColor = _docx()
    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name = "Malgun Gothic"
    st.font.size = Pt(10.5)
    d.add_heading(title, 0)
    if sub:
        p = d.add_paragraph(sub)
        p.runs[0].font.color.rgb = RGBColor(0x4A, 0x56, 0x68)
    return d


def _marked(par, text: str):
    """[확인필요: …] 는 주황 굵게 보이게 한다."""
    _, _, _, RGBColor = _docx()
    pos = 0
    for m in daily.CHECK_RE.finditer(text):
        if m.start() > pos:
            par.add_run(text[pos:m.start()])
        run = par.add_run(m.group(0))
        run.bold = True
        run.font.color.rgb = RGBColor(0xC2, 0x41, 0x0C)
        pos = m.end()
    if pos < len(text):
        par.add_run(text[pos:])


def _photos(d, store, tid, n, photos):
    _, Cm, _, _ = _docx()
    par = d.add_paragraph()
    for ph in photos:
        if not re.search(r"\.(jpe?g|png)$", ph["file"], re.I):
            continue  # HEIC/WebP 등은 Word 에 넣지 못한다
        try:
            p = daily.file_path(store, tid, n, ph["file"])
            par.add_run().add_picture(str(p), width=Cm(5.2))
            par.add_run("  ")
        except (StoreError, Exception):  # noqa: BLE001 - 사진 하나가 깨져도 보고서는 만든다
            continue


def day_docx(store: Store, tid: str, r: dict, with_photos: bool = True) -> bytes:
    d = _new_doc(f"{r['tripName']} · {r['day']}일차 보고서", f"{r['date']} · {r['venue']}")
    d.add_heading("오늘 요약", 1)
    _marked(d.add_paragraph(), r["summary"])
    for c in r["companies"]:
        head = c["name"] + (" (현장 추가)" if c["addedOnSite"] else "")
        d.add_heading(head + (f" · {c['category']}" if c["category"] else ""), 2)
        if c["hall"] or c["booth"]:
            d.add_paragraph(f"위치: {c['hall']} {c['booth']}".strip())
        if c["points"]:
            for p in c["points"]:
                _marked(d.add_paragraph(style="List Bullet"), p)
        else:
            for rec in c["recordings"]:
                t = plain(rec["corrected"] or rec["text"])
                if t:
                    _marked(d.add_paragraph(style="List Bullet"), f"({_hm(rec)} 녹음, {'교정본' if rec['corrected'] else '전사 원문'}) {t}")
        if c["memos"]:
            d.add_paragraph().add_run("내 메모 (원문 그대로)").bold = True
            for m in c["memos"]:
                d.add_paragraph(("★ " if m.get("important") else "") + m["text"], style="Intense Quote")
        if with_photos and c["photos"]:
            _photos(d, store, tid, r["day"], c["photos"])
    if r["tomorrow"]:
        d.add_heading("내일 계획", 1)
        d.add_paragraph(r["tomorrow"])
    if r["checks"]:
        d.add_heading("확인 필요", 1)
        for x in r["checks"]:
            d.add_paragraph(f"{x['company']}: {x['text']}", style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def final_docx(store: Store, tid: str, r: dict) -> bytes:
    t = r["totals"]
    d = _new_doc(f"{r['tripName']} 출장 최종 보고서", f"{r['dates'][0]} ~ {r['dates'][-1]} · {r['venue']}")
    if r["purpose"]:
        d.add_heading("출장 목적", 1)
        d.add_paragraph(r["purpose"])
    d.add_heading("개요", 1)
    d.add_paragraph(f"방문 업체 {t['companies']}곳(현장 추가 {t['newCompanies']}곳), 녹음 {t['recordings']}건, 메모 {t['memos']}건, 사진 {t['photos']}장.")
    tl = travel_lines(r["travel"])
    if tl:
        d.add_heading("이동·숙소·비용", 1)
        for x in tl:
            d.add_paragraph(x, style="List Bullet")
    f = r["final"]
    for title, body in (("총평", f["overview"]),):
        if body:
            d.add_heading(title, 1)
            _marked(d.add_paragraph(), body)
    for title, items in (("주요 발견", f["highlights"]), ("후속 조치", f["followups"])):
        if items:
            d.add_heading(title, 1)
            for x in items:
                _marked(d.add_paragraph(style="List Bullet"), x)
    d.add_heading("일자별 요약", 1)
    for day in r["days"]:
        d.add_heading(f"{day['day']}일차 · {day['date']}", 2)
        _marked(d.add_paragraph(), day["summary"])
    d.add_heading("업체별 정리", 1)
    for c in r["companies"]:
        d.add_heading(f"{c['name']} · {c['category']}", 2)
        for v in c["visits"]:
            d.add_paragraph().add_run(f"{v['day']}일차").bold = True
            for p in v["points"]:
                _marked(d.add_paragraph(style="List Bullet"), p)
            for m in v["memos"]:
                d.add_paragraph("메모: " + m["text"], style="Intense Quote")
    if r["notVisited"]:
        d.add_heading("방문하지 못한 계획 업체", 1)
        d.add_paragraph(", ".join(r["notVisited"]))
    if r["checks"]:
        d.add_heading("확인 필요 항목", 1)
        for x in r["checks"]:
            d.add_paragraph(f"{x['day']}일차 {x['company']}: {x['text']}", style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
