"""전시회 기간의 세미나·컨퍼런스·토론회(세션). 공식 프로그램 페이지를 AI 챗봇으로 조사해 붙여 넣고, 갈 것을 골라 패키지에 담는다."""
import hashlib
import re

from .research import ResearchError, extract_json, norm_name

HM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _s(x, n=200) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def _hm(x) -> str:
    x = _s(x, 8)
    m = HM.match(x)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def key(s: dict) -> str:
    return f"{norm_name(s['title'])}|{s['date']}|{s['start']}"


def clean_one(c: dict, days: list[str] | None = None, keep_id: bool = True) -> dict | None:
    if not isinstance(c, dict):
        return None
    title, date = _s(c.get("title"), 160), _s(c.get("date"), 10)
    if not title or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return None
    if days and date not in days:
        return None
    url = _s(c.get("sourceUrl"), 500)
    ok = bool(re.match(r"^https?://", url))
    s = {"id": "", "title": title, "date": date, "start": _hm(c.get("start")), "end": _hm(c.get("end")),
         "place": _s(c.get("place"), 120), "hall": _s(c.get("hall"), 12), "speaker": _s(c.get("speaker"), 160),
         "topic": _s(c.get("topic"), 300), "sourceUrl": url if ok else "", "verified": c.get("verified") is True and ok,
         "source": _s(c.get("source"), 10) or "manual"}
    s["id"] = _s(c.get("id"), 40) if keep_id and c.get("id") else "s-" + hashlib.sha1(key(s).encode()).hexdigest()[:8]
    return s


def clean_all(items, days=None) -> list[dict]:
    out, seen = [], set()
    for c in items or []:
        s = clean_one(c, days)
        if s and s["id"] not in seen:
            seen.add(s["id"])
            out.append(s)
    return sorted(out, key=lambda s: (s["date"], s["start"] or "99:99", s["title"]))


def build_prompt(trip: dict, site_url: str = "", exclude: list[str] | None = None) -> str:
    skip = ("\nAlready on my list (do not repeat): " + "; ".join(exclude[:60]) + "\n") if exclude else ""
    return f"""I am visiting a trade fair. List the conference sessions, seminars, talks, panel discussions and similar programme items held during THIS edition, from the official programme / event schedule.

Trade fair: {trip['name']} ({trip['days'][0][:4]})
Venue: {trip.get('venue') or 'unknown'}
Dates: {trip['days'][0]} to {trip['days'][-1]}
Official site (if known): {site_url or 'unknown'}
Why I am visiting (Korean, optional context): {(trip.get('purpose') or '').strip() or '(not given)'}
{skip}
Task: use web search and open the official programme / agenda / forum pages of this exact edition. Prefer sessions relevant to my purpose, but list all items you can confirm if fewer than 40.

Rules:
- If you cannot browse the web in this conversation, say so and stop. Do not answer from memory.
- Never invent sessions, times or places. Leave a field empty when the official page does not show it.
- Include ONLY items you saw on the official site; "sourceUrl" is required and "verified" must be true.
- "date" is YYYY-MM-DD, "start"/"end" are 24-hour local times HH:MM at the venue.
- "place": stage / forum / room name; "hall": hall number only (e.g. 3A) if shown.
- "title" and "topic": keep the original language of the programme, and add a short Korean summary in "topic".
- If the full list would not fit in one reply, return fewer complete entries rather than cutting the JSON off.

Reply with ONLY one JSON object in a ```json code block and nothing else:
{{"sessions":[{{"title":"","date":"","start":"","end":"","place":"","hall":"","speaker":"","topic":"","sourceUrl":"","verified":true}}],"notes":"Korean, 1-3 sentences: sources used and what you could not confirm"}}"""


def apply_reply(text: str, existing: list[dict], days: list[str]) -> tuple[list[dict], dict]:
    data = extract_json(text)
    raw = data.get("sessions")
    if not isinstance(raw, list) or not raw:
        raise ResearchError("답변에서 세션 목록을 찾지 못했어요. 프롬프트가 요구한 JSON 형식인지 확인해 주세요.")
    have = {key(s) for s in existing}
    merged, added, dup, outside = list(existing), 0, 0, 0
    for c in raw:
        if isinstance(c, dict) and days and _s(c.get("date"), 10) not in days:
            outside += 1
            continue
        s = clean_one({**c, "source": "ai"}, days, keep_id=False) if isinstance(c, dict) else None
        if not s:
            continue
        if key(s) in have:
            dup += 1
            continue
        have.add(key(s))
        merged.append(s)
        added += 1
    if not added and not dup:
        raise ResearchError("반영할 세션이 없어요. 날짜(YYYY-MM-DD)와 제목이 들어 있는지 확인해 주세요.")
    return clean_all(merged), {"added": added, "existing": dup, "outside": outside, "notes": _s(data.get("notes"), 300),
                              "unverified": sum(1 for c in raw if isinstance(c, dict) and c.get("verified") is not True)}
