"""한 업체가 부스를 여러 곳에 갖는 경우.

업체(체크박스 1개)는 booths 목록을 가진다: [{"hall": "5", "booth": "5-210", "day": 1}, ...]
호환을 위해 hall / booth / day 는 첫 번째 부스 값을 따라간다.
일정 배분·폰 패키지는 부스 하나를 '방문 한 곳(stop)'으로 본다. 첫 부스는 업체 id 를 그대로 쓰고, 나머지는 'c-xxxx#2' 처럼 번호를 붙인다.
"""
import re

SPLIT = re.compile(r"[,;/\n、·]+")


def _t(v, n=24) -> str:
    return str(v if v is not None else "").strip()[:n]


def _hall_of(booth: str) -> str:
    m = re.match(r"^([0-9]+[A-Za-z]?)\s*[-.]", booth)
    return m.group(1) if m else ""


def parse(hall="", booth="") -> list[dict]:
    """'5-210, 6-350G' 같은 문자열을 부스 목록으로 나눈다. 홀이 따로 같은 개수로 있으면 짝지어 쓰고, 없으면 부스 번호 앞부분에서 짐작한다."""
    bs = [x.strip() for x in SPLIT.split(_t(booth, 200)) if x.strip()]
    hs = [x.strip() for x in SPLIT.split(_t(hall, 200)) if x.strip()]
    if not bs:
        return [{"hall": h, "booth": "", "day": None} for h in hs] or [{"hall": "", "booth": "", "day": None}]
    out = []
    for i, b in enumerate(bs):
        h = hs[i] if len(hs) == len(bs) else (hs[0] if len(hs) == 1 else _hall_of(b))
        out.append({"hall": _t(h, 12), "booth": _t(b, 24), "day": None})
    return out


def clean(booths) -> list[dict]:
    out, seen = [], set()
    for b in booths or []:
        if not isinstance(b, dict):
            continue
        k = (_t(b.get("hall"), 12), _t(b.get("booth"), 24))
        if k in seen:
            continue
        seen.add(k)
        d = b.get("day")
        out.append({"hall": k[0], "booth": k[1], "day": d if isinstance(d, int) and not isinstance(d, bool) and d > 0 else None})
        if len(out) >= 12:
            break
    return out or [{"hall": "", "booth": "", "day": None}]


def norm(c: dict) -> dict:
    """업체 dict 에 booths 를 보장하고, hall/booth/day 를 첫 부스에 맞춘다."""
    if isinstance(c.get("booths"), list) and c["booths"]:
        bs = clean(c["booths"])
    else:
        bs = parse(c.get("hall"), c.get("booth"))
        if len(bs) == 1 and isinstance(c.get("day"), int):
            bs[0]["day"] = c["day"]
    c["booths"] = bs
    c["hall"], c["booth"], c["day"] = bs[0]["hall"], bs[0]["booth"], bs[0]["day"]
    return c


def base_id(i: str) -> str:
    return str(i).split("#")[0]


def stops(c: dict) -> list[dict]:
    """업체를 방문 지점(부스)별로 펼친다. 각 항목: id, companyId, hall, booth, day, index."""
    norm(c)
    return [{"id": c["id"] if i == 0 else f"{c['id']}#{i + 1}", "companyId": c["id"], "index": i, "hall": b["hall"], "booth": b["booth"], "day": b["day"]}
            for i, b in enumerate(c["booths"])]


def label(hall: str, booth: str) -> str:
    return " ".join(x for x in (hall, booth) if x).strip()


def merge_into(prev: dict, incoming: list[dict]) -> None:
    """이미 있는 업체에 새 부스를 합친다(같은 홀·부스는 건너뜀). 빈 부스 한 칸만 있으면 채워 넣는다."""
    norm(prev)
    have = {(b["hall"], b["booth"]) for b in prev["booths"]}
    for b in clean(incoming):
        if not (b["hall"] or b["booth"]) or (b["hall"], b["booth"]) in have:
            continue
        if len(prev["booths"]) == 1 and not (prev["booths"][0]["hall"] or prev["booths"][0]["booth"]):
            day = prev["booths"][0]["day"]
            prev["booths"][0] = dict(b, day=day)
        else:
            prev["booths"].append(b)
        have.add((b["hall"], b["booth"]))
    norm(prev)
