"""항공·숙소: 검색 바로가기(링크), AI 챗봇 프롬프트/붙여넣기, 예약 기록.

실시간 검색은 하지 않는다(사이트가 자동 조회를 막고 가격·잔여는 금방 바뀐다).
검색 페이지 주소에 출발지·목적지·날짜·별점을 미리 채워 열어 주고, 예약이 끝나면 기록만 보관한다.
"""
import re
import uuid
from datetime import date, timedelta
from urllib.parse import quote, quote_plus

from . import research
from .store import Store, StoreError

KINDS_DIR = {"outbound": "가는 편", "return": "오는 편", "other": "기타"}
CURRENCIES = {"KRW", "EUR", "USD", "JPY", "GBP", "CNY"}


def _s(v, n=200) -> str:
    return str(v if v is not None else "").strip()[:n]


def _date(v) -> str:
    v = _s(v, 10)
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else ""


def _dt(v) -> str:
    v = _s(v, 16).replace(" ", "T")
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", v) else ""


def _money(v):
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return round(x, 2) if 0 <= x < 1e9 else None


def _cur(v) -> str:
    v = _s(v, 3).upper()
    return v if v in CURRENCIES else "KRW"


def _id(v) -> str:
    v = _s(v, 40)
    return v if re.fullmatch(r"[\w-]+", v) else "b-" + uuid.uuid4().hex[:8]


def clean_flight(f) -> dict | None:
    if not isinstance(f, dict):
        return None
    out = {
        "id": _id(f.get("id")), "direction": f.get("direction") if f.get("direction") in KINDS_DIR else "other",
        "airline": _s(f.get("airline"), 60), "flightNo": _s(f.get("flightNo"), 12).upper(),
        "from": _s(f.get("from"), 60), "to": _s(f.get("to"), 60), "depart": _dt(f.get("depart")), "arrive": _dt(f.get("arrive")),
        "confirmation": _s(f.get("confirmation"), 40), "amount": _money(f.get("amount")), "currency": _cur(f.get("currency")),
        "baggage": _s(f.get("baggage"), 80), "note": _s(f.get("note"), 400),
    }
    return out if (out["flightNo"] or out["airline"] or out["confirmation"] or out["depart"]) else None


def clean_hotel(x) -> dict | None:
    if not isinstance(x, dict):
        return None
    try:
        stars = int(x.get("stars") or 0)
    except (TypeError, ValueError):
        stars = 0
    out = {
        "id": _id(x.get("id")), "name": _s(x.get("name"), 120), "stars": stars if 1 <= stars <= 5 else 0,
        "address": _s(x.get("address"), 200), "checkIn": _date(x.get("checkIn")), "checkOut": _date(x.get("checkOut")),
        "confirmation": _s(x.get("confirmation"), 40), "amount": _money(x.get("amount")), "currency": _cur(x.get("currency")),
        "freeCancelUntil": _dt(x.get("freeCancelUntil")), "site": _s(x.get("site"), 40), "note": _s(x.get("note"), 400),
    }
    return out if out["name"] else None


def clean_candidates(data: dict) -> dict:
    fl, ho = [], []
    for f in (data.get("flights") or [])[:30]:
        if isinstance(f, dict) and (f.get("flightNo") or f.get("airline")):
            fl.append({"airline": _s(f.get("airline"), 60), "flightNo": _s(f.get("flightNo"), 12).upper(), "from": _s(f.get("from"), 40), "to": _s(f.get("to"), 40),
                       "depart": _dt(f.get("depart")), "arrive": _dt(f.get("arrive")), "stops": _s(f.get("stops"), 40), "price": _s(f.get("price"), 40),
                       "sourceUrl": _url(f.get("sourceUrl")), "note": _s(f.get("note"), 300)})
    for x in (data.get("hotels") or [])[:30]:
        if isinstance(x, dict) and x.get("name"):
            try:
                st = int(x.get("stars") or 0)
            except (TypeError, ValueError):
                st = 0
            ho.append({"name": _s(x.get("name"), 120), "stars": st if 1 <= st <= 5 else 0, "address": _s(x.get("address"), 200), "distance": _s(x.get("distance"), 60),
                       "price": _s(x.get("price"), 40), "cancellation": _s(x.get("cancellation"), 80), "sourceUrl": _url(x.get("sourceUrl")), "note": _s(x.get("note"), 300)})
    return {"flights": fl, "hotels": ho}


