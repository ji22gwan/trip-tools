"""일간·최종 보고서 만들기(화면 미리보기용 데이터, Markdown, Word)."""
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import booths, daily, pptdata
from .store import Store, StoreError

MARK_BRACES = re.compile(r"\{\{(.*?)\}\}", re.S)


def plain(text: str) -> str:
    """교정 표시({{ }})는 지우고 [확인필요] 는 그대로 둔다(보고서에 사람이 확인할 곳을 남긴다)."""
    return MARK_BRACES.sub(r"\1", text or "")


def _plan(store, tid) -> list[dict]:
    """계획표: 부스 하나가 한 줄(방문 지점)이다. 부스가 여러 곳인 업체는 줄이 여러 개가 된다."""
    out = []
    for c in store.get_companies(tid):
        if c.get("picked") is False:
            continue
        for x in booths.stops(c):
            out.append(dict(c, id=x["id"], companyId=c["id"], hall=x["hall"], booth=x["booth"], day=x["day"], multi=len(c["booths"]) > 1))
    return out


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
        g = st.get("groups", {}).get(c["id"], {})  # AI 가 내용으로 정한 분류가 있으면 그것을 쓴다
        comps_out.append({
            "id": c["id"], "name": c["name"], "category": g.get("category") or c.get("category", ""), "group": g.get("group", ""), "hall": c.get("hall", ""), "booth": c.get("booth", ""),
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
    tag = lambda c: f"{c['name']}({c['booth'] or c['hall']})" if c.get("multi") else c["name"]
    next_up = [tag(c) for c in plan if c.get("day") == n + 1]
    missed = [tag(c) for c in plan if c.get("day") == n and c["id"] not in visited_ids]
    bits = []
    if next_up:
        bits.append("방문 예정: " + ", ".join(next_up))
    if missed:
        bits.append("오늘 못 간 업체(일정 재조정): " + ", ".join(missed))
    return {
        "tripName": trip["name"], "venue": trip.get("venue", ""), "day": n, "date": v.get("date") or trip["days"][n - 1],
        "sessions": [x for x in v.get("sessions", []) if isinstance(x, dict) and x.get("title")],
        "summary": st.get("summary") or auto, "summaryIsAi": bool(st.get("summary")), "stats": summary,
        "companies": comps_out, "checks": checks,
        "tomorrow": st["tomorrow"] if st.get("tomorrow") is not None else " · ".join(bits),
        "tomorrowIsAuto": st.get("tomorrow") is None,
        "gaps": st.get("gaps", ""), "finalReport": st.get("finalReport"),
        "findings": st.get("findings", []), "tech": st.get("tech", []), "opinion": st.get("opinion", []),
    }


def _attended(days: list[dict]) -> list[dict]:
    """폰에서 '참석'으로 표시해 내보낸 세션(일간 데이터에 들어 있음)."""
    out, seen = [], set()
    for d in days:
        for x in d.get("sessions", []):
            if x.get("id") not in seen:
                seen.add(x.get("id"))
                out.append(x)
    return sorted(out, key=lambda x: (x.get("date", ""), x.get("start") or "99:99"))


def _apply_edited(store: Store, tid: str, d: dict) -> None:
    """일간 보고서에 올려 둔 수정본이 있으면, 최종 보고서는 그 내용(주요 조사 내용·업체별 개조식)을 기준으로 한다."""
    from .research import norm_name

    p = daily.day_dir(store, tid, d["day"]) / "final" / "보고서.md"
    if not p.is_file():
        return
    sec, name, found, pts = "", None, [], {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("#"):
            sec = s
            m = re.match(r"^#{3,4}\s*■\s*(.+)$", s)
            name = re.split(r"\s+·\s+|\s*\(현장 추가\)", m.group(1))[0].strip() if m else None
        elif s.startswith("- "):
            if name:
                pts.setdefault(norm_name(name), []).append(s[2:].strip())
            elif re.match(r"^##\s*\d*\.?\s*주요 조사 내용", sec):
                found.append(s[2:].strip())
    if found:
        d["summary"], d["summaryIsAi"] = " ".join(found), True
    for c in d["companies"]:
        k = norm_name(c["name"])
        hit = pts.get(k) or next((v for kk, v in pts.items() if len(k) >= 3 and len(kk) >= 3 and (k in kk or kk in k)), None)
        if hit:
            c["points"] = hit
    d["editedUsed"] = True


def build_final(store: Store, tid: str) -> dict:
    trip = store.get_trip(tid)
    days = []
    for i in range(1, len(trip["days"]) + 1):
        if daily.get_visits(store, tid, i):
            d = build_day(store, tid, i)
            _apply_edited(store, tid, d)
            days.append(d)
    merged: dict[str, dict] = {}
    for d in days:
        for c in d["companies"]:
            bid = booths.base_id(c["id"])  # 같은 업체의 다른 부스 방문은 한 업체로 합친다
            m = merged.setdefault(bid, {"id": bid, "name": c["name"], "category": c["category"], "hall": c["hall"],
                                       "booth": c["booth"], "addedOnSite": c["addedOnSite"], "visits": []})
            if c["booth"] and c["booth"] not in m["booth"].split(", "):
                m["hall"] = ", ".join(dict.fromkeys(x for x in (m["hall"] + ", " + c["hall"]).split(", ") if x))
                m["booth"] = ", ".join(x for x in (m["booth"], c["booth"]) if x)
            m["visits"].append({"day": d["day"], "date": d["date"], "points": c["points"], "memos": c["memos"],
                                "recordings": c["recordings"], "photos": len(c["photos"])})
    visited = {i for i, m in merged.items() if any(x for x in m["visits"])}
    not_visited = list(dict.fromkeys(c["name"] for c in _plan(store, tid) if booths.base_id(c["id"]) not in visited))
    final = daily._read(store._dir(tid) / "final.json", {})
    return {
        "tripName": trip["name"], "venue": trip.get("venue", ""), "purpose": trip.get("purpose", ""), "dates": trip["days"],
        "days": days, "companies": sorted(merged.values(), key=lambda m: (m["category"], m["name"])),
        "travel": _travel(store, tid, trip),
        "ppt": pptdata.load(store, tid),
        "sessions": _attended(days),
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
    from . import travel

    for f in tv["flights"]:
        d = travel.decorate(f)
        segs = f["segments"]
        amt = f" · {f['amount']:,.0f} {f['currency']}" if f.get("amount") is not None else ""
        fn = "/".join(g["flightNo"] for g in segs if g["flightNo"])
        via = f" (경유 {len(segs) - 1}회)" if len(segs) > 1 else ""
        t0, t1 = segs[0]["depart"].replace("T", " "), segs[-1]["arrive"].replace("T", " ")
        L.append(f"항공 {fn} {'→'.join(d['route'])}{via} {t0}{' → ' + t1 if t1 else ''}{amt}".replace("  ", " ").strip())
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
def _photo_table(name: str, photos: list[str], count: int) -> list[str]:
    """사진을 한 줄에 3개씩 표로 넣는다(원본은 그대로, 보기 크기는 뷰어가 칸 폭에 맞춘다)."""
    L = ["", f"**현장 사진 ({count}장)**" if count else "**현장 사진**", ""]
    if not photos:
        return L + ["<!-- 사진 삽입 -->" if not count else f"사진 {count}장", ""]
    L += ["| | | |", "| :---: | :---: | :---: |"]
    cells = [f"![{name} 사진 {i}]({p})" for i, p in enumerate(photos, 1)]
    for k in range(0, len(cells), 3):
        row = cells[k:k + 3] + [""] * (3 - len(cells[k:k + 3]))
        L.append("| " + " | ".join(row) + " |")
    return L + [""]


def day_markdown(r: dict, photos: dict | None = None) -> str:  # photos: 업체 id → ZIP 안 사진 경로 목록(없으면 장수만 적는다)
    """일간 보고서: 주요 조사 내용 → 업체 현황 → 분류별 업체(개조식 + 사진 3열) → 기술별 결과 → 종합 의견."""
    comps = r["companies"]
    cats: dict[str, list[dict]] = {}
    for c in comps:
        cats.setdefault(c.get("category") or "기타", []).append(c)
    L = [f"# {r['tripName']} · {r['day']}일차 보고서", "", f"- 일자: {r['date']}", *([f"- 장소: {r['venue']}"] if r["venue"] else []), f"- 방문 업체: {len(comps)}개사", ""]
    L += ["## 1. 주요 조사 내용", ""]
    L += [f"- {x}" for x in r.get("findings", [])] if r.get("findings") else [r["summary"]]
    L += ["", "## 2. 방문 업체 현황", "", "| 구분 | 주요 업체 | 업체 수 |", "|---|---|---:|"]
    L += [f"| {k} | {', '.join(c['name'] for c in v)} | {len(v)} |" for k, v in cats.items()]
    L += [f"| **합계** | | **{len(comps)}** |", ""]
    n = 2
    for cat, items in cats.items():
        n += 1
        L += [f"## {n}. {cat}", ""]
        sub, k = "", 0
        grouped = any(c.get("group") for c in items)
        for c in sorted(items, key=lambda c: c.get("group") or "") if grouped else items:
            if grouped and (c.get("group") or "") != sub:
                sub = c.get("group") or ""
                if sub:
                    k += 1
                    L += [f"### {n}.{k}. {sub}", ""]
            tag = " (현장 추가)" if c["addedOnSite"] else ""
            pos = f" · {c['hall']} {c['booth']}".rstrip() if c["hall"] or c["booth"] else ""
            L += [f"{'####' if sub else '###'} ■ {c['name']}{tag}{pos}", ""]
            if c["points"]:
                L += [f"- {p}" for p in c["points"]]
            else:
                for rec in c["recordings"]:
                    t = plain(rec["corrected"] or rec["text"])
                    if t:
                        L.append(f"- ({_hm(rec)} 녹음, {'교정본' if rec['corrected'] else '전사 원문'}) {t}")
            if c["memos"]:
                L += ["", "**내 메모 (원문)**", ""] + [f"> {'★ ' if m.get('important') else ''}{m['text']}" for m in c["memos"]]
            if c["photos"]:
                L += _photo_table(c["name"], (photos or {}).get(c["id"], []), len(c["photos"]))
            else:
                L.append("")
    if r.get("tech"):
        n += 1
        L += [f"## {n}. 주요 기술별 조사 결과", "", "| 조사 기술 | 관련 업체 | 주요 검토 사항 |", "|---|---|---|"]
        L += [f"| {t['tech']} | {', '.join(t['companies'])} | {t['review']} |" for t in r["tech"]] + [""]
    if r.get("opinion"):
        n += 1
        L += [f"## {n}. 종합 의견", ""]
        for k, o in enumerate(r["opinion"], 1):
            L += [f"### {n}.{k}. {o['category']}", "", *[f"- {b}" for b in o["bullets"]], ""]
    if r["tomorrow"]:
        L += ["## 내일 계획", r["tomorrow"], ""]
    if r.get("gaps"):
        L += ["## 오늘 미흡한 부분", r["gaps"], ""]
    return "\n".join(L)


def day_md_zip(store: Store, tid: str, r: dict) -> bytes:
    """Markdown 과 사진을 ZIP 으로 묶는다. 사진은 photos/ 에 넣고 본문에 상대 경로로 연결한다."""
    import zipfile
    ddir = daily.day_dir(store, tid, r["day"])
    photos: dict[str, list[str]] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for c in r["companies"]:
            for ph in c["photos"]:
                rel = str(ph.get("file", ""))
                src = ddir / rel
                if ".." in rel or not src.is_file():
                    continue
                arc = f"photos/{src.name}"
                z.write(src, arc)
                photos.setdefault(c["id"], []).append(arc)
        z.writestr("보고서.md", day_markdown(r, photos).encode("utf-8"))
    return buf.getvalue()


def session_lines(r: dict) -> list[str]:
    return [f"{x['date'][5:]} {x.get('start', '')}{('~' + x['end']) if x.get('end') else ''} · {x['title']}"
            + (f" ({x.get('place', '')}{' · 홀 ' + x['hall'] if x.get('hall') else ''})" if x.get("place") or x.get("hall") else "") + (f" — {x['speaker']}" if x.get("speaker") else "")
            for x in r.get("sessions", [])]


def final_markdown(r: dict) -> str:
    t = r["totals"]
    L = [f"# {r['tripName']} 출장 최종 보고서", f"{r['dates'][0]} ~ {r['dates'][-1]} · {r['venue']}".strip(" ·"), ""]
    if r["purpose"]:
        L += ["## 출장 목적", r["purpose"], ""]
    L += ["## 개요", f"방문 업체 {t['companies']}곳(현장 추가 {t['newCompanies']}곳), 녹음 {t['recordings']}건, 메모 {t['memos']}건, 사진 {t['photos']}장.", ""]
    tl = travel_lines(r["travel"])
    if tl:
        L += ["## 이동·숙소·비용", *[f"- {x}" for x in tl], ""]
    sl = session_lines(r)
    if sl:
        L += ["## 참관한 세션(세미나·컨퍼런스)", *[f"- {x}" for x in sl], ""]
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
    if r.get("gaps"):
        d.add_heading("오늘 미흡한 부분", 1)
        d.add_paragraph(r["gaps"])
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
    sl = session_lines(r)
    if sl:
        d.add_heading("참관한 세션(세미나·컨퍼런스)", 1)
        for x in sl:
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
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
