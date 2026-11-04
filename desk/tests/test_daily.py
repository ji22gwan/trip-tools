import io
import json
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest

from tripdesk import daily, dayai, reports, server, transcribe
from tripdesk.store import StoreError

JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def make_trip(store):
    t = store.create_trip("SPS 2026", "Nuremberg", "2026-11-24", "2026-11-26", "휴머노이드 조사")
    store.set_companies(t["id"], [
        {"id": "c-a", "name": "Alpha Robotics", "category": "휴머노이드", "hall": "3A", "booth": "118", "day": 1, "preNotes": "페이로드 확인", "questions": ["납기"], "picked": True},
        {"id": "c-b", "name": "Beta Weld", "category": "용접", "hall": "4", "booth": "2", "day": 1, "preNotes": "", "questions": [], "picked": True},
        {"id": "c-c", "name": "Gamma Vision", "category": "비전", "hall": "", "booth": "", "day": 2, "preNotes": "", "questions": [], "picked": True},
        {"id": "c-x", "name": "Skipped Co", "category": "기타", "hall": "", "booth": "", "day": 1, "preNotes": "", "questions": [], "picked": False},
    ])
    store.set_glossary(t["id"], ["EtherCAT", "payload"])
    return t


def day_zip(tid, day=1, extra=None, trip_id=None):
    visits = {
        "schema": 1, "tripId": trip_id or tid, "tripName": "SPS 2026", "venue": "Nuremberg", "day": day, "date": "2026-11-24", "tzOffsetMin": 60,
        "companies": [
            {"id": "c-a", "name": "Alpha Robotics", "category": "휴머노이드", "hall": "3A", "booth": "118", "addedOnSite": False, "visited": True,
             "recordings": [{"file": "audio/alpha_1024_01.m4a", "at": "2026-11-24T10:24:00.000Z", "durationSec": 192, "mime": "audio/mp4"}],
             "memos": [{"text": "납기는 직접 다시 확인  <b>x</b>", "important": True, "at": "2026-11-24T10:30:00.000Z"}],
             "photos": [{"file": "photos/alpha_1030_01.jpg", "at": "2026-11-24T10:30:00.000Z"}]},
            {"id": "c-g", "name": "Gadget Neu", "category": "기타", "addedOnSite": True, "visited": True, "recordings": [], "memos": [{"text": "명함 받음", "important": False, "at": "2026-11-24T14:00:00.000Z"}], "photos": []},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        base = f"trip_SPS_2026/days/day{day}/"
        z.writestr(base + "visits.json", json.dumps(visits))
        z.writestr(base + "audio/alpha_1024_01.m4a", b"fakeaudio")
        z.writestr(base + "photos/alpha_1030_01.jpg", JPG)
        z.writestr(base + "audio/../../evil.txt", b"x")  # 경로 탈출
        z.writestr(base + "photos/.hidden", b"x")
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    p = buf.getvalue()
    return p


@pytest.fixture
def zpath(tmp_path):
    def mk(data):
        p = tmp_path / "d.zip"
        p.write_bytes(data)
        return p
    return mk


def test_import_extracts_safely_and_keeps_state(store, zpath):
    t = make_trip(store)
    res = daily.import_zip(store, t["id"], zpath(day_zip(t["id"])))
    assert res[0]["day"] == 1 and res[0]["companies"] == 2 and res[0]["recordings"] == 1 and res[0]["newCompanies"] == 1
    d = daily.day_dir(store, t["id"], 1)
    assert (d / "audio" / "alpha_1024_01.m4a").read_bytes() == b"fakeaudio"
    assert not (store._dir(t["id"]) / "evil.txt").exists() and not (d / "photos" / ".hidden").exists()
    daily.set_recording(store, t["id"], 1, "audio/alpha_1024_01.m4a", text="수정한 전사")
    daily.import_zip(store, t["id"], zpath(day_zip(t["id"])))  # 다시 가져와도 전사는 남는다
    assert daily.get_state(store, t["id"], 1)["recordings"]["audio/alpha_1024_01.m4a"]["text"] == "수정한 전사"


def test_import_rejects_wrong_trip_and_non_exports(store, zpath):
    t = make_trip(store)
    with pytest.raises(StoreError, match="다른 출장"):
        daily.import_zip(store, t["id"], zpath(day_zip(t["id"], trip_id="trip-deadbeef")))
    with pytest.raises(StoreError, match="ZIP"):
        daily.import_zip(store, t["id"], zpath(b"not a zip"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(StoreError, match="visits.json"):
        daily.import_zip(store, t["id"], zpath(buf.getvalue()))
    with pytest.raises(StoreError):
        daily.file_path(store, t["id"], 1, "audio/../../trip.json")


def run_transcribe(store, t, redo=False, fail=None):
    visits = daily.get_visits(store, t["id"], 1)
    st = daily.get_state(store, t["id"], 1)
    msgs = []
    out = transcribe.run_day(visits, st, lambda f: daily.file_path(store, t["id"], 1, f), "ko", "EtherCAT", "small", redo,
                             msgs.append, lambda: daily.save_state(store, t["id"], 1, st))
    return out, msgs, st


def test_transcribe_with_stub_skips_done_and_survives_errors(store, zpath):
    t = make_trip(store)
    daily.import_zip(store, t["id"], zpath(day_zip(t["id"])))
    seen = []
    transcribe.set_backend(lambda path, lang, prompt, model: seen.append((lang, prompt, model)) or "페이로드는 이십 킬로")
    try:
        (done, errors), msgs, st = run_transcribe(store, t)
        assert done == 1 and errors == [] and seen == [("ko", "EtherCAT", "small")]
        assert daily.day_summary(store, t["id"], 1)["transcribed"] == 1
        (done2, _), _, _ = run_transcribe(store, t)
        assert done2 == 0  # 이미 있는 전사는 다시 돌리지 않는다
        (done3, _), _, _ = run_transcribe(store, t, redo=True)
        assert done3 == 1
        transcribe.set_backend(lambda *a: (_ for _ in ()).throw(transcribe.TranscribeError("모델 준비 실패")))
        (done4, errors4), _, _ = run_transcribe(store, t, redo=True)
        assert done4 == 0 and "모델 준비 실패" in errors4[0]
    finally:
        transcribe.set_backend(None)


def test_availability_message_without_engine():
    ok, why = transcribe.available()
    if not ok:
        assert "faster-whisper" in why and "직접" in why


REPLY = {
    "recordings": [{"file": "audio/alpha_1024_01.m4a", "corrected": "페이로드는 {{20kg}} 정도이고 {{EtherCAT}} 지원, 납기는 [확인필요: 5개월 / 6개월]"},
                   {"file": "audio/unknown.m4a", "corrected": "무시"}],
    "companies": [{"id": "c-a", "points": ["페이로드 약 20kg", "납기 [확인필요: 5~6개월]"]}, {"id": "zzz", "points": ["무시"]}],
    "summary": "휴머노이드 업체에서 사양을 확인했다.",
}


def prep(store, zpath):
    t = make_trip(store)
    daily.import_zip(store, t["id"], zpath(day_zip(t["id"])))
    daily.set_recording(store, t["id"], 1, "audio/alpha_1024_01.m4a", text="페이로드는 이십 킬로 정도고 이더켓 지원")
    return t


def test_prompt_contains_glossary_notes_and_ids(store, zpath):
    t = prep(store, zpath)
    ps = dayai.build_prompts(store.get_trip(t["id"]), 1, daily.get_visits(store, t["id"], 1), daily.get_state(store, t["id"], 1),
                             store.get_glossary(t["id"]), store.get_companies(t["id"]))
    assert len(ps) == 1
    p = ps[0]
    assert "EtherCAT, payload" in p and 'id=c-a' in p and "audio/alpha_1024_01.m4a" in p and "이십 킬로" in p
    assert "페이로드 확인" in p and "납기" in p and "do not rewrite" in p and "Gadget Neu" not in p  # 전사 없는 업체는 빠진다
    with pytest.raises(Exception, match="전사된 녹음이 없어요"):
        dayai.build_prompts({"name": "x"}, 1, {"companies": [], "date": ""}, {"recordings": {}}, [], [])


def test_apply_reply_and_report(store, zpath):
    t = prep(store, zpath)
    visits = daily.get_visits(store, t["id"], 1)
    st = daily.get_state(store, t["id"], 1)
    res = dayai.apply_reply("답변\n```json\n" + json.dumps(REPLY, ensure_ascii=False) + "\n```", visits, st)
    assert res["recordings"] == 1 and res["companies"] == 1 and res["ignored"] == 2 and res["summary"]
    daily.save_state(store, t["id"], 1, st)
    r = reports.build_day(store, t["id"], 1)
    a = r["companies"][0]
    assert a["points"][0] == "페이로드 약 20kg" and r["summary"].startswith("휴머노이드") and r["summaryIsAi"]
    assert [c["text"] for c in r["checks"]] == ["5개월 / 6개월", "5~6개월"]
    assert a["memos"][0]["text"].startswith("납기는 직접 다시 확인")  # 내 메모는 원문 그대로
    assert a["recordings"][0]["time"] == "11:24" and a["memos"][0]["time"] == "11:30"  # UTC 10:24 → 폰이 있던 곳(+60분)의 시각
    assert reports.local_hm("2026-11-24T10:24:00.000Z", None) == "10:24 UTC"  # 오프셋 기록이 없으면 UTC 로 밝혀서 표시
    assert r["companies"][1]["addedOnSite"] is True
    # 내일 계획: 2일차로 배정된 업체. Skipped Co(미선택)는 빠진다. 오늘 못 간 업체는 재조정 안내.
    assert "Gamma Vision" in r["tomorrow"] and "Skipped" not in r["tomorrow"]
    assert "Beta Weld" in r["tomorrow"]
    md = reports.day_markdown(r)
    assert "페이로드는 20kg 정도이고 EtherCAT" in md or "페이로드 약 20kg" in md
    assert "{{" not in md and "> ★ 납기는 직접 다시 확인" in md and "## 확인 필요" in md
    # 미리보기 문장은 사용자가 고친 것이 우선이고, None 으로 자동 문장으로 되돌린다
    st = daily.get_state(store, t["id"], 1)
    st["tomorrow"] = "직접 쓴 계획"
    daily.save_state(store, t["id"], 1, st)
    assert reports.build_day(store, t["id"], 1)["tomorrow"] == "직접 쓴 계획"


def test_report_without_ai_falls_back_to_transcript(store, zpath):
    t = prep(store, zpath)
    r = reports.build_day(store, t["id"], 1)
    assert not r["summaryIsAi"] and "2곳 방문(현장 추가 1곳)" in r["summary"]
    md = reports.day_markdown(r)
    assert "전사 원문" in md and "이십 킬로" in md  # AI 정리가 없으면 원문을 그대로 보여 준다(지어내지 않는다)


def test_docx_and_final(store, zpath):
    docx = pytest.importorskip("docx")
    t = prep(store, zpath)
    st = daily.get_state(store, t["id"], 1)
    dayai.apply_reply("```json\n" + json.dumps(REPLY, ensure_ascii=False) + "\n```", daily.get_visits(store, t["id"], 1), st)
    daily.save_state(store, t["id"], 1, st)
    r = reports.build_day(store, t["id"], 1)
    data = reports.day_docx(store, t["id"], r)
    text = "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    assert "페이로드 약 20kg" in text and "납기는 직접 다시 확인" in text and "[확인필요: 5~6개월]" in text
    fr = reports.build_final(store, t["id"])
    assert fr["totals"]["companies"] == 2 and fr["notVisited"] == ["Beta Weld", "Gamma Vision"]
    p = dayai.build_final_prompt(store.get_trip(t["id"]), fr)
    assert "Alpha Robotics" in p and "페이로드 약 20kg" in p and "overview" in p
    out = dayai.apply_final('```json\n{"overview":"총평","highlights":["A"],"followups":["B"]}\n```')
    daily._write(store._dir(t["id"]) / "final.json", out)
    fr = reports.build_final(store, t["id"])
    md = reports.final_markdown(fr)
    assert "## 총평" in md and "## 방문하지 못한 계획 업체" in md and "Gadget Neu" in md
    assert docx.Document(io.BytesIO(reports.final_docx(store, t["id"], fr))).paragraphs


def call(base, method, path, body=None, raw=False, headers=None):
    h = {"X-TripDesk": "1", **(headers or {})}
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_api_day_flow(store):
    httpd, port = server.serve(store, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    transcribe.set_backend(lambda *a: "페이로드는 이십 킬로")
    try:
        t = make_trip(store)
        tid = t["id"]
        s, b, _ = call(base, "POST", f"/api/trips/{tid}/days/import", day_zip(tid), raw=True)
        assert s == 200 and json.loads(b)["days"][0]["recordings"] == 1
        s, b, _ = call(base, "POST", f"/api/trips/{tid}/days/import", b"nope", raw=True)
        assert s == 400
        s, b, h = call(base, "GET", f"/api/trips/{tid}/days/1/file/audio/alpha_1024_01.m4a", headers={"Range": "bytes=2-5"})
        assert s == 206 and b == b"keau" and h["Content-Range"] == "bytes 2-5/9"
        assert call(base, "GET", f"/api/trips/{tid}/days/1/file/audio/..%2F..%2Ftrip.json")[0] == 400
        s, b, _ = call(base, "POST", f"/api/trips/{tid}/days/1/transcribe", {"language": "ko", "model": "small"})
        assert s == 200
        for _ in range(100):
            j = json.loads(call(base, "GET", f"/api/trips/{tid}/days/1/transcribe")[1])
            if j["job"]["status"] != "running":
                break
            time.sleep(0.05)
        assert j["job"]["status"] == "done" and j["summary"]["transcribed"] == 1
        s, b, _ = call(base, "POST", f"/api/trips/{tid}/days/1/prompt", {})
        assert s == 200 and "이십 킬로" in json.loads(b)["prompts"][0]
        s, b, _ = call(base, "POST", f"/api/trips/{tid}/days/1/paste", {"text": "```json\n" + json.dumps(REPLY, ensure_ascii=False) + "\n```"})
        assert s == 200 and json.loads(b)["applied"]["recordings"] == 1
        s, b, _ = call(base, "PUT", f"/api/trips/{tid}/days/1/report", {"summary": "고친 요약", "points": {"c-a": ["수정 포인트"]}})
        rep = json.loads(b)["report"]
        assert rep["summary"] == "고친 요약" and rep["companies"][0]["points"] == ["수정 포인트"]
        s, b, h = call(base, "GET", f"/api/trips/{tid}/days/1/report.md")
        assert s == 200 and "수정 포인트".encode() in b and "attachment" in h["Content-Disposition"]
        s, b, h = call(base, "GET", f"/api/trips/{tid}/days/1/report.docx")
        assert s == 200 and b[:2] == b"PK"
        assert call(base, "GET", f"/api/trips/{tid}/days/2")[0] == 400  # 가져오지 않은 일차
        s, b, _ = call(base, "GET", f"/api/trips/{tid}/final.docx")
        assert s == 200 and b[:2] == b"PK"
        # 목록에는 일차별 진행 상황이 들어 있다
        trips = json.loads(call(base, "GET", "/api/trips")[1])["trips"]
        assert trips[0]["pickedCount"] == 3 and trips[0]["dayStats"][0]["transcribed"] == 1
    finally:
        transcribe.set_backend(None)
        httpd.shutdown()
