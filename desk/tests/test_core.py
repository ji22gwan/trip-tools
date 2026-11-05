import io
import json
import zipfile

import pytest

from conftest import JPG, PDF, PNG
from tripdesk import companies_io, mapfinder, package
from tripdesk.store import StoreError


def new_trip(store, name="SPS 2026"):
    return store.create_trip(name, "Nuremberg", "2026-11-24", "2026-11-26", "휴머노이드 조사")


def test_trip_days_and_validation(store):
    t = new_trip(store)
    assert t["days"] == ["2026-11-24", "2026-11-25", "2026-11-26"]
    with pytest.raises(StoreError):
        store.create_trip("", "", "2026-11-24", None)
    with pytest.raises(StoreError):
        store.create_trip("x", "", "2026-11-26", "2026-11-24")
    with pytest.raises(StoreError):
        store.get_trip("../../etc")


def test_sniff_and_download(site):
    assert mapfinder.sniff(PDF) == ".pdf" and mapfinder.sniff(PNG) == ".png" and mapfinder.sniff(JPG) == ".jpg"
    assert mapfinder.sniff(b"<html>") is None
    data, ext = mapfinder.download_map(site + "/docs/Hallenplan_2026.pdf")
    assert ext == ".pdf" and data.startswith(b"%PDF")
    with pytest.raises(mapfinder.MapError, match="PDF/이미지가 아니"):
        mapfinder.download_map(site + "/fake.pdf")
    with pytest.raises(mapfinder.MapError, match="거절"):
        mapfinder.download_map(site + "/blocked.pdf")
    with pytest.raises(mapfinder.MapError):
        mapfinder.download_map("file:///etc/passwd")


def test_find_candidates_ranks_map_over_privacy(site):
    c = mapfinder.find_map_candidates(site + "/")
    urls = [x["url"] for x in c]
    assert urls[0].endswith("Hallenplan_2026.pdf")
    assert any(u.endswith("venue_map.png") for u in urls)  # 하위 페이지의 이미지도 찾는다
    assert not any(u.endswith("privacy.pdf") for u in urls)


def test_known_source():
    k = mapfinder.known_source("SPS 2026", 2026)
    assert k and k["mapUrls"][0].endswith("SPS2026_Gelaendeplan_map_of_the_grounds_2026.pdf")
    assert mapfinder.known_source("SPS 2026", 2030) is None
    assert mapfinder.known_source("Hannover Messe", 2026) is None


def test_csv_import_merge_keeps_ids(store):
    t = new_trip(store)
    csv_bytes = ("업체명,카테고리,홀,부스,일차,메모,질문\n"
                 "A사,휴머노이드,3A,118,1,메모,가동 시간; 가격\n"
                 "B사,용접,4A,330,2026-11-25,,\n"
                 "C사,센서,3,1,9,,\n").encode("utf-8-sig")
    rows, warns = companies_io.parse_companies("l.csv", csv_bytes, t["days"])
    assert [r["day"] for r in rows] == [1, 2, None] and len(warns) == 1
    assert rows[0]["questions"] == ["가동 시간", "가격"]
    merged, a, u = companies_io.merge_companies([], rows)
    first_id = merged[0]["id"]
    rows2, _ = companies_io.parse_companies("l.csv", csv_bytes.replace("1,메모,가동".encode(), "1,수정,가동".encode()), t["days"])
    merged, a2, u2 = companies_io.merge_companies(merged, rows2)
    assert (a, u, a2, u2) == (3, 0, 0, 3) and merged[0]["id"] == first_id and merged[0]["preNotes"] == "수정"


def test_xlsx_and_cp949_and_bad_header(store):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Company", "Category", "Hall", "Booth", "Day"])
    ws.append(["X Corp", "Cobot", "3A", 12, 1])
    buf = io.BytesIO()
    wb.save(buf)
    rows, _ = companies_io.parse_companies("a.xlsx", buf.getvalue(), ["2026-11-24"])
    assert rows[0]["name"] == "X Corp" and rows[0]["booth"] == "12" and rows[0]["day"] == 1
    rows, _ = companies_io.parse_companies("a.csv", "업체명,홀\n가나다,3\n".encode("cp949"), ["2026-11-24"])
    assert rows[0]["name"] == "가나다"
    with pytest.raises(companies_io.ImportError_):
        companies_io.parse_companies("a.csv", b"foo,bar\n1,2\n", ["2026-11-24"])


