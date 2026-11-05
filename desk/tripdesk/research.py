"""키워드로 AI 챗봇에 물어볼 프롬프트를 만들고, 돌아온 답을 후보 업체로 읽는다.

원칙
- Desk 는 AI 를 직접 부르지 않는다(API 키 불필요). 프롬프트를 복사해 AI 챗봇에 붙이고, 답을 다시 붙여 넣는다.
- 읽어 들인 업체는 '후보'(picked=False)로만 들어간다. 사용자가 체크한 것만 패키지에 들어간다.
- 모든 후보에 근거 URL 과 '확인됨' 여부를 붙여, AI 가 지어낸 업체를 걸러 낼 수 있게 한다.
"""
import json
import re
from datetime import date
import unicodedata
import uuid

from . import booths

MAX_ITEMS = 150
LEGAL = {"gmbh", "ag", "kg", "se", "co", "ltd", "llc", "inc", "corp", "corporation", "bv", "sa", "srl", "spa", "oy", "ab",
         "as", "kk", "limited", "company", "mbh", "ug", "sas", "plc", "pte"}


class ResearchError(Exception):
    pass


def norm_name(s: str) -> str:
    """대소문자·악센트·기호·법인 표기(GmbH 등)를 지운 비교용 이름."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace("&", " and ")
    toks = [t for t in re.split(r"[^\w]+", s, flags=re.UNICODE) if t and t not in LEGAL]
    return " ".join(toks)


def split_keywords(text: str) -> list[str]:
    out = []
    for k in re.split(r"[,\n;/、]+", text or ""):
        k = k.strip()
        if k and k not in out:
            out.append(k[:60])
    return out[:12]


def build_keyword_prompt(trip: dict, keywords: list[str], count: int = 20, site_url: str = "", exclude: list[str] | None = None) -> str:
    """AI 챗봇에 그대로 붙여 넣는 프롬프트. 답변 JSON 을 Desk 에 붙여 넣으면 읽을 수 있게 형식을 고정한다."""
    if not keywords:
        raise ResearchError("찾고 싶은 키워드를 한 개 이상 적어 주세요.")
    count = max(5, min(int(count or 20), 100))
    year = trip["days"][0][:4]
    kw = ", ".join(keywords)
    skip = ""
    if exclude:
        skip = "\nAlready on my list (do not repeat these): " + "; ".join(exclude[:60]) + "\n"
    purpose = (trip.get("purpose") or "").strip()
    today = date.today().isoformat()
    return f"""I am preparing a business visit to a trade fair. Find exhibitors of THIS edition that match my keywords.

Trade fair: {trip['name']} ({year})
Venue: {trip.get('venue') or 'unknown'}
Dates: {trip['days'][0]} to {trip['days'][-1]}
Official site (if known): {site_url or 'unknown'}
Keywords: {kw}
Why I am visiting (Korean, optional context): {purpose or '(not given)'}
{skip}
Task: use web search. Start from the official exhibitor directory / exhibitor search of this exact edition, then confirm with company pages or press releases. Give up to {count} companies, most relevant first. Do not return only literal keyword matches; build a varied list from these groups (roughly 50-60% from the first group, the rest spread over the others):
  1. [키워드] companies matching or closely related to my keywords.
  2. [글로벌] globally well-known companies in these fields (market leaders, major robot / automation / sensor / AI makers) that exhibit at this edition.
  3. [최근 이슈] companies that made big news in the last 12 months (before {today}), in Korea or abroad: new products, large funding, acquisitions, partnerships, major deployments or controversies.
  4. [행사] companies that run many events at this fair or have an important event there (keynotes, product launches, demos, conference talks, press events) according to the official programme or their own announcements.

