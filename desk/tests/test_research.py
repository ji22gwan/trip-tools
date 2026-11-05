import json
import threading
import urllib.error
import urllib.request

import pytest

from tripdesk import package, research, server

RESULT = {
    "companies": [
        {"name": "Alpha Robotics GmbH", "category": "휴머노이드", "hall": "3A", "booth": "118", "reason": "중량물 작업 가능", "matched": ["휴머노이드"], "sourceUrl": "https://ex.example/alpha", "verified": True},
        {"name": "Beta Weld", "category": "용접 자동화", "reason": "용접 셀", "sourceUrl": "", "verified": True},  # 근거 없음 -> 확인됨 취소
        {"name": "alpha robotics", "category": "중복", "reason": "dup"},
        {"name": "Gamma Vision", "category": "비전·센서", "reason": "센서", "sourceUrl": "javascript:alert(1)", "verified": False},
        "garbage",
    ],
    "notes": "공식 참가업체 목록 확인",
}
TRIP = {"name": "SPS 2026", "venue": "Nuremberg", "days": ["2026-11-24", "2026-11-25"], "purpose": "휴머노이드와 용접 자동화 조사"}


def test_keyword_prompt_has_keywords_rules_and_format():
    p = research.build_keyword_prompt(TRIP, ["휴머노이드", "welding robot"], 25, "https://sps.mesago.com/", ["Old Co"])
    assert "휴머노이드, welding robot" in p and "Never invent" in p and "SPS 2026" in p
    assert "Old Co" in p and "```json" in p and '"verified"' in p
    assert "[글로벌]" in p and "[최근 이슈]" in p and "[행사]" in p and "last 12 months" in p
    assert "MUST EXCLUDE" in p and "official site" in p and "similar or closely related" in p
    with pytest.raises(research.ResearchError):
        research.build_keyword_prompt(TRIP, [])
    assert "up to 100 companies" in research.build_keyword_prompt(TRIP, ["x"], 999)
    assert "up to 10 companies" in research.build_keyword_prompt(TRIP, ["x"], 10)


def test_split_keywords():
    assert research.split_keywords("휴머노이드, 용접 로봇;\n비전 센서, 휴머노이드") == ["휴머노이드", "용접 로봇", "비전 센서"]


def test_sanitize_marks_unsourced_as_unverified_and_dedups():
    items, notes = research.sanitize(RESULT)
    assert [i["name"] for i in items] == ["Alpha Robotics GmbH", "Beta Weld", "Gamma Vision"]  # 법인 표기만 다른 중복은 합친다
    assert [i["verified"] for i in items] == [True, False, False]
    assert items[2]["sourceUrl"] == "" and notes


def test_add_candidates_unpicked_and_no_duplicates():
    items, _ = research.sanitize(RESULT)
    existing = [{"id": "c-1", "name": "alpha robotics", "category": "x", "hall": "", "booth": ""}]
    merged, added, existing_n = research.add_candidates(existing, items, ["키워드"])
    assert (added, existing_n) == (2, 1)
    assert merged[0]["hall"] == "3A" and "휴머노이드" in merged[0]["keywords"]  # 기존 업체는 위치만 채우고 건드리지 않는다
    new = merged[1]
    assert new["picked"] is False and new["source"] == "ai" and new["day"] is None


def test_extract_json_errors():
    with pytest.raises(research.ResearchError):
        research.extract_json("no json here")
    with pytest.raises(research.ResearchError, match="깨져"):
        research.extract_json("```json\n{bad}\n```")
    assert research.extract_json("답변입니다\n```json\n{\"companies\": []}\n```\n끝")["companies"] == []


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers={"X-TripDesk": "1"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_prompt_paste_pick_package(store):
    import io, zipfile

    httpd, port = server.serve(store, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        tid = call(base, "POST", "/api/trips", {"name": "SPS 2026", "venue": "N", "start": "2026-11-24", "end": "2026-11-25", "purpose": "로봇"})[1]["trip"]["id"]
        assert call(base, "POST", f"/api/trips/{tid}/prompt/exhibitors", {"keywords": ""})[0] == 400
        s, r = call(base, "POST", f"/api/trips/{tid}/prompt/exhibitors", {"keywords": "휴머노이드, 용접", "count": 15})
        assert s == 200 and r["keywords"] == ["휴머노이드", "용접"] and "휴머노이드, 용접" in r["prompt"]
        assert call(base, "POST", f"/api/trips/{tid}/paste/exhibitors", {"text": "그냥 글"})[0] == 400
        text = "결과\n```json\n" + json.dumps(RESULT, ensure_ascii=False) + "\n```"
        s, v = call(base, "POST", f"/api/trips/{tid}/paste/exhibitors", {"text": text, "keywords": "휴머노이드"})
        assert v["pasted"]["added"] == 3 and v["pasted"]["unverified"] == 2
        assert all(c["picked"] is False for c in v["companies"])
        assert any("선택하지 않은" in w or "아직 고르지" in w for w in v["warnings"])  # 고른 업체가 없음을 알린다
        # 같은 답을 또 붙여도 늘어나지 않는다
        v2 = call(base, "POST", f"/api/trips/{tid}/paste/exhibitors", {"text": text})[1]
        assert v2["pasted"]["added"] == 0 and len(v2["companies"]) == 3
        # 두 곳을 골라 일차를 정하고 패키지를 만든다
        cs = v2["companies"]
        cs[0].update(picked=True, day=1)
        cs[2].update(picked=True, day=2)
        v3 = call(base, "PUT", f"/api/trips/{tid}/companies", cs)[1]
        assert any("확인하지 못한" in w for w in v3["warnings"])
        name, data = package.build_package(store, tid)
        z = zipfile.ZipFile(io.BytesIO(data))
        out = json.loads(z.read(f"{name[:-4]}/companies.json"))
        assert [c["name"] for c in out] == ["Alpha Robotics GmbH", "Gamma Vision"]  # 고르지 않은 후보는 폰으로 가지 않는다
        assert "출처: https://ex.example/alpha" in out[0]["preNotes"] and "확인 필요" in out[1]["preNotes"]
        assert not any("exhibitor" in n for n in z.namelist())
    finally:
        httpd.shutdown()


def test_keyword_prompt_does_not_drop_multi_booth_and_widens():
    from tripdesk import research
    p = research.build_keyword_prompt({"name": "X", "days": ["2026-11-24", "2026-11-26"], "venue": "V"}, ["비전 센서"], 30, "", ["Old Co"])
    assert "list EVERY hall/booth" in p and "open its detail page" in p and "closely related search terms" in p and "Old Co" in p