def test_package_matches_phone_importer_contract(store):
    t = new_trip(store, "SPS 2026")
    store.add_map(t["id"], "hall.pdf", PDF, source="http://x/hall.pdf")
    store.add_map(t["id"], "../../evil.png", PNG)  # 경로 탈출 시도는 파일명만 남는다
    rows, _ = companies_io.parse_companies("l.csv", "업체명,일차\nA,1\n".encode(), t["days"])
    store.set_companies(t["id"], companies_io.merge_companies([], rows)[0])
    store.set_glossary(t["id"], ["EtherCAT", "EtherCAT", " TCP "])
    name, data = package.build_package(store, t["id"])
    assert name == "trip_SPS_2026.zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    assert not any(".." in n for n in names)
    base = {n.split("/")[-1] for n in names}
    assert {"trip.json", "companies.json", "glossary.json", "hall.pdf"} <= base
    assert "evil.png" not in base  # 대표 지도(처음 받은 hall.pdf) 1장만 들어간다
    store.set_primary_map(t["id"], "evil.png")
    _, data2 = package.build_package(store, t["id"])
    maps2 = [n for n in zipfile.ZipFile(io.BytesIO(data2)).namelist() if "/map/" in n]
    assert maps2 == ["trip_SPS_2026/map/evil.png"]
    store.delete_map(t["id"], "evil.png")  # 대표를 지우면 남은 지도가 대표가 된다
    assert store.primary_map(t["id"]).name == "hall.pdf"
    with pytest.raises(StoreError):
        store.set_primary_map(t["id"], "nope.pdf")
    trip = json.loads(z.read("trip_SPS_2026/trip.json"))
    assert trip["id"] == t["id"] and trip["schema"] == 1 and len(trip["days"]) == 3  # importer 필수 필드
    assert json.loads(z.read("trip_SPS_2026/glossary.json"))["terms"] == ["EtherCAT", "TCP"]
    comp = json.loads(z.read("trip_SPS_2026/companies.json"))[0]
    assert comp["id"] and comp["name"] == "A" and comp["day"] == 1


def test_hall_pins_clean_and_in_package(store):
    from tripdesk.store import hall_key, clean_hall_pins

    assert hall_key("Hall 3a") == hall_key("홀 3A") == hall_key(" 3 A ") == "3A"
    t = new_trip(store)
    store.update_trip(t["id"], hallPins={"Hall 3A": {"x": 0.31, "y": 0.42}, "4A": {"x": 1.5, "y": 0.2}, "5": "bad", "6": {"x": 0.1, "y": 0.9, "page": 1}})
    pins = store.get_trip(t["id"])["hallPins"]
    assert set(pins) == {"3A", "6"} and pins["3A"] == {"x": 0.31, "y": 0.42, "page": 0} and pins["6"]["page"] == 1  # 범위 밖·형식 오류는 버린다
    store.set_companies(t["id"], [{"id": "c1", "name": "A", "hall": "3a", "booth": "1", "day": 1}, {"id": "c2", "name": "B", "hall": "Hall 7", "booth": "", "day": 2}])
    store.add_map(t["id"], "m.pdf", PDF)
    assert any("7" in w and "배치" in w for w in package.check(store, t["id"]))  # 위치 없는 홀을 알려 준다
    _, data = package.build_package(store, t["id"])
    z = zipfile.ZipFile(io.BytesIO(data))
    assert json.loads(z.read("trip_SPS_2026/trip.json"))["hallPins"]["3A"]["x"] == 0.31


