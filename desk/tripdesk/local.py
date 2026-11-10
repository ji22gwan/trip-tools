"""현지에서 먹고 이동하기: 경유 공항·숙소 주변 식사 장소, 공항↔숙소↔행사장 교통편.

Desk 는 AI 를 직접 부르지 않는다. 사용자가 이미 적어 둔 항공·숙소 기록으로 '프롬프트'를 만들어 주고,
AI 챗봇의 JSON 답변을 붙여 넣으면 정리해서 저장한다(폰으로도 보낸다).
"""
import re
import uuid

from . import research, travel
from .store import Store, StoreError

MEAL_KINDS = ("airport", "hotel", "venue")
_REF = re.compile(r"^(lay:[\w\-]{1,40}:\d{1,2}|hotel:[\w\-]{1,40}|venue)$")
LEGS = {"arr-hotel": "도착 공항 → 숙소", "hotel-venue": "숙소 ↔ 행사장 (매일 출퇴근)", "hotel-dep": "숙소 → 출발 공항 (귀국)", "other": "기타"}


def _s(v, n=200) -> str:
    return travel._s(v, n)


def _clean_place(x) -> dict | None:
    if not isinstance(x, dict) or not _s(x.get("name"), 120):
        return None
    ref = _s(x.get("ref"), 80)
    return {
        "id": _s(x.get("id"), 20) or "m-" + uuid.uuid4().hex[:8],
        "ref": ref if _REF.match(ref) else "", "area": _s(x.get("area"), 80),
        "name": _s(x.get("name"), 120), "cuisine": _s(x.get("cuisine"), 80), "meal": _s(x.get("meal"), 30),
        "price": _s(x.get("price"), 80), "where": _s(x.get("where"), 200), "hours": _s(x.get("hours"), 160),
        "why": _s(x.get("why"), 400), "tip": _s(x.get("tip"), 300), "sourceUrl": travel._url(x.get("sourceUrl")),
        "fav": x.get("fav") is True,
    }


def _clean_route(x) -> dict | None:
    if not isinstance(x, dict) or not (_s(x.get("from")) or _s(x.get("to")) or _s(x.get("line"))):
        return None
    leg = _s(x.get("leg"), 20)
    try:
        dur = int(float(x.get("durationMin")))
        dur = dur if 0 < dur < 1500 else None
    except (TypeError, ValueError):
        dur = None
    steps = [_s(t, 200) for t in (x.get("steps") or []) if _s(t, 200)][:12] if isinstance(x.get("steps"), list) else []
    return {
        "id": _s(x.get("id"), 20) or "r-" + uuid.uuid4().hex[:8], "leg": leg if leg in LEGS else "other",
        "label": _s(x.get("label"), 100), "from": _s(x.get("from"), 100), "to": _s(x.get("to"), 100),
        "mode": _s(x.get("mode"), 60), "line": _s(x.get("line"), 80), "boardStation": _s(x.get("boardStation"), 100), "alightStation": _s(x.get("alightStation"), 100),
        "durationMin": dur, "frequency": _s(x.get("frequency"), 80), "firstLast": _s(x.get("firstLast"), 120),
        "fare": _s(x.get("fare"), 100), "ticket": _s(x.get("ticket"), 120), "whereToBuy": _s(x.get("whereToBuy"), 160), "taxi": _s(x.get("taxi"), 120),
        "steps": steps, "tips": _s(x.get("tips"), 400), "sourceUrl": travel._url(x.get("sourceUrl")), "fav": x.get("fav") is True,
    }


def _clean_pass(x) -> dict | None:
    if not isinstance(x, dict) or not _s(x.get("name"), 120):
        return None
    return {"id": _s(x.get("id"), 20) or "p-" + uuid.uuid4().hex[:8], "name": _s(x.get("name"), 120), "price": _s(x.get("price"), 80),
            "valid": _s(x.get("valid"), 160), "whereToBuy": _s(x.get("whereToBuy"), 160), "note": _s(x.get("note"), 300)}


def default_local() -> dict:
    return {"prefs": "", "meals": [], "routes": [], "passes": [], "notes": ""}


