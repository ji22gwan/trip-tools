"""폰이 내보낸 하루치 ZIP 가져오기와 하루 단위 작업 상태(전사·교정·요약) 저장.

저장 위치: trips/<id>/days/day<N>/{visits.json, state.json, audio/, photos/}
"""
import io
import json
import re
import shutil
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
    st.setdefault("groups", {})  # 업체 id → {"category","group"}: AI 가 내용으로 판단한 분류
    st.setdefault("findings", [])  # 주요 조사 내용
    st.setdefault("tech", [])  # 기술별 조사 결과 표 행
    st.setdefault("opinion", [])  # 분류별 종합 의견
    st.setdefault("gaps", "")  # 오늘 미흡했던 부분(직접 적는 메모). 패키지로 폰 앱에 보낸다
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


IMG_RE = re.compile(r"\.(jpe?g|png|gif|webp)$", re.I)
MAX_FINAL = 2 * 1024**3


def save_final_zip(store, tid, n, zip_path) -> dict:
    """외부에서 고친 일간 보고서(.md + 사진 폴더) ZIP 을 그 일차의 '최종 보고서'로 저장한다. 이전 수정본은 대체된다."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise StoreError("ZIP 파일이 아니에요. '보고서.md' 와 photos 폴더가 든 ZIP 을 올려 주세요.") from e
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir() and not any(p.startswith(".") or p == "__MACOSX" for p in i.filename.split("/"))]
        mds = [i for i in infos if i.filename.lower().endswith(".md")]
        if not mds:
            raise StoreError("ZIP 안에 .md 보고서 파일이 없어요.")
        if sum(i.file_size for i in infos) > MAX_FINAL:
            raise StoreError("압축을 풀면 너무 커요(2GB 초과).")
        md = next((i for i in mds if i.filename.split("/")[-1] == "보고서.md"), None) or min(mds, key=lambda i: i.filename.count("/"))
        prefix = md.filename[: len(md.filename) - len(md.filename.split("/")[-1])]
        d = day_dir(store, tid, n) / "final"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        (d / "보고서.md").write_bytes(zf.read(md))
        photos = 0
        for i in infos:
            parts = i.filename[len(prefix):].split("/") if i.filename.startswith(prefix) else []
            if len(parts) != 2 or not SAFE_NAME.match(parts[0]) or not SAFE_NAME.match(parts[1]) or not IMG_RE.search(parts[1]):
                continue
            (d / parts[0]).mkdir(exist_ok=True)
            with zf.open(i) as src, open(d / parts[0] / parts[1], "wb") as out:
                shutil.copyfileobj(src, out)
            photos += 1
    st = get_state(store, tid, n)
    st["finalReport"] = {"at": datetime.now().isoformat(timespec="seconds"), "photos": photos}
    save_state(store, tid, n, st)
    return st["finalReport"]


def final_zip(store, tid, n) -> bytes | None:
    d = day_dir(store, tid, n) / "final"
    if not (d / "보고서.md").is_file():
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(d).as_posix())
    return buf.getvalue()


def clear_final(store, tid, n) -> None:
    shutil.rmtree(day_dir(store, tid, n) / "final", ignore_errors=True)
    st = get_state(store, tid, n)
    st.pop("finalReport", None)
    save_state(store, tid, n, st)


def check_marks(text: str) -> list[str]:
    return [m.strip() or "확인 필요" for m in CHECK_RE.findall(text or "")]