def test_travel_links_prompts_and_records(store):
    from tripdesk import travel

    t = new_trip(store)
    tid = t["id"]
    tr = travel.save(store, tid, {"origin": "ICN", "destination": "NUE", "minStars": 4, "maxStars": 3})
    assert (tr["minStars"], tr["maxStars"]) == (3, 4)  # 순서가 뒤집혀도 바로잡는다
    ln = travel.links(store.get_trip(tid), tr)
    assert "ICN" in ln["flights"][0]["url"] and any("skyscanner" in x["url"] for x in ln["flights"])
    agoda = next(x for x in ln["hotels"] if x["name"] == "Agoda")["url"]
    assert "minStarRating=3" in agoda and "maxStarRating=4" in agoda and t["days"][0] in agoda
    assert "class%3D3" in next(x for x in ln["hotels"] if x["name"] == "Booking.com")["url"]
    hp = travel.build_hotel_prompt(store.get_trip(tid), tr)
    assert "3성 이상 4성 이하" in hp and "리뷰 평점이 아니라" in hp
    reply = '```json\n{"flights":[{"direction":"outbound","flightNo":"lh713","airline":"Lufthansa","from":"ICN","to":"FRA","depart":"2026-11-22 13:00","confirmation":"ABC123","amount":"1,250,000","currency":"krw"}],"hotels":[{"name":"Hotel X","stars":4,"checkIn":"2026-11-23","checkOut":"2026-11-25","amount":420,"currency":"EUR"}]}\n```'
    assert travel.paste(store, tid, "booking", reply)["added"] == 2
    assert travel.paste(store, tid, "booking", reply) == {"added": 0, "existing": 2}  # 같은 예약은 중복으로 넣지 않는다
    tr = travel.get(store, tid)
    g = tr["flights"][0]["segments"][0]  # 옛 형식(한 편짜리)도 구간 하나짜리 여정으로 받는다
    assert g["flightNo"] == "LH713" and tr["flights"][0]["amount"] == 1250000 and g["depart"] == "2026-11-22T13:00"
    sm = travel.summary(tr, store.get_trip(tid))
    assert sm["totals"] == {"KRW": 1250000.0, "EUR": 420.0}
    assert any("오는 항공편" in x for x in sm["issues"]) and any("체크아웃" in x for x in sm["issues"])
    _, data = package.build_package(store, tid)
    z = zipfile.ZipFile(io.BytesIO(data))
    assert json.loads(z.read(next(n for n in z.namelist() if n.endswith("trip.json"))))["bookings"]["hotels"][0]["name"] == "Hotel X"


def test_trip_keywords_saved_and_cleaned(store):
    t = store.create_trip("K", "V", "2026-11-24", "2026-11-26", "") if hasattr(store, "create_trip") else None
    if t is None:
        return
    out = store.update_trip(t["id"], keywords=[" 용접 로봇 ", "용접 로봇", "", "비전 센서"], keywordCount=30)
    assert out["keywords"] == ["용접 로봇", "비전 센서"] and out["keywordCount"] == 30
    assert store.update_trip(t["id"], keywordCount=1000)["keywordCount"] == 30  # 범위 밖은 무시
    assert store.get_trip(t["id"])["keywords"] == ["용접 로봇", "비전 센서"]


def test_sessions_reply_conflicts_and_package(store):
    import io, json, zipfile
    from tripdesk import package, sessions
    t = store.create_trip("S", "V", "2026-11-24", "2026-11-26", "")
    days = t["days"]
    reply = {"sessions": [
        {"title": "Cobots in Shipbuilding", "date": "2026-11-25", "start": "10:00", "end": "10:45", "place": "Forum", "hall": "3A", "sourceUrl": "https://x.example/p/1", "verified": True},
        {"title": "AI Panel", "date": "2026-11-25", "start": "10:30", "end": "11:15", "place": "Stage 2", "sourceUrl": "", "verified": True},   # 근거 없음 → 미확인
        {"title": "Outside", "date": "2026-12-01", "start": "10:00"},      # 기간 밖
        {"title": "Bad time", "date": "2026-11-26", "start": "25:99"},     # 시간 오류 → 시간 미정
        {"title": "Cobots in Shipbuilding", "date": "2026-11-25", "start": "10:00"},  # 중복
    ]}
    merged, res = sessions.apply_reply("```json\n" + json.dumps(reply) + "\n```", [], days)
    assert res["added"] == 3 and res["outside"] == 1 and res["existing"] == 1
    by = {s["title"]: s for s in merged}
    assert by["Cobots in Shipbuilding"]["verified"] and not by["AI Panel"]["verified"] and by["Bad time"]["start"] == ""
    store.set_sessions(t["id"], merged)
    assert any("확인하지 못한 세션" in w for w in package.check(store, t["id"]))
    _, data = package.build_package(store, t["id"])
    z = zipfile.ZipFile(io.BytesIO(data))
    trip_json = json.loads(z.read([n for n in z.namelist() if n.endswith("trip.json")][0]))
    assert len(trip_json["sessions"]) == 3 and "sourceUrl" not in trip_json["sessions"][0]  # 세션은 전부 폰으로


