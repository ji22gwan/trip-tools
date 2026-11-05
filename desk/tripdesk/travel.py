"""항공·숙소: 검색 바로가기(링크), AI 챗봇 프롬프트/붙여넣기, 예약 기록.

실시간 검색은 하지 않는다(사이트가 자동 조회를 막고 가격·잔여는 금방 바뀐다).
검색 페이지 주소에 출발지·목적지·날짜·별점을 미리 채워 열어 주고, 예약이 끝나면 기록만 보관한다.
"""
import re
import uuid
from datetime import date, datetime, timedelta
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


_MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def _time(txt: str) -> str:
    """'18:40', '6:40 PM', '오후 6:40' → '18:40' (24시간제). 알 수 없으면 ''."""
    m = re.search(r"(오전|오후|AM|PM|am|pm)?\s*(\d{1,2})\s*:\s*(\d{2})\s*(AM|PM|am|pm)?", txt)
    if not m:
        return ""
    ap = (m.group(1) or m.group(4) or "").upper()
    hh, mm = int(m.group(2)), int(m.group(3))
    if ap in ("PM", "오후") and hh < 12:
        hh += 12
    if ap in ("AM", "오전") and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm:02d}" if hh < 24 and mm < 60 else ""


def _dt(v) -> str:
    """날짜(+시각)를 'YYYY-MM-DD' 또는 'YYYY-MM-DDTHH:MM'(24시간제)으로 맞춘다. '23NOV26 18:40', '2026/11/23 6:40 PM' 도 받는다."""
    raw = _s(v, 40)
    d = ""
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if m:
        d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        rest = raw[m.end():]
    else:
        m = re.search(r"(\d{1,2})\s*([A-Za-z]{3})\s*(\d{2,4})", raw)
        if not m or m.group(2).upper() not in _MON:
            return ""
        y = int(m.group(3))
        y += 2000 if y < 100 else 0
        d = f"{y}-{_MON[m.group(2).upper()]:02d}-{int(m.group(1)):02d}"
        rest = raw[m.end():]
    try:
        date.fromisoformat(d)
    except ValueError:
        return ""
    t = _time(rest)
    return f"{d}T{t}" if t else d


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


def _airport(v) -> str:
    v = _s(v, 60)
    return v.upper() if re.fullmatch(r"[A-Za-z]{3}", v) else v


def clean_segment(g) -> dict | None:
    """여정 안의 한 구간(비행기 한 편, 또는 버스·기차 같은 지상 이동)."""
    if not isinstance(g, dict):
        return None
    out = {
        "flightNo": _s(g.get("flightNo"), 12).upper().replace(" ", ""), "airline": _s(g.get("airline"), 60), "operatedBy": _s(g.get("operatedBy"), 60),
        "from": _airport(g.get("from")), "to": _airport(g.get("to")), "depart": _dt(g.get("depart")), "arrive": _dt(g.get("arrive")),
        "fromTerm": _s(g.get("fromTerm"), 12), "toTerm": _s(g.get("toTerm"), 12), "cabin": _s(g.get("cabin"), 40), "baggage": _s(g.get("baggage"), 80),
        "aircraft": _s(g.get("aircraft"), 60), "mode": "ground" if g.get("mode") == "ground" else "air",
    }
    return out if (out["flightNo"] or (out["from"] and out["to"])) else None


def clean_flight(f) -> dict | None:
    """한 번의 이동(여정). 경유가 몇 번이든 segments 에 순서대로 담는다. 옛 형식(편명이 바로 들어 있는 한 편짜리)도 받는다."""
    if not isinstance(f, dict):
        return None
    raw = f.get("segments") if isinstance(f.get("segments"), list) else [f]
    segs = [x for x in map(clean_segment, raw[:12]) if x]
    if not segs:
        return None
    if not isinstance(f.get("segments"), list) and f.get("baggage"):
        segs[0]["baggage"] = _s(f.get("baggage"), 80)
    return {
        "id": _id(f.get("id")), "direction": f.get("direction") if f.get("direction") in KINDS_DIR else "other",
        "confirmation": _s(f.get("confirmation"), 40).upper(), "amount": _money(f.get("amount")), "currency": _cur(f.get("currency")),
        "note": _s(f.get("note"), 400), "segments": segs,
    }