def get(store: Store, tid: str) -> dict:
    d = default_local()
    d.update(store._read(store._dir(tid) / "local.json", {}))
    d["meals"] = [x for x in map(_clean_place, d["meals"]) if x]
    d["routes"] = [x for x in map(_clean_route, d["routes"]) if x]
    d["passes"] = [x for x in map(_clean_pass, d["passes"]) if x]
    return d


def save(store: Store, tid: str, data: dict) -> dict:
    cur = get(store, tid)
    if "prefs" in data:
        cur["prefs"] = _s(data["prefs"], 600)
    if "notes" in data:
        cur["notes"] = _s(data["notes"], 1500)
    if "meals" in data:
        cur["meals"] = [x for x in map(_clean_place, data["meals"] or []) if x][:300]
    if "routes" in data:
        cur["routes"] = [x for x in map(_clean_route, data["routes"] or []) if x][:60]
    if "passes" in data:
        cur["passes"] = [x for x in map(_clean_pass, data["passes"] or []) if x][:30]
    store._write(store._dir(tid) / "local.json", cur)
    return cur


# ---------------- 프롬프트에 넣을 '내 상황' ----------------

def _hm(dt: str) -> str:
    return dt.replace("T", " ") if dt else "?"


def targets(store: Store, tid: str) -> dict:
    """식사 장소를 찾을 만한 곳(경유 공항·숙소·행사장)과 이동 구간을 항공·숙소 기록에서 뽑는다."""
    trip = store.get_trip(tid)
    tr = travel.get(store, tid)
    airports = []
    for j in (travel.decorate(f) for f in tr["flights"]):
        segs = j["segments"]
        for i, lay in enumerate(j["layovers"]):
            a, b = segs[i], segs[i + 1]
            airports.append({
                "ref": f"lay:{j['id'] or 'f'}:{i}", "code": lay["at"], "direction": j["direction"], "flight": " → ".join(j["route"]),
                "arrive": a["arrive"], "depart": b["depart"], "minutes": lay["minutes"], "arrTerm": a["toTerm"], "depTerm": b["fromTerm"],
                "airportChange": lay["airportChange"], "toAirport": lay["to"], "arrFlight": a["flightNo"], "depFlight": b["flightNo"],
            })
    hotels = [{"ref": f"hotel:{h['id']}", "name": h["name"], "address": h["address"], "checkIn": h["checkIn"], "checkOut": h["checkOut"]} for h in tr["hotels"]]
    outs = sorted((travel.decorate(f) for f in tr["flights"] if f["direction"] == "outbound"), key=lambda j: j["segments"][0]["depart"])
    rets = sorted((travel.decorate(f) for f in tr["flights"] if f["direction"] == "return"), key=lambda j: j["segments"][0]["depart"])
    arr = outs[-1]["segments"][-1] if outs else None
    dep = rets[0]["segments"][0] if rets else None
    return {
        "airports": airports, "hotels": hotels, "venue": {"ref": "venue", "name": trip.get("venue") or trip["name"]},
        "arrival": {"airport": arr["to"] if arr else (tr["destination"] or ""), "terminal": arr["toTerm"] if arr else "", "time": arr["arrive"] if arr else ""},
        "departure": {"airport": dep["from"] if dep else (tr["destination"] or ""), "terminal": dep["fromTerm"] if dep else "", "time": dep["depart"] if dep else ""},
    }


def _hotel_line(h: dict) -> str:
    return f"{h['name']} (주소: {h['address'] or '미입력 — 이름으로 위치를 찾아 주세요'}, 숙박 {h['checkIn'] or '?'} ~ {h['checkOut'] or '?'})"


_MEAL_JSON = ('{"places":[{"ref":"(아래 \'대상\'의 ref 값을 그대로)","area":"FRA 공항 T1 / 호텔 주변","name":"가게 이름(현지 표기)","cuisine":"독일 가정식","meal":"점심",'
              '"price":"1인 약 12~18유로","where":"보안검색 후 B구역 / 호텔에서 도보 6분","hours":"월~토 11:00~22:00, 일 휴무","why":"혼자 먹기 편하고 주문이 빠름","tip":"점심 피크 12시 전후엔 줄이 김","sourceUrl":""}],"notes":""}')