def test_travel_multi_leg_journey_24h_and_dedup(store):
    import io, json, zipfile
    from tripdesk import package, reports, travel
    t = store.create_trip("F", "V", "2026-11-24", "2026-11-26", "")
    tid = t["id"]
    reply = '''```json
{"flights":[
 {"direction":"outbound","confirmation":"smt2z5","segments":[
   {"flightNo":"LH 713","airline":"Lufthansa","from":"icn","to":"FRA","depart":"23NOV26 12:55","arrive":"2026-11-23 6:40 PM","fromTerm":"1","cabin":"W","baggage":"1PC"},
   {"flightNo":"LH148","from":"FRA","to":"NUE","depart":"2026-11-23T21:25","arrive":"2026-11-23T22:10"}]},
 {"direction":"return","confirmation":"SMT2Z5","segments":[
   {"flightNo":"LH3805","from":"NUE","to":"MUC","depart":"2026-11-27T11:45","arrive":"2026-11-27T14:00","mode":"ground"},
   {"flightNo":"LH718","from":"MUC","to":"ICN","depart":"2026-11-27T16:05","arrive":"2026-11-28T11:15"}]}]}
```'''
    assert travel.paste(store, tid, "booking", reply)["added"] == 2
    assert travel.paste(store, tid, "booking", reply) == {"added": 0, "existing": 2}
    tr = travel.get(store, tid)
    out = tr["flights"][0]
    assert [g["flightNo"] for g in out["segments"]] == ["LH713", "LH148"] and out["confirmation"] == "SMT2Z5"
    assert out["segments"][0]["depart"] == "2026-11-23T12:55" and out["segments"][0]["arrive"] == "2026-11-23T18:40"  # 24시간제로 통일
    d = travel.decorate(out)
    assert d["route"] == ["ICN", "FRA", "NUE"] and d["layovers"][0]["minutes"] == 165 and not d["layovers"][0]["airportChange"]
    assert tr["flights"][1]["segments"][0]["mode"] == "ground"
    assert not any("오는 항공편" in x or "가는 항공편" in x for x in travel.summary(tr, store.get_trip(tid))["issues"])
    tr["flights"][0]["segments"][1]["depart"] = "2026-11-23T18:55"  # 경유 15분
    travel.save(store, tid, {"flights": tr["flights"]})
    assert any("15분" in x for x in travel.summary(travel.get(store, tid), store.get_trip(tid))["issues"])
    lines = reports.travel_lines({"flights": travel.get(store, tid)["flights"], "hotels": [], "totals": {}})
    assert "LH713/LH148 ICN→FRA→NUE (경유 1회) 2026-11-23 12:55" in lines[0]
    _, data = package.build_package(store, tid)
    z = zipfile.ZipFile(io.BytesIO(data))
    pf = json.loads(z.read(next(n for n in z.namelist() if n.endswith("trip.json"))))["bookings"]["flights"][0]
    assert pf["route"] == ["ICN", "FRA", "NUE"] and len(pf["segments"]) == 2