def _url(v) -> str:
    v = _s(v, 500)
    return v if re.match(r"^https?://", v) else ""


def default_travel(trip: dict) -> dict:
    return {"origin": "", "destination": "", "minStars": 3, "maxStars": 4, "outDate": "", "retDate": "", "checkIn": "", "checkOut": "",
            "flights": [], "hotels": [], "candidates": {"flights": [], "hotels": []}, "notes": ""}


def get(store: Store, tid: str) -> dict:
    t = default_travel(store.get_trip(tid))
    t.update(store._read(store._dir(tid) / "travel.json", {}))
    return t


def save(store: Store, tid: str, data: dict) -> dict:
    cur = get(store, tid)
    for k in ("origin", "destination", "notes"):
        if k in data:
            cur[k] = _s(data[k], 200 if k != "notes" else 2000)
    for k in ("outDate", "retDate", "checkIn", "checkOut"):
        if k in data:
            cur[k] = _date(data[k])
    if "minStars" in data or "maxStars" in data:
        lo = max(1, min(5, int(data.get("minStars", cur["minStars"]) or 1)))
        hi = max(1, min(5, int(data.get("maxStars", cur["maxStars"]) or 5)))
        cur["minStars"], cur["maxStars"] = min(lo, hi), max(lo, hi)
    if "flights" in data:
        cur["flights"] = [x for x in map(clean_flight, data["flights"] or []) if x][:30]
    if "hotels" in data:
        cur["hotels"] = [x for x in map(clean_hotel, data["hotels"] or []) if x][:30]
    if "candidates" in data:
        cur["candidates"] = clean_candidates(data["candidates"] or {})
    store._write(store._dir(tid) / "travel.json", cur)
    return cur


def _dates(trip: dict, tr: dict) -> tuple[str, str, str, str]:
    days = trip["days"]
    out = tr["outDate"] or days[0]
    ret = tr["retDate"] or days[-1]
    ci = tr["checkIn"] or days[0]
    co = tr["checkOut"] or days[-1]
    return out, ret, ci, co


def _yymmdd(d: str) -> str:
    return d[2:4] + d[5:7] + d[8:10]


def links(trip: dict, tr: dict) -> dict:
    """검색 페이지 바로가기. 주소 형식은 사이트가 바꿀 수 있어 일부 값(특히 별점 필터)은 미리 채워지지 않을 수 있다."""
    out, ret, ci, co = _dates(trip, tr)
    o, d = tr["origin"].strip(), (tr["destination"] or trip.get("venue", "")).strip()
    lo, hi = tr["minStars"], tr["maxStars"]
    place = trip.get("venue", "").strip() or d  # 호텔은 공항 코드가 아니라 행사장(없으면 목적지) 근처로 찾는다
    fl, ho = [], []
    if o and d:
        fl.append({"name": "Google 항공편", "url": "https://www.google.com/travel/flights?q=" + quote_plus(f"Flights from {o} to {d} on {out} through {ret}")})
        if re.fullmatch(r"[A-Za-z]{3}", o) and re.fullmatch(r"[A-Za-z]{3}", d):
            fl.append({"name": "Skyscanner", "url": f"https://www.skyscanner.co.kr/transport/flights/{o.lower()}/{d.lower()}/{_yymmdd(out)}/{_yymmdd(ret)}/"})
    if place:
        stars = ",".join(str(s * 10) for s in range(lo, hi + 1))
        ho += [
            {"name": "Agoda", "url": f"https://www.agoda.com/search?textToSearch={quote_plus(place)}&checkIn={ci}&checkOut={co}&rooms=1&adults=1&minStarRating={lo}&maxStarRating={hi}"},
            {"name": "Hotels.com", "url": f"https://www.hotels.com/Hotel-Search?destination={quote_plus(place)}&startDate={ci}&endDate={co}&adults=1&star={quote(stars)}&sort=DISTANCE"},
            {"name": "Booking.com", "url": f"https://www.booking.com/searchresults.html?ss={quote_plus(place)}&checkin={ci}&checkout={co}&group_adults=1&no_rooms=1&nflt=" + quote(";".join(f"class={s}" for s in range(lo, hi + 1)))},
            {"name": "Google 호텔", "url": f"https://www.google.com/travel/hotels/{quote(place)}?q={quote_plus(place + ' hotels')}&dates={ci},{co}"},
        ]
    return {"flights": fl, "hotels": ho, "dates": {"out": out, "ret": ret, "checkIn": ci, "checkOut": co}}


