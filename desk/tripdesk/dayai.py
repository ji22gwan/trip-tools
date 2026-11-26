"""하루 녹음의 교정·요약용 AI 챗봇 프롬프트를 만들고, 돌아온 답을 반영한다(API 키 불필요)."""
import re

from .research import ResearchError, extract_json, norm_name

MAX_CHARS = 36000


def _company_block(c: dict, plan: dict | None, state: dict) -> str:
    lines = [f'### COMPANY id={c["id"]} name="{c["name"]}" category="{c.get("category", "")}" hall/booth={c.get("hall", "")}/{c.get("booth", "")}']
    if plan:
        note = "; ".join(x for x in [plan.get("preNotes", "").strip().replace("\n", " "), plan.get("reason", "")] if x)
        if note:
            lines.append(f"Pre-visit notes: {note}")
        if plan.get("questions"):
            lines.append("Questions I wanted to ask: " + " | ".join(plan["questions"]))
    for r in c.get("recordings", []):
        text = state["recordings"].get(r["file"], {}).get("text", "").strip()
        if not text:
            continue
        lines.append(f'RECORDING file="{r["file"]}" time={r.get("at", "")[11:16]} length={r.get("durationSec", 0)}s')
        lines.append(text)
    memos = c.get("memos", [])
    if memos:
        lines.append("My own memos (context only; do not rewrite or copy them): " + " / ".join(m["text"].replace("\n", " ") for m in memos))
    return "\n".join(lines)


def build_prompts(trip: dict, day: int, visits: dict, state: dict, glossary: list[str], plan: list[dict]) -> list[str]:
    plan_by_id = {p["id"]: p for p in plan}
    blocks = []
    for c in visits.get("companies", []):
        if any(state["recordings"].get(r["file"], {}).get("text") for r in c.get("recordings", [])):
            blocks.append(_company_block(c, plan_by_id.get(c["id"]), state))
    if not blocks:
        raise ResearchError("전사된 녹음이 없어요. 먼저 전사(또는 직접 입력)를 해 주세요.")
    parts, cur, size = [], [], 0
    for b in blocks:
        if cur and size + len(b) > MAX_CHARS:
            parts.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b)
    parts.append(cur)
    head = f"""You are helping an engineer clean up speech-recognition transcripts of conversations held at a trade fair booth.

Fair: {trip['name']} - day {day} ({visits.get('date') or ''}). The conversations are mostly Korean with English/German technical terms.
Glossary of terms the speech recognizer often gets wrong (use these spellings): {', '.join(glossary) if glossary else '(none)'}

Tasks, for every RECORDING below:
1. "corrected": the transcript with obvious recognition errors fixed using the glossary, company names and pre-visit notes. Keep the speaker's meaning and wording. Normalize spoken numbers and units (e.g. "이십 킬로" -> "20kg").
   - Wrap every term or number you changed in double curly braces, e.g. {{{{20kg}}}}, {{{{EtherCAT}}}}.
   - If a word or number is unclear and you are not sure, do NOT guess: write [확인필요: option A / option B].
2. For every COMPANY:
   - "points": Korean notes in 개조식 (terse bullet phrases, not paragraphs, not a table), at most 12, stating only facts that were actually said in its recordings (specs, prices, lead times, compatibility, follow-ups). End each bullet with a period. Put "추가 확인 필요" on facts that are still open. Keep the bullets short so that photos can be placed under each company.
   - "category": judge from the CONTENT of the conversation (not just the category label I typed) which broad technology/business area the company belongs to, e.g. "Vision & Sensor", "Teach Pendant & HMI", "Digital Twin & OLP", "Industrial PC & Control", "Robotics & Welding". Use the SAME category name for companies of the same area, so the report can group them.
   - "group": optional finer sub-group inside the category (e.g. "Laser Profile & Seam Sensing", "3D Vision & AI"); "" if not needed.
3. Across the day: "findings" = 3-6 Korean bullets of the main things investigated today (the purpose of the visits, in 개조식); "tech" = rows of the technologies investigated: {{"tech":"","companies":["short names"],"review":"what to examine"}}; "opinion" = per category 1-4 Korean bullets of overall remarks drawn only from the conversations.
Voice: write the bullets like a 20-year field engineer who also develops the control software: concrete specs first, then what it means for a shipyard welding line (what is different from conventional touch sensing / fixed sensors / wired pendants, what must be verified: arc, fume, spatter, weight, interface, price). No brochure tone. Do NOT start bullets with labels such as "면담:", "조사:", "현장:", "적용:". Keep what the company said separate from my own judgment by putting my judgment in a bullet that begins with "판단".
Never add facts, numbers or names that are not in the transcript. Do not touch my memos.
"""
    prompts = []
    for i, part in enumerate(parts, start=1):
        label = f"\n(Part {i} of {len(parts)}. Answer only for the companies in this part.)\n" if len(parts) > 1 else ""
        tail = """
Reply with ONLY one JSON object in a ```json code block, nothing else, so I can paste it into another tool:
{"recordings":[{"file":"<the exact file value>","corrected":""}],"companies":[{"id":"<the exact id>","category":"","group":"","points":[""]}],"summary":"2-3 Korean sentences summarizing this part of the day","findings":[""],"tech":[{"tech":"","companies":[""],"review":""}],"opinion":[{"category":"","bullets":[""]}]}
"""
        prompts.append(head + label + "\n--- DATA ---\n" + "\n\n".join(part) + "\n--- END ---\n" + tail)
    return prompts