def test_travel_legacy_flat_records_merge_into_journey(store):
    from tripdesk import travel
    t = store.create_trip("L", "V", "2026-11-24", "2026-11-26", "")
    flat = [{"direction": "outbound", "flightNo": "LH1", "from": "ICN", "to": "FRA", "depart": "2026-11-23T10:00", "arrive": "2026-11-23T16:00", "confirmation": "AAA111"},
            {"direction": "outbound", "flightNo": "LH2", "from": "FRA", "to": "NUE", "depart": "2026-11-23T18:00", "arrive": "2026-11-23T19:00", "confirmation": "AAA111"},
            {"direction": "return", "flightNo": "LH9", "from": "NUE", "to": "ICN", "depart": "2026-11-27T10:00", "arrive": "2026-11-27T20:00", "confirmation": "AAA111"}]
    out = travel.clean_flights(flat)
    assert len(out) == 2 and len(out[0]["segments"]) == 2 and out[1]["direction"] == "return"
    assert travel.build_booking_prompt("").startswith("첨부한 이미지") and "24시간제" in travel.build_booking_prompt("") and "AM/PM" in travel.build_booking_prompt("")
    assert "예약 내용" in travel.build_booking_prompt("LH713 11/23")


def test_multi_booth_company_one_checkbox_many_stops(store):
    import io, json, zipfile
    from tripdesk import booths, companies_io, package, reports, research
    t = store.create_trip("M", "V", "2026-11-24", "2026-11-26", "")
    tid = t["id"]
    items, _ = research.sanitize({"companies": [
        {"name": "Codewerk GmbH", "category": "AI.소프트웨어", "booth": "5-210, 6-350G", "reason": "[키워드] x", "sourceUrl": "https://e.com/a", "verified": True},
        {"name": "Duo", "category": "로봇", "booths": [{"hall": "3A", "booth": "3A-100"}, {"hall": "4", "booth": "4-20"}, {"hall": "4", "booth": "4-20"}], "sourceUrl": "https://e.com/b", "verified": True}]})
    cs, added, _ = research.add_candidates(store.get_companies(tid), items, [])
    store.set_companies(tid, cs)
    assert added == 2  # 업체 수는 체크박스 기준
    c = store.get_companies(tid)[0]
    assert [(b["hall"], b["booth"]) for b in c["booths"]] == [("5", "5-210"), ("6", "6-350G")] and c["hall"] == "5"
    assert len(store.get_companies(tid)[1]["booths"]) == 2  # 같은 부스 중복 입력은 하나로
    cs = store.get_companies(tid)
    cs[0]["booths"][0]["day"], cs[0]["booths"][1]["day"] = 1, 3
    for x in cs:
        x["picked"] = True
    store.set_companies(tid, cs)
    st = booths.stops(store.get_companies(tid)[0])
    assert [x["id"] for x in st] == [cs[0]["id"], cs[0]["id"] + "#2"] and [x["day"] for x in st] == [1, 3]
    _, data = package.build_package(store, tid)
    z = zipfile.ZipFile(io.BytesIO(data))
    out = json.loads(z.read(next(n for n in z.namelist() if n.endswith("companies.json"))))
    assert len(out) == 4  # 업체 2곳 → 방문 지점 4곳
    dup = [x for x in out if x["name"] == "Codewerk GmbH"]
    assert dup[1]["dup"]["i"] == 2 and dup[1]["dup"]["n"] == 2 and dup[1]["dup"]["others"][0]["id"] == cs[0]["id"] and dup[1]["day"] == 3
    assert len(reports._plan(store, tid)) == 4
    rows = companies_io.merge_companies(store.get_companies(tid), [{"name": "codewerk gmbh", "category": "x", "booths": [{"hall": "6", "booth": "6-350G", "day": 2}, {"hall": "7", "booth": "7-1", "day": None}]}])
    cw = rows[0][0]
    assert len(cw["booths"]) == 3 and cw["booths"][1]["day"] == 2 and cw["id"] == cs[0]["id"]


