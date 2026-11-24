"""폰 앱(Trip Field)이 읽는 출장 패키지 ZIP 만들기."""
import io
import json
import re
import zipfile
from pathlib import Path

from . import SCHEMA_VERSION, research, sessions as sess
from . import booths, daily, local, pdfreport, travel
from .launcher import find_browser
from .store import Store, StoreError, hall_key


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return s[:40] or "trip"


def picked(companies: list[dict]) -> list[dict]:
    """패키지에 들어갈 업체: 후보로만 있는(picked=False) 것은 빼고, 직접 만들거나 가져온 것은 넣는다."""
    return [c for c in companies if c.get("picked") is not False]


def _bookings(store, trip_id) -> dict:
    """폰에 보여 줄 항공·숙소 기록 (후보 목록은 제외)."""
    tr = travel.get(store, trip_id)
    return {"flights": [travel.decorate(f) for f in tr["flights"]], "hotels": tr["hotels"]}


def _local(store, trip_id) -> dict:
    """폰에 보여 줄 식사 장소·현지 교통(읽기 전용). 즐겨찾기를 앞에 둔다."""
    d = local.get(store, trip_id)
    t = local.targets(store, trip_id)
    names = {a["ref"]: f"{a['code']} 공항 경유" for a in t["airports"]} | {h["ref"]: f"{h['name']} 주변" for h in t["hotels"]} | {"venue": f"행사장({t['venue']['name']})"}
    ctx = {a["ref"]: f"{a['code']} Airport" for a in t["airports"]} | {h["ref"]: h["address"] or h["name"] for h in t["hotels"]} | {"venue": t["venue"]["name"]}
    # mapQuery: 구글 지도가 가게를 정확히 찾도록 '가게 이름 + 근처 기준점(숙소 주소·공항·행사장)'만 쓴다
    meals = [dict(m, group=names.get(m["ref"]) or m["area"] or "기타", mapQuery=f"{m['name']}, {ctx.get(m['ref'], m['area'])}".strip(", ")) for m in d["meals"]]
    meals.sort(key=lambda m: not m["fav"])
    return {"meals": meals, "routes": sorted(d["routes"], key=lambda r: not r["fav"]), "passes": d["passes"], "foods": d["foods"], "notes": d["notes"]}


def check(store: Store, trip_id: str) -> list[str]:
    """만들기 전에 사용자에게 알려줄 점검 사항."""
    warns = []
    if not store.list_maps(trip_id):
        warns.append("전시장 지도가 아직 없어요. 지도 없이도 만들 수 있지만 폰에서 따로 불러와야 해요.")
    if store.render_state(trip_id)["needed"]:
        warns.append("대표 지도(PDF)를 폰용 이미지로 아직 바꾸지 않았어요. 이대로 보내면 폰에서 변환하느라 불러오기가 오래 걸려요. '패키지 확정' 창에서 자동으로 바꿔 줘요.")
    if len(store.list_maps(trip_id)) > 1:
        warns.append(f"지도가 여러 장이에요. 패키지에는 대표 지도 '{store.primary_map(trip_id).name}' 1장만 들어가요.")
    cs = picked(store.get_companies(trip_id))
    pins = store.get_trip(trip_id).get("hallPins", {})
    stops = [x for c in cs for x in booths.stops(c)]
    missing = sorted({hall_key(x["hall"]) for x in stops if hall_key(x.get("hall")) and hall_key(x["hall"]) not in pins})
    if store.list_maps(trip_id) and missing:
        warns.append(f"지도에 위치를 정하지 않은 홀이 있어요: {', '.join(missing)} ('지도에 배치' 탭). 폰 지도에 이 홀의 업체는 표시되지 않아요.")
    if not cs:
        warns.append("패키지에 넣을 업체를 아직 고르지 않았어요. 현장에서 하나씩 추가해야 합니다.")
    elif any(x["day"] is None for x in stops):
        warns.append(f"일정(일차)이 정해지지 않은 방문 지점(부스)이 {sum(x['day'] is None for x in stops)}곳 있어요.")
    edited = [n for n in range(1, len(store.get_trip(trip_id).get("days", [])) + 1) if (daily.day_dir(store, trip_id, n) / "final" / "보고서.md").is_file()]
    if edited and not find_browser():
        warns.append("수정한 일간 보고서를 PDF 로 바꾸려면 크롬(또는 엣지)이 필요한데 찾지 못했어요. 이대로 보내면 PDF 는 빠져요.")
    elif edited:
        warns.append(f"수정한 일간 보고서({', '.join(f'{n}일차' for n in edited)})는 PDF 로 바꿔 함께 보내요. 처음 한 번은 일차마다 십수 초 걸려요.")
    ss = store.get_sessions(trip_id)
    if any(not x.get("verified") for x in ss):
        warns.append(f"공식 사이트에서 확인하지 못한 세션이 {sum(not x.get('verified') for x in ss)}개 있어요. 일정이 바뀌었을 수 있으니 확인해 주세요.")
    unverified = [c for c in cs if c.get("source") == "ai" and not c.get("verified")]
    if unverified:
        warns.append(f"AI가 찾았지만 참가 여부를 확인하지 못한 업체가 {len(unverified)}곳 있어요. 공식 목록에서 확인해 주세요.")
    return warns


