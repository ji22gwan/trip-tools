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