def _minutes(a: str, b: str):
    try:
        return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60) if "T" in a and "T" in b else None
    except ValueError:
        return None


def clean_flights(items) -> list[dict]:
    """여러 건을 정리한다. 옛 형식의 '한 편씩' 기록이 같은 예약번호로 이어져 있으면(같은 공항에서 24시간 안에 연결) 한 여정으로 합친다."""
    out: list[dict] = []
    for raw in items or []:
        f = clean_flight(raw)
        if not f:
            continue
        legacy = isinstance(raw, dict) and not isinstance(raw.get("segments"), list)
        prev = out[-1] if out else None
        if legacy and prev and prev.get("_legacy") and f["confirmation"] and f["confirmation"] == prev["confirmation"]:
            last = prev["segments"][-1]
            gap = _minutes(last["arrive"], f["segments"][0]["depart"])
            if last["to"] and last["to"] == f["segments"][0]["from"] and gap is not None and 0 <= gap < 24 * 60:
                prev["segments"] += f["segments"]
                continue
        f["_legacy"] = legacy
        out.append(f)
    for f in out:
        f.pop("_legacy", None)
    return out


def decorate(j: dict) -> dict:
    """화면·보고서용 계산값(저장하지 않음): 경로, 경유 대기 시간."""
    segs = j["segments"]
    route = [segs[0]["from"]]
    lay = []
    for i, g in enumerate(segs):
        if g["from"] and g["from"] != route[-1]:
            route.append(g["from"])
        route.append(g["to"])
        if i + 1 < len(segs):
            n = segs[i + 1]
            lay.append({"at": g["to"], "minutes": _minutes(g["arrive"], n["depart"]), "airportChange": bool(g["to"] and n["from"] and g["to"] != n["from"]), "to": n["from"]})
    return dict(j, route=[x for x in route if x], layovers=lay)


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
        if isinstance(f, dict) and (f.get("flightNo") or f.get("airline") or f.get("segments")):
            segs = [x for x in map(clean_segment, (f.get("segments") or [])[:12]) if x]
            fn = _s(f.get("flightNo"), 40).upper() or " / ".join(g["flightNo"] for g in segs if g["flightNo"])
            fl.append({"airline": _s(f.get("airline"), 60), "flightNo": fn, "from": _airport(f.get("from") or (segs[0]["from"] if segs else "")),
                       "to": _airport(f.get("to") or (segs[-1]["to"] if segs else "")), "depart": _dt(f.get("depart") or (segs[0]["depart"] if segs else "")),
                       "arrive": _dt(f.get("arrive") or (segs[-1]["arrive"] if segs else "")), "stops": _s(f.get("stops"), 40), "price": _s(f.get("price"), 40),
                       "segments": segs, "sourceUrl": _url(f.get("sourceUrl")), "note": _s(f.get("note"), 300)})
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
    t["flights"] = clean_flights(t["flights"])  # 옛 '한 편씩' 기록은 여정(구간 묶음)으로 바꿔 보여 준다
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
        cur["flights"] = clean_flights(data["flights"])[:30]
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
            f"- 출장지: {trip.get('venue') or trip['name']}\n\n조건: 직항이 없거나 불편하면 경유(2회 이상도 가능)를 포함하고, 경유 횟수가 적고 대기 시간이 너무 길거나 짧지 않은 순으로, "
            "현지 도착 후 하루 일정에 무리가 없는 시각을 우선해 가는 편 3개·오는 편 3개 안팎으로 비교해 주세요. 경유편은 구간(segments)을 하나씩 나눠 적고, 시각은 24시간제(HH:MM) 현지 시각입니다. "
            "가격은 검색 시점의 대략값이며 변동될 수 있다고 밝혀 주세요. 확인하지 못한 항공편은 만들어 내지 말고 sourceUrl 에 근거 주소를 적어 주세요."
            + _json_tail('{"flights":[{"airline":"","flightNo":"LH713 / LH148","from":"ICN","to":"NUE","depart":"2026-11-23T12:55","arrive":"2026-11-23T22:10","stops":"1회 경유(FRA)","price":"약 120만원",'
                         '"segments":[{"flightNo":"LH713","from":"ICN","to":"FRA","depart":"2026-11-23T12:55","arrive":"2026-11-23T18:40"},{"flightNo":"LH148","from":"FRA","to":"NUE","depart":"2026-11-23T21:25","arrive":"2026-11-23T22:10"}],"sourceUrl":"","note":""}],"notes":""}'))