def _json_tail(example: str) -> str:
    return ("\n\n답변 마지막에 아래 형식의 JSON 을 ```json 코드 블록 하나로 넣어 주세요. 모르는 값은 빈 문자열로 두고 지어내지 마세요.\n```json\n" + example + "\n```")


def build_flight_prompt(trip: dict, tr: dict) -> str:
    out, ret, _, _ = _dates(trip, tr)
    if not tr["origin"] or not tr["destination"]:
        raise StoreError("출발지와 목적지를 먼저 적어 주세요.")
    return (f"출장용 항공편을 찾아 주세요. 웹 검색을 사용하세요.\n- 출발지: {tr['origin']}\n- 목적지: {tr['destination']}\n- 가는 날: {out}\n- 오는 날: {ret}\n"
            f"- 출장지: {trip.get('venue') or trip['name']}\n\n조건: 직항 또는 1회 경유, 현지 도착 후 하루 일정에 무리가 없는 시각을 우선하고, 가는 편 3개·오는 편 3개 안팎으로 비교해 주세요. "
            "가격은 검색 시점의 대략값이며 변동될 수 있다고 밝혀 주세요. 확인하지 못한 항공편은 만들어 내지 말고 sourceUrl 에 근거 주소를 적어 주세요."
            + _json_tail('{"flights":[{"airline":"","flightNo":"","from":"ICN","to":"NUE","depart":"2026-11-23T10:00","arrive":"2026-11-23T16:00","stops":"직항|1회 경유(FRA)","price":"약 120만원","sourceUrl":"","note":""}],"notes":""}'))


def build_hotel_prompt(trip: dict, tr: dict) -> str:
    _, _, ci, co = _dates(trip, tr)
    place = tr["destination"] or trip.get("venue") or trip["name"]
    return (f"출장지 부근 호텔을 찾아 주세요. 웹 검색을 사용하세요.\n- 위치 기준: {trip.get('venue') or place} ({place})\n- 체크인: {ci} / 체크아웃: {co}\n"
            f"- 호텔 등급(성급, hotel class): {tr['minStars']}성 이상 {tr['maxStars']}성 이하 — 투숙객 리뷰 평점이 아니라 호텔 자체의 공식 성급 기준입니다\n- 이용 사이트 참고: Hotels.com, Agoda, Booking.com\n\n조건: 행사장까지 이동이 편한(도보·대중교통) 곳을 우선하고, 해당 날짜에 예약 가능해 보이는 곳만 8곳 안팎 추려 주세요. "
            "각 호텔의 stars 에는 성급(1~5의 정수)을 넣고, 성급을 확인하지 못한 곳은 0 으로 두세요. 행사 기간에는 요금이 오르거나 만실일 수 있으니 확인하지 못한 가용 여부는 '미확인'이라고 적고, 취소 가능 여부도 알려 주세요. 지어내지 말고 sourceUrl 에 근거 주소를 적어 주세요."
            + _json_tail('{"hotels":[{"name":"","stars":4,"address":"","distance":"행사장까지 지하철 15분","price":"1박 약 150유로","cancellation":"무료 취소 ~11/20","sourceUrl":"","note":"가용 미확인"}],"notes":""}'))