def build_meal_prompt(store: Store, tid: str, refs: list[str], prefs: str = "") -> str:
    trip = store.get_trip(tid)
    t = targets(store, tid)
    air = {a["ref"]: a for a in t["airports"]}
    hot = {h["ref"]: h for h in t["hotels"]}
    pick = [r for r in dict.fromkeys(refs) if r in air or r in hot or r == "venue"]
    if not pick:
        raise StoreError("식사 장소를 찾을 곳(경유 공항·숙소·행사장)을 하나 이상 골라 주세요.")
    days = trip["days"]
    L = [f"출장 중 식사할 장소를 추천해 주세요. 반드시 웹 검색(지도·리뷰·공식 사이트)을 사용하고, 아래 '대상' 각각에 대해 따로 정리해 주세요.\n",
         f"[출장] {trip['name']} · 행사장 {t['venue']['name']} · {days[0]} ~ {days[-1]} · 혼자 출장 중인 한국인 직장인 기준"]
    if prefs.strip():
        L.append(f"[내 취향·제약] {prefs.strip()}")
    L.append("\n[대상]")
    for r in pick:
        if r in air:
            a = air[r]
            mins = f"{a['minutes']}분" if a["minutes"] is not None and a["minutes"] >= 0 else "확인 필요"
            L.append(f"- ref={r} · 경유 공항 {a['code']} ({a['flight']}) — {a['arrFlight'] or '도착편'}이 {_hm(a['arrive'])}에 터미널 {a['arrTerm'] or '?'}에 도착, "
                     f"{a['depFlight'] or '다음 편'}이 {_hm(a['depart'])}에 터미널 {a['depTerm'] or '?'}에서 출발 → 대기 {mins}"
                     + (f". 공항이 바뀌어 {a['toAirport']}로 이동해야 함" if a["airportChange"] else ""))
        elif r in hot:
            L.append(f"- ref={r} · 숙소 주변 — {_hotel_line(hot[r])}")
        else:
            L.append(f"- ref=venue · 행사장({t['venue']['name']}) 안팎 — 전시 중 점심을 해결할 곳(행사장 내 식당가·푸드코트, 가까운 외부 식당)")
    arr = t["arrival"]
    L.append("\n[조건 — 이 부분이 가장 중요합니다]")
    L += [
        "1. 공항(경유): 대기 시간 안에 실제로 먹고 올 수 있는 곳만 추천하세요. 환승 동선(보안검사·입국심사·터미널 이동·탑승 마감 약 40분 전)을 빼고 남는 시간을 계산해, 시간이 빠듯하면 '포장·빠른 식사' 위주로, 여유가 있으면 앉아서 먹는 곳도 넣어 주세요. "
        "보안검색 이후(airside)인지 이전(landside)인지, 터미널·구역을 반드시 적고, 그 도착·출발 시각에 영업 중인지(새벽·심야 포함) 확인해 주세요. 같은 공항이라도 터미널이 다르면 이동 가능 여부(셔틀·도보 분)를 알려 주세요. "
        "공항이 바뀌는 경유라면 식사보다 이동 시간이 우선이니, 먹을 수 있는지부터 판단해 알려 주세요.",
        f"2. 숙소 주변: 숙소에서 도보 10~15분 안쪽(가까울수록 좋음)을 기준으로, 호텔 조식은 포함 여부를 모르니 저녁·늦은 저녁·간단한 아침/카페를 나눠 추천하세요. "
        + (f"출장 첫날 숙소에 {_hm(arr['time'])} 무렵 도착 예정이니 늦은 시각에도 여는 곳을 최소 1곳 포함하고, " if arr["time"] else "")
        + "현지 휴무일(예: 독일은 일요일·공휴일에 대부분 휴무)과 점심 휴게시간, 라스트 오더 시각을 출장 날짜 기준으로 확인해 주세요. 혼자 가기 편한 곳(바 좌석·빠른 회전)을 우선하세요.",
        "3. 대상마다 3~5곳, 서로 종류가 겹치지 않게(현지식·가벼운 한 끼·아시안/한식·카페·마트/베이커리 등) 골라 주세요. 평점 숫자만 보지 말고 최근 리뷰의 영업 상태(폐업·이전 여부)를 확인하세요.",
        "4. 가격은 1인 기준 대략값(통화 표기)으로, 주소나 구역은 지도 앱에서 찾을 수 있게 적어 주세요. 확인하지 못한 영업시간·가격은 '미확인'이라고 쓰고 절대 지어내지 마세요. sourceUrl 에 근거(지도·공식 사이트) 주소를 넣어 주세요.",
        "5. 각 장소에 '왜 추천하는지'(한 줄)와 주문·예약 팁을 넣고, 답변 본문에는 대상별 추천 순서와 한 줄 요약도 적어 주세요.",
    ]
    return "\n".join(L) + travel._json_tail(_MEAL_JSON)