def _merge_lists(state: dict, data: dict, mode: str) -> None:
    """findings / tech / opinion 을 반영한다. 여러 조각(append)이면 이어 붙이고 같은 항목은 한 번만 둔다."""
    txt = lambda x: str(x).strip()
    found = [txt(x) for x in data.get("findings") or [] if txt(x)][:10]
    tech = [{"tech": txt(t.get("tech")), "companies": [txt(c) for c in t.get("companies") or [] if txt(c)][:8], "review": txt(t.get("review"))}
            for t in data.get("tech") or [] if isinstance(t, dict) and txt(t.get("tech"))][:20]
    opin = [{"category": txt(o.get("category")), "bullets": [txt(b) for b in o.get("bullets") or [] if txt(b)][:6]}
            for o in data.get("opinion") or [] if isinstance(o, dict) and txt(o.get("category")) and o.get("bullets")][:12]
    for key, new, ident in (("findings", found, lambda x: x), ("tech", tech, lambda x: x["tech"]), ("opinion", opin, lambda x: x["category"])):
        if not new:
            continue
        old = state.get(key, []) if mode == "append" else []
        seen = {ident(x) for x in old}
        state[key] = old + [x for x in new if ident(x) not in seen]


def apply_reply(text: str, visits: dict, state: dict, mode: str = "replace") -> dict:
    """답변 JSON 을 상태에 반영한다. 모르는 파일·업체 id 는 무시하고 개수를 알려 준다."""
    data = extract_json(text)
    files = {r["file"] for c in visits.get("companies", []) for r in c.get("recordings", [])}
    ids = {c["id"]: c for c in visits.get("companies", [])}
    by_name = {norm_name(c["name"]): c["id"] for c in visits.get("companies", [])}
    n_rec = n_pts = ignored = 0
    for r in data.get("recordings") or []:
        if isinstance(r, dict) and r.get("file") in files and str(r.get("corrected") or "").strip():
            state["recordings"].setdefault(r["file"], {})["corrected"] = str(r["corrected"]).strip()
            n_rec += 1
        else:
            ignored += 1
    for c in data.get("companies") or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") if c.get("id") in ids else by_name.get(norm_name(c.get("name", "")))
        pts = [str(p).strip() for p in (c.get("points") or []) if str(p).strip()]
        if cid and pts:
            state["points"][cid] = pts[:12]
            n_pts += 1
            cat, grp = str(c.get("category") or "").strip()[:60], str(c.get("group") or "").strip()[:60]
            if cat:
                state.setdefault("groups", {})[cid] = {"category": cat, "group": grp}
        elif not cid:
            ignored += 1
    s = str(data.get("summary") or "").strip()
    if s:
        state["summary"] = (state["summary"] + " " + s).strip() if mode == "append" and state.get("summary") else s
    _merge_lists(state, data, mode)
    if not (n_rec or n_pts or s):
        raise ResearchError("답변에서 반영할 내용을 찾지 못했어요. 프롬프트의 file/id 값이 그대로 들어 있는지 확인해 주세요.")
    return {"recordings": n_rec, "companies": n_pts, "ignored": ignored, "summary": bool(s)}


def build_final_prompt(trip: dict, report: dict) -> str:
    lines = []
    for d in report["days"]:
        lines.append(f'## Day {d["day"]} ({d["date"]})\nSummary: {d["summary"]}')
        for c in d["companies"]:
            pts = " / ".join(c["points"]) or "(no AI points)"
            lines.append(f'- {c["name"]} [{c["category"]}]: {pts}')
            for m in c["memos"]:
                lines.append(f'    my memo: {m["text"]}')
    return f"""I attended the trade fair "{trip['name']}". Purpose of the visit (Korean): {trip.get('purpose') or '(not given)'}
Below are my daily summaries and per-company notes. Write the overall conclusion for my final trip report, in Korean.

{chr(10).join(lines)}

Rules: use only what is written above; do not invent facts. Mark anything uncertain with [확인필요: ...].
Reply with ONLY one JSON object in a ```json code block:
{{"overview":"4-6 Korean sentences: what was learned relative to the purpose","highlights":["up to 6 Korean bullets: the most promising companies/technologies and why"],"followups":["up to 6 Korean bullets: concrete follow-up actions"]}}"""


def apply_final(text: str) -> dict:
    d = extract_json(text)
    out = {
        "overview": str(d.get("overview") or "").strip(),
        "highlights": [str(x).strip() for x in d.get("highlights") or [] if str(x).strip()][:10],
        "followups": [str(x).strip() for x in d.get("followups") or [] if str(x).strip()][:10],
    }
    if not (out["overview"] or out["highlights"] or out["followups"]):
        raise ResearchError("답변에서 총평 내용을 찾지 못했어요.")
    return out
