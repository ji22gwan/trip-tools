"""매뉴얼용 Desk 화면 캡처. 가상 데이터를 임시 폴더에 만들고 실제 화면을 띄워 img/ 에 저장한다.
실행:  python3 docs/manual/make_desk_shots.py   (playwright, matplotlib, pillow 필요)"""
import json, os, pathlib, shutil, sys, tempfile, threading, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desk")); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import demo_data as D
from tripdesk import server
from tripdesk.store import Store
from playwright.sync_api import sync_playwright

IMG = pathlib.Path(__file__).parent / "img"; IMG.mkdir(exist_ok=True)
HOME = pathlib.Path(tempfile.mkdtemp(prefix="manual-"))
PORT = 8790; BASE = f"http://127.0.0.1:{PORT}"

def call(method, path, body=None, raw=False):
    data = None if body is None else (body if raw else json.dumps(body).encode())
    req = urllib.request.Request(BASE + "/api" + path, data=data, method=method, headers={"X-TripDesk": "1", "Content-Type": "application/octet-stream" if raw else "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read()
        return json.loads(t) if t[:1] in (b"{", b"[") else t

store = Store(HOME)
httpd, _ = server.serve(store, PORT)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
os.environ["TRIP_TOOLS_HOME"] = str(HOME / "tt")  # 설치 기록 없음 → '서버 업로드' 비활성 상태가 그대로 보인다

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        def go(h): pg.goto(f"{BASE}/#/{h}"); pg.reload(); pg.wait_for_timeout(900)
        def shot(name, full=False, clip_modal=False):
            pg.wait_for_timeout(350)
            if clip_modal and pg.locator(".modal").count():
                pg.locator(".modal").first.screenshot(path=str(IMG / f"{name}.png"))
            else:
                pg.screenshot(path=str(IMG / f"{name}.png"), full_page=full)
            print("shot", name)
        def click(text, exact=True, nth=0):
            pg.get_by_role("button", name=text, exact=exact).nth(nth).click(); pg.wait_for_timeout(500)

        T = D.TRIP
        # ---------- 1. 출장 만들기 ----------
        go("trips"); shot("desk-01-trips-empty")
        click("+ 새 출장"); pg.wait_for_timeout(300)
        ins = pg.locator(".modal input")
        ins.nth(0).fill(T["name"]); ins.nth(1).fill(T["venue"]); ins.nth(2).fill(T["start"]); ins.nth(3).fill(T["end"])
        pg.locator(".modal textarea").fill(T["purpose"])
        shot("desk-02-new-trip", clip_modal=True)
        click("만들기"); pg.wait_for_timeout(900)
        tid = call("GET", "/trips")["trips"][0]["id"]
        shot("desk-03-prep-empty")

        # ---------- 2. AI 프롬프트로 후보 찾기 ----------
        click("AI 프롬프트 만들기"); pg.wait_for_timeout(300)
        pg.locator(".modal input").first.fill("협동로봇, 용접 로봇, 비전 센서")
        click("프롬프트 만들기"); pg.wait_for_timeout(600)
        shot("desk-04-ai-prompt")
        reply = {"companies": [
            {"name": "알파로보틱스", "category": "협동로봇", "hall": "1", "booth": "1A12", "reason": "가반하중 20kg급 협동로봇", "matched": "협동로봇", "sourceUrl": "https://example.com/exhibitors/alpha", "verified": True},
            {"name": "에코웰딩", "category": "용접 로봇", "hall": "3A", "booth": "3A07", "reason": "조선 소조립 용접 자동화", "matched": "용접 로봇", "sourceUrl": "https://example.com/exhibitors/eco", "verified": True},
            {"name": "코발트비전", "category": "비전 센서", "hall": "", "booth": "", "reason": "용접선 추적 3D 비전 (참가 여부 확인 필요)", "matched": "비전 센서", "sourceUrl": "", "verified": False}],
            "notes": "코발트비전은 참가 목록에서 확인하지 못했어요."}
        ta = pg.locator(".modal textarea").last
        ta.fill("알겠습니다. 아래가 결과입니다.\n```json\n" + json.dumps(reply, ensure_ascii=False, indent=1) + "\n```")
        shot("desk-05-ai-paste")
        click("가져오기"); pg.wait_for_timeout(900)
        shot("desk-06-candidates-after-paste")

        # ---------- 3. 가상 데이터로 본격 채우기 ----------
        call("POST", f"/trips/{tid}/maps/upload?filename=floorplan.pdf", D.map_pdf(), raw=True)
        call("PUT", f"/trips/{tid}/glossary", D.GLOSSARY)
        comps = [dict(id=c[0], name=c[1], category=c[2], hall=c[3], booth=c[4], day=c[5], picked=c[0] in D.PICKED, source=c[6], verified=c[7], reason=c[8], questions=c[9],
                      sourceUrl="https://example.com/exhibitors/" + c[0][2:] if c[6] == "ai" else "") for c in D.COMPANIES]
        call("PUT", f"/trips/{tid}/companies", comps)
        go(f"prep/{tid}")
        shot("desk-07-candidates", full=True)
        pg.locator("button[aria-label='알파로보틱스 편집']").click(); pg.wait_for_timeout(400)
        shot("desk-08-company-edit", clip_modal=True)
        click("저장") if False else pg.locator(".modalbg").evaluate("e=>e.remove()")
        pg.locator("button:has-text('일정 배분')").first.click(); pg.wait_for_timeout(600)
        shot("desk-09-plan", full=True)
        pg.locator("button:has-text('전시장 맵')").first.click(); pg.wait_for_timeout(2500)
        pg.wait_for_selector("canvas", timeout=20000); pg.wait_for_timeout(800)
        shot("desk-10-map-tab", full=True)
        pg.get_by_role("button", name="지도 글자에서 자동 찾기").click(); pg.wait_for_timeout(600)
        pg.locator("text=홀 위치 지정").first.scroll_into_view_if_needed()
        shot("desk-11-hall-pins")
        pg.get_by_role("button", name="저장", exact=True).last.click(); pg.wait_for_timeout(700)

        # 항공·숙소
        pg.locator("text=항공·숙소").last.click(); pg.wait_for_selector("text=이동 조건")
        pg.fill("input[placeholder*='ICN']", D.TRAVEL["origin"]); pg.fill("input[placeholder*='NUE']", D.TRAVEL["destination"])
        pg.get_by_role("button", name="저장", exact=True).first.click(); pg.wait_for_timeout(700)
        shot("desk-12-travel-search", full=True)
        click("항공편 후보 프롬프트 (AI 챗봇)", exact=True); pg.wait_for_timeout(500)
        shot("desk-13-travel-prompt")
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        tr = call("GET", f"/trips/{tid}/travel")["travel"]
        call("PUT", f"/trips/{tid}/travel", dict(candidates=dict(flights=D.CAND_FLIGHTS, hotels=D.CAND_HOTELS), flights=D.FLIGHTS, hotels=D.HOTELS))
        go(f"prep/{tid}"); pg.locator("text=항공·숙소").last.click(); pg.wait_for_selector("text=예약 기록")
        shot("desk-14-travel-candidates-records", full=True)
        pg.get_by_role("button", name="편집").first.click(); pg.wait_for_timeout(400)
        shot("desk-15-flight-edit", clip_modal=True)
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        click("예약 메일로 자동 정리 (AI 챗봇)"); pg.wait_for_timeout(300)
        pg.locator(".modal textarea").first.fill("[데모에어] 예약 확인\n예약번호 X7K2QD / DA101 ICN→FRA 2026-11-23 13:10 도착 17:40 / DA102 FRA→ICN 2026-11-26 19:30\n총 결제 1,450,000원")
        shot("desk-16-booking-mail", clip_modal=True)
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        pg.locator("text=용어집").first.click(); pg.wait_for_timeout(500)
        shot("desk-17-glossary")

        # 패키지 확정
        go(f"prep/{tid}")
        pg.get_by_role("button", name="패키지 확정 · 폰으로 보내기").first.click(); pg.wait_for_timeout(900)
        shot("desk-18-package", clip_modal=True)
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        open(IMG.parent / ".tid", "w").write(tid)
        (IMG.parent / "package.zip").write_bytes(call("GET", f"/trips/{tid}/package"))

        # ---------- 4. 일간 import ----------
        trip = call("GET", f"/trips/{tid}")
        trip = trip.get("trip", trip)
        go(f"import/{tid}"); shot("desk-19-import-empty")
        for d in (1, 2, 3):
            call("POST", f"/trips/{tid}/days/import", D.day_zip(trip, d), raw=True)
        go(f"import/{tid}"); shot("desk-20-import-done", full=True)
        # 전사(원문)
        for d in (1, 2, 3):
            for (cid, recs, memos, photos) in D.DAYS[d]:
                for ri, (hm, dur, raw, cor) in enumerate(recs):
                    fn = f"audio/{cid}_{hm.replace(':', '')}_{ri + 1:02d}.wav"
                    call("PUT", f"/trips/{tid}/days/{d}/recording", dict(file=fn, text=raw))
        # ---------- 5. 일간 보고서 ----------
        go(f"daily/{tid}/1"); shot("desk-21-daily-raw", full=True)
        click("AI 교정·요약"); pg.wait_for_timeout(600)
        shot("desk-22-daily-prompt")
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        for d in (1, 2, 3):
            recs = []; comps_ = []
            for (cid, rr, memos, photos) in D.DAYS[d]:
                for ri, (hm, dur, raw, cor) in enumerate(rr):
                    recs.append(dict(file=f"audio/{cid}_{hm.replace(':', '')}_{ri + 1:02d}.wav", corrected=cor))
                comps_.append(dict(id=cid, points=D.POINTS[cid]))
            call("POST", f"/trips/{tid}/days/{d}/paste", dict(text="```json\n" + json.dumps(dict(recordings=recs, companies=comps_, summary=D.DAY_SUMMARY[d]), ensure_ascii=False) + "\n```"))
        go(f"daily/{tid}/1"); shot("desk-23-daily-1", full=True)
        go(f"daily/{tid}/2"); shot("desk-24-daily-2")
        pg.locator("button:has-text('수정')").first.click(); pg.wait_for_timeout(400)
        shot("desk-25-daily-edit", clip_modal=True)
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        # ---------- 6. 최종 보고서 ----------
        go(f"final/{tid}"); shot("desk-26-final-empty")
        click("AI 총평 프롬프트"); pg.wait_for_timeout(500); shot("desk-27-final-prompt")
        pg.locator(".modalbg").evaluate("e=>e.remove()")
        call("POST", f"/trips/{tid}/final/paste", dict(text="```json\n" + json.dumps(D.FINAL, ensure_ascii=False) + "\n```"))
        go(f"final/{tid}"); shot("desk-28-final", full=True)
        print("home", HOME)
        b.close()
    print(errs)
main()