def test_plan_report_markdown(store):
    from tripdesk import planreport
    t = store.create_trip("계획 엑스포", "데모센터", "2026-11-24", "2026-11-26", "휴머노이드 동향 조사\n용접 자동화 확인")
    tid = t["id"]
    store.set_companies(tid, [
        {"id": "c-1", "name": "Codewerk GmbH", "category": "AI.소프트웨어", "booths": [{"hall": "5", "booth": "5-210", "day": 1}, {"hall": "6", "booth": "6-350G", "day": 3}],
         "picked": True, "source": "ai", "verified": True, "reason": "[키워드] 비전 소프트웨어"},
        {"id": "c-2", "name": "후보만", "category": "x", "picked": False}])
    md = planreport.build_markdown(store, tid)
    assert "## 1. 출장 정보" in md and "## 2. 출장 목표 및 예상 결과" in md and "## 3. 방문 후보 업체 (1곳, 방문 지점 2곳)" in md
    assert "- 휴머노이드 동향 조사" in md and "5 · 5-210<br>6 · 6-350G" in md and "[키워드] 비전 소프트웨어" in md and "후보만" not in md
    planreport.save(store, tid, {"goals": "A\nB", "expected": ["C"]})
    md = planreport.build_markdown(store, tid)
    assert "- A" in md and "- C" in md and "휴머노이드 동향 조사" not in md


def test_map_pdf_prerendered_images_go_into_package(store):
    import io, json, zipfile
    from tripdesk import package
    t = store.create_trip("R", "V", "2026-11-24", "2026-11-25", "")
    tid = t["id"]
    store.add_map(tid, "plan.pdf", b"%PDF-1.4 fake")
    assert store.render_state(tid)["needed"] is True
    _, data = package.build_package(store, tid)
    assert any(n.endswith("map/plan.pdf") for n in zipfile.ZipFile(io.BytesIO(data)).namelist())  # 변환 전에는 PDF 그대로(폰이 변환)
    store.render_begin(tid)
    store.render_put(tid, 1, b"\xff\xd8\xff" + b"a" * 10)
    store.render_put(tid, 2, b"\xff\xd8\xff" + b"b" * 10)
    store.render_done(tid)
    assert store.render_state(tid)["needed"] is False
    names = zipfile.ZipFile(io.BytesIO(package.build_package(store, tid)[1])).namelist()
    assert any(n.endswith("map/plan_p01.jpg") for n in names) and any(n.endswith("map/plan_p02.jpg") for n in names) and not any(n.endswith(".pdf") for n in names)
    store.add_map(tid, "plan2.pdf", b"%PDF-1.4 other")
    store.set_primary_map(tid, "plan2.pdf")
    assert store.render_state(tid)["needed"] is True  # 대표 지도가 바뀌면 다시 변환


def test_cloud_package_list_and_delete(tmp_path, monkeypatch):
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from tripdesk import cloud
    state = {"pk": [{"id": "t1", "name": "A", "size": 10, "at": 1}, {"id": "t2", "name": "B", "size": 20, "at": 2}], "auth": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, obj):
            b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            state["auth"].append(self.headers.get("Authorization")); self._send({"packages": state["pk"]})
        def do_PUT(self):
            n = int(self.headers["Content-Length"]); state["put"] = (self.path, len(self.rfile.read(n)), self.headers.get("X-Trip-Name"))
            self._send({"ok": True, "id": self.path.rsplit("/", 1)[1]})
        def do_DELETE(self):
            i = self.path.rsplit("/", 1)[1]; state["pk"] = [p for p in state["pk"] if p["id"] != i]; self._send({"ok": True})
    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    home = tmp_path / "tt"; home.mkdir()
    (home / "install.env").write_text(f'WORKER_URL="http://127.0.0.1:{srv.server_port}"\nTOKEN="tok"\nKV_ID="x"\n')
    monkeypatch.setenv("TRIP_TOOLS_HOME", str(home)); monkeypatch.setenv("TRIPDESK_HOME", str(tmp_path / "td"))
    assert [p["id"] for p in cloud.list_packages()] == ["t1", "t2"] and state["auth"][0] == "Bearer tok"
    r = cloud.upload_package("t9", "한글 이름", b"PK" + b"x" * 300000)
    assert r["ok"] and r["id"] == "t9" and state["put"][1] == 300002 and r["uploadSec"] >= 0 and r["kbps"] > 0
    cloud.delete_package("t1")
    assert [p["id"] for p in cloud.list_packages()] == ["t2"]
    srv.shutdown()