Rules:
- If you cannot browse the web in this conversation, say so and stop. Do not answer from memory.
- "up to {count}" is a maximum, not a target: if fewer genuinely match, return fewer. If the full list would not fit in one reply, return fewer complete entries rather than cutting the JSON off.
- Never invent companies, hall numbers or booth numbers. Leave "hall" and "booth" empty when you did not see them in a source.
- Booths (required): list EVERY hall/booth of the company, one entry per booth in "booths": {{"hall":"5","booth":"5-210"}}. Return a company with several booths ONCE, with all its booths. Search result lists often show only one booth or just "N booths", so for every company open its detail page on the official site (the exhibitor's own page in the exhibitor directory) and copy all of its booths from there. Never stop at the first booth. If the page says "3 booths", "booths" must have 3 entries. Only if you truly cannot open the detail page after trying, list the booths you saw and add "(부스 N곳 중 일부 확인)" to the reason; do not drop the company for that. Do not repeat the company.
- Coverage: do not stop at the first page of one search. For each keyword also try 3-5 closely related search terms (synonyms, adjacent technologies, product names) and look at result pages 2-3 when page 1 is full. Fill up to {count}. If the list is short because most matches are already on my list (above), widen with related terms until you reach {count} NEW companies, or say in "notes" how many new ones exist and why you stopped.
- MUST EXCLUDE any company whose participation in this edition you could not confirm on the official site (the official exhibitor directory / exhibitor list of this exact edition). Do not list unconfirmed companies at all, even if they look relevant.
- INCLUDE companies that are similar or closely related to my keywords even when they do not fall perfectly into the keyword's category (adjacent technology, component or system suppliers). In "reason" say how it is similar, and in "matched" give the closest keyword. Rank exact matches first.
- "verified": must be true for every company you return (it was confirmed on the official site).
- "sourceUrl": the official-site page where you saw the company listed for this edition (required for every company).
- "category": a short Korean category name (at most 8 different categories overall, e.g. 휴머노이드, 협동로봇, 용접 자동화, 비전·센서). Use the same name for similar companies.
- "reason": one Korean sentence, starting with the group label in brackets ([키워드], [글로벌], [최근 이슈] or [행사]), saying why this company is worth visiting; for [최근 이슈] and [행사] name the news or event briefly. A company can have several labels. Keep the variety of categories wide; do not fill the list with many near-identical companies.
- "matched": which of my keywords it matched.

Reply with ONLY one JSON object in a ```json code block and nothing else, so I can paste it into another tool:
{{"companies":[{{"name":"","category":"","booths":[{{"hall":"","booth":""}}],"reason":"","matched":[""],"sourceUrl":"","verified":true}}],"notes":"Korean, 1-3 sentences: sources used and what you could not confirm"}}"""


def extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text or "", re.S) or re.search(r"(\{.*\})", text or "", re.S)
    if not m:
        raise ResearchError("붙여 넣은 내용에서 결과(JSON)를 찾지 못했어요. AI 답변 전체를 복사해 붙여 넣었는지 확인해 주세요.")
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        raise ResearchError("JSON 형식이 깨져 있어요. 답변이 중간에 끊기지 않았는지 확인하거나 '이어서 전체 JSON 다시 보여줘'라고 요청해 보세요.") from e


def _s(v, n) -> str:
    return str(v or "").strip()[:n]


def sanitize(data: dict) -> tuple[list[dict], str]:
    items, seen = [], set()
    for c in data.get("companies") or []:
        if not isinstance(c, dict):
            continue
        name = _s(c.get("name"), 120)
        key = norm_name(name)
        if not name or not key or key in seen:
            continue
        seen.add(key)
        url = _s(c.get("sourceUrl"), 500)
        ok_url = bool(re.match(r"^https?://", url))
        matched = c.get("matched") if isinstance(c.get("matched"), list) else []
        items.append({
            "name": name,
            "category": _s(c.get("category"), 30) or "기타",
            "booths": booths.clean(c["booths"]) if isinstance(c.get("booths"), list) and c["booths"] else booths.parse(c.get("hall"), c.get("booth")),
            "reason": _s(c.get("reason"), 300),
            "matched": [_s(k, 40) for k in matched if _s(k, 40)][:6],
            "sourceUrl": url if ok_url else "",
            "verified": c.get("verified") is True and ok_url,  # 근거 주소 없는 '확인됨'은 인정하지 않는다
        })
        if len(items) >= MAX_ITEMS:
            break
    return items, _s(data.get("notes"), 600)


def add_candidates(existing: list[dict], items: list[dict], keywords: list[str]) -> tuple[list[dict], int, int]:
    """후보를 업체 목록에 '미선택' 상태로 넣는다. 이미 있는 업체는 건드리지 않고 키워드만 보탠다."""
    have = {norm_name(c["name"]): c for c in existing}
    added = skipped = 0
    for it in items:
        key = norm_name(it["name"])
        prev = have.get(key)
        kws = list(dict.fromkeys(it.get("matched") or keywords))
        if prev:
            prev["keywords"] = list(dict.fromkeys((prev.get("keywords") or []) + kws))
            booths.merge_into(prev, it["booths"])
            skipped += 1
            continue
        c = {
            "id": "c-" + uuid.uuid4().hex[:8], "name": it["name"], "category": it["category"], "booths": it["booths"],
            "day": None, "preNotes": "", "questions": [], "picked": False, "source": "ai",
            "reason": it["reason"], "sourceUrl": it["sourceUrl"], "verified": it["verified"], "keywords": kws,
        }
        existing.append(c)
        have[key] = c
        added += 1
    return existing, added, skipped


def package_note(c: dict) -> str:
    """폰에 보낼 사전 메모: 사용자가 쓴 메모 + AI 가 적은 이유와 출처."""
    parts = [c.get("preNotes", "").strip()]
    if c.get("reason"):
        parts.append(c["reason"])
    if c.get("sourceUrl"):
        parts.append("출처: " + c["sourceUrl"])
    if c.get("source") == "ai" and not c.get("verified"):
        parts.append("(AI 추정 · 참가 여부 확인 필요)")
    return "\n".join(p for p in parts if p)