def build_hotel_prompt(trip: dict, tr: dict) -> str:
    _, _, ci, co = _dates(trip, tr)
    place = tr["destination"] or trip.get("venue") or trip["name"]
    return (f"출장지 부근 호텔을 찾아 주세요. 웹 검색을 사용하세요.\n- 위치 기준: {trip.get('venue') or place} ({place})\n- 체크인: {ci} / 체크아웃: {co}\n"
            f"- 호텔 등급(성급, hotel class): {tr['minStars']}성 이상 {tr['maxStars']}성 이하 — 투숙객 리뷰 평점이 아니라 호텔 자체의 공식 성급 기준입니다\n- 이용 사이트 참고: Hotels.com, Agoda, Booking.com\n\n조건: 행사장까지 이동이 편한(도보·대중교통) 곳을 우선하고, 해당 날짜에 예약 가능해 보이는 곳만 8곳 안팎 추려 주세요. "
            "각 호텔의 stars 에는 성급(1~5의 정수)을 넣고, 성급을 확인하지 못한 곳은 0 으로 두세요. 행사 기간에는 요금이 오르거나 만실일 수 있으니 확인하지 못한 가용 여부는 '미확인'이라고 적고, 취소 가능 여부도 알려 주세요. 지어내지 말고 sourceUrl 에 근거 주소를 적어 주세요."
            + _json_tail('{"hotels":[{"name":"","stars":4,"address":"","distance":"행사장까지 지하철 15분","price":"1박 약 150유로","cancellation":"무료 취소 ~11/20","sourceUrl":"","note":"가용 미확인"}],"notes":""}'))


_BOOKING_JSON = ('{"flights":[{"direction":"outbound","confirmation":"ABC123","amount":0,"currency":"KRW","note":"",'
                 '"segments":[{"flightNo":"LH713","airline":"Lufthansa","operatedBy":"","from":"ICN","to":"FRA","depart":"2026-11-23T12:55","arrive":"2026-11-23T18:40",'
                 '"fromTerm":"1","toTerm":"1","cabin":"W","baggage":"1PC","aircraft":"Boeing 787-9","mode":"air"},'
                 '{"flightNo":"LH148","airline":"Lufthansa","from":"FRA","to":"NUE","depart":"2026-11-23T21:25","arrive":"2026-11-23T22:10","mode":"air"}]}],'
                 '"hotels":[{"name":"","stars":0,"address":"","checkIn":"","checkOut":"","confirmation":"","amount":0,"currency":"EUR","freeCancelUntil":"","site":"","note":""}]}')