_ROUTE_JSON = ('{"routes":[{"leg":"arr-hotel","label":"공항 → 숙소","from":"뉘른베르크 공항(NUE)","to":"호텔 이름","mode":"지하철","line":"U2 (Röthenbach 방면)","boardStation":"Flughafen","alightStation":"Hauptbahnhof",'
               '"durationMin":12,"frequency":"평일 낮 10분 간격","firstLast":"첫차 04:30 / 막차 00:45","fare":"편도 3.30유로","ticket":"Einzelfahrschein 요금구역 A","whereToBuy":"역 승강장 자동판매기, VGN 앱",'
               '"taxi":"약 25~30유로, 20분","steps":["공항 도착홀에서 U2 표지판 따라 지하철역으로","Flughafen 승차 → Hauptbahnhof 하차","역에서 호텔까지 도보 5분"],"tips":"탑승 전 반드시 개찰(Entwerter) 필요","sourceUrl":""}],'
               '"passes":[{"name":"1일권 (Tageskarte Plus)","price":"약 9.2유로","valid":"당일~다음날 03:00, 동승 1인","whereToBuy":"자동판매기·앱","note":"행사 입장권에 대중교통이 포함되는지 확인"}],"notes":""}')


def build_transport_prompt(store: Store, tid: str, legs: list[str], prefs: str = "") -> str:
    trip = store.get_trip(tid)
    t = targets(store, tid)
    legs = [x for x in dict.fromkeys(legs) if x in ("arr-hotel", "hotel-venue", "hotel-dep")]
    if not legs:
        raise StoreError("알아볼 이동 구간을 하나 이상 골라 주세요.")
    hotel = t["hotels"][0] if t["hotels"] else None
    hot = _hotel_line(hotel) if hotel else "(숙소 미정 — 행사장 주변·시내 중심 어디든 일반적인 시내 숙소 기준으로 설명)"
    arr, dep = t["arrival"], t["departure"]
    days = trip["days"]
    L = [f"출장지에서 쓸 현지 교통편을 알려 주세요. 반드시 웹 검색(교통공사·철도·행사 공식 사이트·지도 앱)을 사용해 최신 정보를 확인하세요.\n",
         f"[출장] {trip['name']} · {days[0]} ~ {days[-1]} · 행사장 {t['venue']['name']} · 혼자 출장 중인 한국인 직장인, 현지 대중교통이 처음",
         f"[숙소] {hot}"]
    if prefs.strip():
        L.append(f"[내 취향·제약] {prefs.strip()}")
    L.append("\n[알아볼 구간]")
    if "arr-hotel" in legs:
        L.append(f"- leg=arr-hotel · 도착 공항({arr['airport'] or '?'}{' T' + arr['terminal'] if arr['terminal'] else ''}) → 숙소. 도착 예정 {_hm(arr['time'])}")
    if "hotel-venue" in legs:
        L.append(f"- leg=hotel-venue · 숙소 ↔ 행사장({t['venue']['name']}) 매일 왕복. 전시 시간대(이른 아침 출근·저녁 퇴근) 기준")
    if "hotel-dep" in legs:
        L.append(f"- leg=hotel-dep · 숙소 → 출발 공항({dep['airport'] or '?'}{' T' + dep['terminal'] if dep['terminal'] else ''}). 출발 예정 {_hm(dep['time'])} (귀국 날)")
    L.append("\n[조건 — 이 부분이 가장 중요합니다]")
    L += [
        "1. 구간마다 가장 추천하는 방법 1개(+ 대안 1~2개: 다른 노선·택시·도보)를 알려 주세요. 각각 노선/번호, 탑승역(정류장)과 하차역, 환승이 있으면 환승역과 방향(종착역 이름), 소요 시간, 배차 간격, 첫차·막차(행사 시간대와 도착 시각이 막차 이후이면 대안 필수)를 적어 주세요.",
        "2. 요금은 현지 통화로 편도/왕복/1일권을 모두 알려 주고, 어느 표가 가장 이득인지(예: 출장 일수 기준 1일권 vs 개별 편도 vs 다일권) 계산해서 추천하세요. 요금구역·표 종류 이름은 현지 표기 그대로 적어 주세요.",
        "3. 표를 어디서 어떻게 사는지(자동판매기 위치, 앱 이름과 설치 후 결제 방법, 해외 카드 사용 여부), 개찰·검표 방법(개찰기 필수인지)과 무임승차 단속 유의점을 적어 주세요.",
        "4. 행사장 입장권(전시회 등록 배지·티켓)에 대중교통 무료 이용이 포함되는지 공식 사이트에서 확인해 알려 주세요. 포함이라면 적용 범위와 시간대, 사용 방법도요.",
        "5. 행사장 주변은 행사 기간에 임시 셔틀·증편·혼잡이 있는지, 정문·입구(홀 기준)가 어느 역과 가까운지(예: 어떤 출구/게이트)도 알려 주세요.",
        "6. 택시/승차공유(Uber·Bolt 등)는 대략 요금과 소요 시간만 적고, 늦은 밤이나 짐이 많을 때의 대안으로 설명하세요.",
        "7. 확인하지 못한 정보는 '미확인'이라고 쓰고 절대 지어내지 마세요. 요금·시간표는 변동될 수 있으니 확인한 날짜와 sourceUrl(공식 사이트 주소)을 적어 주세요.",
    ]
    return "\n".join(L) + travel._json_tail(_ROUTE_JSON)