def build_package(store: Store, trip_id: str) -> tuple[str, bytes]:
    trip = store.get_trip(trip_id)
    if not trip.get("days"):
        raise StoreError("출장 날짜가 없습니다.")
    root = f"trip_{_slug(trip['name'])}"
    trip_out = {
        "schema": SCHEMA_VERSION,
        "id": trip["id"],
        "name": trip["name"],
        "venue": trip.get("venue", ""),
        "purpose": trip.get("purpose", ""),
        "days": trip["days"],
        "bookings": _bookings(store, trip_id),
        "local": _local(store, trip_id),
        "sessions": [{k: x.get(k, "") for k in ("id", "title", "date", "start", "end", "place", "hall", "speaker", "topic")}
                     for x in store.get_sessions(trip_id)],  # 세션은 전부 폰으로 보내고, 갈지 말지는 폰에서 고른다
        "gaps": [{"day": n, "date": d, "text": t} for n, d in enumerate(trip["days"], 1) if (t := daily.get_state(store, trip_id, n).get("gaps"))],  # 일간 보고서에 적은 '미흡한 부분'
        "hallPins": trip.get("hallPins", {}),  # 홀 → 지도 위 위치. 폰 지도에 일자별로 표시한다
    }
    companies = []
    for c in picked(research.mark_core(store.get_companies(trip_id), trip.get("coreKeywords"))):
        st = booths.stops(c)
        for x in st:
            item = {"id": x["id"], "name": c["name"], "category": c.get("category") or "기타", "hall": x["hall"], "booth": x["booth"], "day": x["day"],
                    "preNotes": research.package_note(c), "questions": list(dict.fromkeys([*trip.get("questions", []), *c.get("questions", [])]))}
            if c.get("core"):  # 핵심 키워드에 맞는 업체 — 폰에서 중요도 높음으로 보여 준다
                item["core"] = True
            if len(st) > 1:  # 같은 업체의 다른 부스 — 폰에서 '중복 업체'로 알아볼 수 있게 한다
                item["dup"] = {"n": len(st), "i": x["index"] + 1, "others": [{"id": y["id"], "hall": y["hall"], "booth": y["booth"], "day": y["day"]} for y in st if y is not x]}
            companies.append(item)
    # 수정본을 올려 둔 일차는 PDF 로 바꿔 함께 보낸다(사진을 줄여 용량을 아낀다). 폰 앱에서 볼 수 있다.
    pdfs = {n: p for n in range(1, len(trip["days"]) + 1) if (p := pdfreport.day_report_pdf(store, trip_id, n))}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, p in pdfs.items():
            z.writestr(f"{root}/reports/day{n}.pdf", p)
        z.writestr(f"{root}/trip.json", json.dumps(trip_out, ensure_ascii=False, indent=2))
        z.writestr(f"{root}/companies.json", json.dumps(companies, ensure_ascii=False, indent=2))
        z.writestr(f"{root}/glossary.json", json.dumps({"terms": store.get_glossary(trip_id)}, ensure_ascii=False, indent=2))
        primary = store.primary_map(trip_id)  # 폰에는 대표 지도 1장만 보낸다
        if primary:
            imgs = store.render_files(trip_id) if primary.suffix.lower() == ".pdf" else []
            if imgs:  # PDF 는 노트북에서 미리 이미지로 바꿔 둔 것을 보낸다 → 폰이 변환하느라 오래 걸리지 않고 용량도 작다
                for im in imgs:
                    z.write(im, f"{root}/map/{Path(primary.name).stem}_{im.name}")
            else:
                z.write(primary, f"{root}/map/{primary.name}")
    return f"{root}.zip", buf.getvalue()
