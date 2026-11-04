"""폰이 내보낸 하루치 ZIP 가져오기와 하루 단위 작업 상태(전사·교정·요약) 저장.

저장 위치: trips/<id>/days/day<N>/{visits.json, state.json, audio/, photos/}
"""
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .store import Store, StoreError

VISITS_RE = re.compile(r"(^|/)days/day(\d{1,2})/visits\.json$")
SAFE_NAME = re.compile(r"^[\w][\w.\- ()]*$", re.UNICODE)
MAX_TOTAL = 6 * 1024**3  # 압축 해제 총량 상한(비정상 ZIP 방어)
CHECK_RE = re.compile(r"\[확인필요[:：]?\s*([^\]]*)\]")


def day_dir(store: Store, tid: str, n: int) -> Path:
    if not isinstance(n, int) or not 1 <= n <= 31:
        raise StoreError("일차가 올바르지 않아요.")
    return store._dir(tid) / "days" / f"day{n}"


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, obj) -> None:
    store_write = Store._write
    store_write(path, obj)


def get_visits(store, tid, n) -> dict | None:
    return _read(day_dir(store, tid, n) / "visits.json", None)


def get_state(store, tid, n) -> dict:
    st = _read(day_dir(store, tid, n) / "state.json", {})
    st.setdefault("recordings", {})
    st.setdefault("summary", "")
    st.setdefault("points", {})
    st.setdefault("tomorrow", None)
    return st


def save_state(store, tid, n, st) -> None:
    _write(day_dir(store, tid, n) / "state.json", st)


def import_zip(store: Store, tid: str, zip_path) -> list[dict]:
    """ZIP 안의 모든 일차를 풀어 넣는다. 이미 있는 전사·교정은 유지한다."""
    trip = store.get_trip(tid)
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise StoreError("ZIP 파일이 아니에요. 폰 앱의 '내보내기'로 만든 파일을 올려 주세요.") from e
    with zf:
        days = {}
        for name in zf.namelist():
            m = VISITS_RE.search(name)
            if m:
                days[int(m.group(2))] = name
        if not days:
            raise StoreError("하루치 데이터(days/dayN/visits.json)가 들어 있지 않아요. 폰 앱의 '내보내기'로 만든 ZIP인지 확인해 주세요.")
        if sum(i.file_size for i in zf.infolist()) > MAX_TOTAL:
            raise StoreError("압축을 풀면 너무 커요(6GB 초과).")
        results = []
        for n, vname in sorted(days.items()):
            try:
                visits = json.loads(zf.read(vname).decode("utf-8"))
            except ValueError as e:
                raise StoreError(f"{n}일차 visits.json 을 읽을 수 없어요.") from e
            if visits.get("tripId") != tid:
                raise StoreError(
                    f"다른 출장의 데이터예요('{visits.get('tripName', '?')}'). "
                    f"지금 선택한 출장('{trip['name']}')과 같은 패키지로 폰에 넣었던 데이터만 가져올 수 있어요.")
            d = day_dir(store, tid, n)
            prefix = vname[: -len("visits.json")]
            skipped = 0
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                rel = info.filename[len(prefix):]
                parts = rel.split("/")
                if len(parts) != 2 or parts[0] not in ("audio", "photos"):
                    continue
                if not SAFE_NAME.match(parts[1]):
                    skipped += 1
                    continue
                target = d / parts[0] / parts[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    while chunk := src.read(1 << 20):
                        out.write(chunk)
            _write(d / "visits.json", visits)
            st = get_state(store, tid, n)
            st["importedAt"] = datetime.now().isoformat(timespec="seconds")
            # 이번 ZIP에 없는 녹음의 전사는 남겨 두되, 있는 것은 그대로 유지한다
            save_state(store, tid, n, st)
            r = day_summary(store, tid, n)
            r["skippedFiles"] = skipped
            results.append(r)
    return results


def recordings_of(visits: dict) -> list[dict]:
    out = []
    for c in visits.get("companies", []):
        for r in c.get("recordings", []):
            out.append({**r, "companyId": c["id"], "companyName": c["name"]})
    return out


def day_summary(store, tid, n) -> dict:
    v = get_visits(store, tid, n)
    if not v:
        return {"day": n, "imported": False}
    st = get_state(store, tid, n)
    recs = recordings_of(v)
    comps = v.get("companies", [])
    transcribed = sum(1 for r in recs if st["recordings"].get(r["file"], {}).get("text"))
    corrected = sum(1 for r in recs if st["recordings"].get(r["file"], {}).get("corrected"))
    return {
        "day": n, "imported": True, "date": v.get("date"), "importedAt": st.get("importedAt"),
        "companies": len(comps), "visited": sum(1 for c in comps if c.get("visited")),
        "newCompanies": sum(1 for c in comps if c.get("addedOnSite")),
        "recordings": len(recs), "transcribed": transcribed, "corrected": corrected,
        "memos": sum(len(c.get("memos", [])) for c in comps), "photos": sum(len(c.get("photos", [])) for c in comps),
        "audioSeconds": sum(int(r.get("durationSec") or 0) for r in recs),
        "hasSummary": bool(st.get("summary")),
    }


def list_days(store, tid) -> list[dict]:
    trip = store.get_trip(tid)
    out = []
    for i, date in enumerate(trip["days"], start=1):
        s = day_summary(store, tid, i)
        s.setdefault("date", date)
        s["date"] = s.get("date") or date
        out.append(s)
    return out


def set_recording(store, tid, n, file, **fields) -> dict:
    v = get_visits(store, tid, n)
    if not v or not any(r["file"] == file for r in recordings_of(v)):
        raise StoreError("그 녹음을 찾을 수 없어요.")
    st = get_state(store, tid, n)
    rec = st["recordings"].setdefault(file, {})
    for k in ("text", "corrected"):
        if k in fields and isinstance(fields[k], str):
            rec[k] = fields[k].strip()
    if "text" in fields:
        rec["engine"] = rec.get("engine") or "수동 입력"
    save_state(store, tid, n, st)
    return rec


def file_path(store, tid, n, rel) -> Path:
    parts = rel.split("/")
    if len(parts) != 2 or parts[0] not in ("audio", "photos") or not SAFE_NAME.match(parts[1]):
        raise StoreError("파일을 찾을 수 없어요.")
    p = day_dir(store, tid, n) / parts[0] / parts[1]
    if not p.is_file():
        raise StoreError("파일을 찾을 수 없어요.")
    return p


def check_marks(text: str) -> list[str]:
    return [m.strip() or "확인 필요" for m in CHECK_RE.findall(text or "")]