# ---------------- 붙여넣기 ----------------

def paste(store: Store, tid: str, kind: str, text: str) -> dict:
    data = research.extract_json(text)
    cur = get(store, tid)
    if kind == "meals":
        new = [x for x in map(_clean_place, data.get("places") or []) if x][:100]
        if not new:
            raise research.ResearchError("식사 장소를 찾지 못했어요. 답변의 JSON 블록이 빠졌는지 확인해 주세요.")
        key = lambda x: (x["ref"], x["name"].casefold())
        idx = {key(x): i for i, x in enumerate(cur["meals"])}
        added = 0
        for x in new:
            k = key(x)
            if k in idx:
                old = cur["meals"][idx[k]]
                cur["meals"][idx[k]] = dict(x, id=old["id"], fav=old["fav"])  # 같은 곳을 다시 받으면 최신 정보로 갱신하고 즐겨찾기는 유지
            else:
                cur["meals"].append(x)
                idx[k] = len(cur["meals"]) - 1
                added += 1
        save(store, tid, {"meals": cur["meals"]})
        return {"added": added, "updated": len(new) - added}
    if kind == "transport":
        routes = [x for x in map(_clean_route, data.get("routes") or []) if x][:30]
        passes = [x for x in map(_clean_pass, data.get("passes") or []) if x][:20]
        if not (routes or passes):
            raise research.ResearchError("교통 정보를 찾지 못했어요. 답변의 JSON 블록이 빠졌는지 확인해 주세요.")
        # 같은 구간을 다시 받으면 그 구간은 새 답변으로 바꾼다(요금·시간표는 최신이 맞다). 즐겨찾기 표시는 노선 이름이 같으면 이어받는다.
        favs = {(r["leg"], r["line"].casefold()) for r in cur["routes"] if r["fav"]}
        legs = {r["leg"] for r in routes}
        keep = [r for r in cur["routes"] if r["leg"] not in legs]
        for r in routes:
            r["fav"] = r["fav"] or (r["leg"], r["line"].casefold()) in favs
        pk = {p["name"].casefold(): p for p in cur["passes"]}
        for p in passes:
            pk[p["name"].casefold()] = p
        notes = _s(data.get("notes"), 1500) or cur["notes"]
        save(store, tid, {"routes": keep + routes, "passes": list(pk.values()), "notes": notes})
        return {"added": len(routes), "updated": len(passes)}
    raise StoreError("알 수 없는 종류예요.")
