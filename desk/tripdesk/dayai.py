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
2. For every COMPANY: "points" = at most 5 short Korean bullet sentences stating only facts that were actually said in its recordings (specs, prices, lead times, follow-ups). Add [확인필요: ...] where a fact is uncertain.
Never add facts, numbers or names that are not in the transcript. Do not touch my memos.
"""
    prompts = []
    for i, part in enumerate(parts, start=1):
        label = f"\n(Part {i} of {len(parts)}. Answer only for the companies in this part.)\n" if len(parts) > 1 else ""
        tail = """
Reply with ONLY one JSON object in a ```json code block, nothing else, so I can paste it into another tool:
{"recordings":[{"file":"<the exact file value>","corrected":""}],"companies":[{"id":"<the exact id>","points":[""]}],"summary":"2-3 Korean sentences summarizing this part of the day"}
"""
        prompts.append(head + label + "\n--- DATA ---\n" + "\n\n".join(part) + "\n--- END ---\n" + tail)
    return prompts


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
            state["points"][cid] = pts[:8]
            n_pts += 1
        elif not cid:
            ignored += 1
    s = str(data.get("summary") or "").strip()
    if s:
        state["summary"] = (state["summary"] + " " + s).strip() if mode == "append" and state.get("summary") else s
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