def build_booking_prompt(text: str) -> str:
    return ("아래 예약 확인 메일·문자 내용에서 항공권과 숙소 예약 정보를 정리해 주세요. 내용에 없는 값은 빈 문자열로 두고 추측하지 마세요. "
            "시각은 현지 시각 그대로 YYYY-MM-DDTHH:MM, 날짜는 YYYY-MM-DD, 금액은 숫자만, 통화는 KRW/EUR/USD 같은 코드로 적어 주세요. 가는 편은 direction=outbound, 오는 편은 return 입니다.\n\n--- 예약 내용 ---\n"
            + (text or "").strip()[:12000] + "\n--- 끝 ---"
            + _json_tail('{"flights":[{"direction":"outbound","airline":"","flightNo":"","from":"","to":"","depart":"","arrive":"","confirmation":"","amount":0,"currency":"KRW","baggage":"","note":""}],"hotels":[{"name":"","stars":0,"address":"","checkIn":"","checkOut":"","confirmation":"","amount":0,"currency":"EUR","freeCancelUntil":"","site":"","note":""}]}'))


def paste(store: Store, tid: str, kind: str, text: str) -> dict:
    data = research.extract_json(text)
    tr = get(store, tid)
    if kind == "booking":
        fl = [x for x in map(clean_flight, data.get("flights") or []) if x]
        ho = [x for x in map(clean_hotel, data.get("hotels") or []) if x]
        key = lambda x: (x.get("confirmation") or "", x.get("flightNo") or x.get("name") or "", x.get("depart") or x.get("checkIn") or "")
        have = {key(x) for x in tr["flights"] + tr["hotels"]}
        add_f = [x for x in fl if key(x) not in have]
        add_h = [x for x in ho if key(x) not in have]
        if not (fl or ho):
            raise research.ResearchError("예약 정보를 찾지 못했어요. 메일 본문 전체를 넣었는지 확인해 주세요.")
        save(store, tid, {"flights": tr["flights"] + add_f, "hotels": tr["hotels"] + add_h})
        return {"added": len(add_f) + len(add_h), "existing": len(fl) + len(ho) - len(add_f) - len(add_h)}
    cand = clean_candidates(data)
    if kind == "flights":
        tr["candidates"]["flights"] = cand["flights"]
    else:
        tr["candidates"]["hotels"] = cand["hotels"]
    save(store, tid, {"candidates": tr["candidates"]})
    return {"added": len(cand["flights" if kind == "flights" else "hotels"]), "existing": 0}


def summary(tr: dict, trip: dict) -> dict:
    """통화별 합계와 점검 사항."""
    totals: dict[str, float] = {}
    for x in tr["flights"] + tr["hotels"]:
        if x.get("amount") is not None:
            totals[x["currency"]] = round(totals.get(x["currency"], 0) + x["amount"], 2)
    days = trip["days"]
    issues = []
    if not any(f["direction"] == "outbound" for f in tr["flights"]):
        issues.append("가는 항공편 기록이 없어요.")
    if not any(f["direction"] == "return" for f in tr["flights"]):
        issues.append("오는 항공편 기록이 없어요.")
    if not tr["hotels"]:
        issues.append("숙소 기록이 없어요.")
    for x in tr["hotels"]:
        if x["checkIn"] and x["checkIn"] > days[0]:
            issues.append(f"{x['name']}: 체크인({x['checkIn']})이 출장 첫날({days[0]})보다 늦어요.")
        if x["checkOut"] and x["checkOut"] < days[-1]:
            issues.append(f"{x['name']}: 체크아웃({x['checkOut']})이 출장 마지막 날({days[-1]})보다 일러요.")
    hs = sorted((x for x in tr["hotels"] if x["checkIn"] and x["checkOut"]), key=lambda x: x["checkIn"])
    for a, b in zip(hs, hs[1:]):
        if b["checkIn"] > a["checkOut"]:
            issues.append(f"{a['checkOut']} ~ {b['checkIn']} 사이에 숙소가 비어요.")
    return {"totals": totals, "issues": issues}