def build_booking_prompt(text: str = "") -> str:
    """예약 확인 화면(스크린샷)·메일·문자 → 기록. 글이 없으면 '첨부한 이미지' 기준 프롬프트를 만든다."""
    text = (text or "").strip()
    src = ("아래 예약 확인 메일·문자 내용" if text else "첨부한 이미지(예약 확인서·여정표 스크린샷. 여러 장이면 모두)") + "에서 항공권과 숙소 예약 정보를 정리해 주세요."
    rules = (
        "\n\n규칙:\n"
        "1. 보이는 값만 옮기고 없는 값은 빈 문자열로 두세요. 추측하지 마세요. 편명과 날짜만 있고 시각이 없으면 웹 검색으로 확인하되, 확인한 값은 note 에 '시각은 웹 검색 기준'이라고 적으세요.\n"
        "2. 하나의 이동(여정)은 flights 의 항목 하나이고, 비행기를 갈아타는 경유는 그 안의 segments 에 순서대로 모두 넣으세요(경유가 여러 번이어도 같습니다). "
        "같은 공항에서 24시간 안에 이어지는 구간은 한 여정입니다. 출장지에 가는 여정은 direction=outbound, 돌아오는 여정은 return, 국내선 등 그 밖의 이동은 other 입니다.\n"
        "3. 버스·기차 같은 지상 이동 구간도 segments 에 넣고 mode 를 ground 로 하세요(비행기는 air).\n"
        "4. 시각은 현지 시각 그대로 24시간제 YYYY-MM-DDTHH:MM (AM/PM 쓰지 않음, 예: 18:40). '23NOV26' 같은 표기는 2026-11-23 으로 바꾸세요. 금액은 숫자만, 통화는 KRW/EUR/USD 같은 코드입니다.\n"
        "5. 승객 이름, 항공권 번호(e-ticket), 여권·연락처는 적지 마세요. 예약번호(6자리 영숫자)는 confirmation 에 넣으세요.\n"
        "6. 터미널은 fromTerm/toTerm, 좌석등급은 cabin, 수하물은 baggage, 기종은 aircraft, 다른 항공사가 운항하면 operatedBy 에 넣으세요."
    )
    body = f"\n\n--- 예약 내용 ---\n{text[:12000]}\n--- 끝 ---" if text else ""
    return src + rules + body + _json_tail(_BOOKING_JSON)


def paste(store: Store, tid: str, kind: str, text: str) -> dict:
    data = research.extract_json(text)
    tr = get(store, tid)
    if kind == "booking":
        rawf = [x for x in (data.get("flights") or []) if isinstance(x, dict)]
        fl = clean_flights(rawf)
        # AI 가 가는/오는 구분을 빼먹었으면 날짜 순서로 짐작한다(화면에서 고칠 수 있다)
        if rawf and not any(x.get("direction") in KINDS_DIR for x in rawf):
            for i, f in enumerate(sorted(fl, key=lambda f: f["segments"][0]["depart"])):
                f["direction"] = "outbound" if i == 0 else "return" if i == 1 else "other"
        ho = [x for x in map(clean_hotel, data.get("hotels") or []) if x]
        fkey = lambda x: ("F", x["confirmation"], x["segments"][0]["flightNo"], x["segments"][0]["depart"][:10])
        hkey = lambda x: ("H", x["confirmation"], x["name"], x["checkIn"])
        have = {fkey(x) for x in tr["flights"]} | {hkey(x) for x in tr["hotels"]}
        add_f = [x for x in fl if fkey(x) not in have]
        add_h = [x for x in ho if hkey(x) not in have]
        if not (fl or ho):
            raise research.ResearchError("예약 정보를 찾지 못했어요. 이미지·메일 내용이 전부 들어갔는지 확인해 주세요.")
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
    for f in tr["flights"]:
        d = decorate(f)
        tag = "→".join(d["route"])
        for l in d["layovers"]:
            if l["minutes"] is None:
                continue
            if l["minutes"] < 0:
                issues.append(f"{tag}: {l['at']} 경유 시각이 앞뒤가 맞지 않아요. 도착·출발 시각을 확인해 주세요.")
            elif l["minutes"] < 60:
                issues.append(f"{tag}: {l['at']} 경유 시간이 {l['minutes']}분으로 짧아요.")
            if l["airportChange"]:
                issues.append(f"{tag}: {l['at']}에서 {l['to']}(으)로 공항이 바뀌어요. 이동 시간을 확인하세요.")
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
