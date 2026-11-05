"""매뉴얼용 폰 앱(Trip Field) 화면 캡처. make_desk_shots.py 가 만든 package.zip 을 서버에서 받는 흐름까지 그대로 재현한다.
실행: python3 docs/manual/make_desk_shots.py && python3 docs/manual/make_phone_shots.py"""
import base64, functools, http.server, json, pathlib, sys, threading
ROOT = pathlib.Path(__file__).resolve().parents[2]; HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE)); import demo_data as D
from playwright.sync_api import sync_playwright
IMG = HERE / "img"; PKG = (HERE / "package.zip").read_bytes()
PORT = 8791; BASE = f"http://127.0.0.1:{PORT}"; WORKER = "https://demo-worker.example.workers.dev"
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "field-pwa"))
H.log_message = lambda *a, **k: None
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H); threading.Thread(target=httpd.serve_forever, daemon=True).start()
b64 = lambda b: base64.b64encode(b).decode()

def worker_route(route):
    r = route.request; u = r.url
    hd = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}
    if r.method == "OPTIONS": return route.fulfill(status=204, headers=hd)
    if u.endswith("/packages"):
        return route.fulfill(json={"packages": [{"id": "demo", "name": D.TRIP["name"], "at": "2026-11-20T09:12:00Z", "size": len(PKG)}]}, headers=hd)
    if "/packages/" in u: return route.fulfill(body=PKG, headers={**hd, "content-type": "application/zip"})
    if u.endswith("/translate"):
        t = json.loads(r.post_data or "{}")
        return route.fulfill(json={"translation": "페이로드가 20kg인 협동로봇의 납기는 어떻게 되나요?" if t.get("to") == "ko" else "What is the lead time for the 20 kg payload cobot?", "ms": 640, "model": "gemini"}, headers=hd)
    if u.endswith("/health"): return route.fulfill(json={"ok": True}, headers=hd)
    route.fulfill(status=404, headers=hd)

SEED = """async ({days, tone, photo}) => {
  const db = await import('/js/db.js'); const m = await import('/js/model.js');
  const bytes = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const trip = await m.loadActiveTrip(); const cos = await m.listCompanies(trip.id);
  for (const [dayStr, items] of Object.entries(days)) {
    const day = Number(dayStr); const date = trip.days[day - 1];
    for (const it of items) {
      const c = cos.find(x => x.id === it.id); if (!c) continue;
      let first = null;
      for (const [hm, dur] of it.recs) {
        const at = new Date(date + 'T' + hm + ':00').getTime(); first = first || at;
        await db.put('recordings', {id: db.newId(), tripId: trip.id, companyId: c.id, day, mime: 'audio/wav', createdAt: at, duration: dur, status: 'done', blob: new Blob([bytes(tone)], {type: 'audio/wav'})});
      }
      for (const [t, imp] of it.memos) await db.put('memos', {id: db.newId(), tripId: trip.id, companyId: c.id, day, text: t, important: imp, createdAt: first + 60000});
      for (let i = 0; i < it.photos; i++) await db.put('photos', {id: db.newId(), tripId: trip.id, companyId: c.id, day, blob: new Blob([bytes(photo)], {type: 'image/jpeg'}), createdAt: first + 90000 + i});
      c.visits = [...(c.visits || []).filter(v => v.day !== day), {day, at: first}]; await db.put('companies', c);
    }
  }
}"""

def main():
    days = {}
    for d, items in D.DAYS.items():
        if d == 3: continue
        sel = items if d == 1 else items[:2]
        days[str(d)] = [dict(id=cid, recs=[(hm, dur) for hm, dur, _, _ in rr], memos=memos, photos=ph) for cid, rr, memos, ph in sel]
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ko-KR",
                            timezone_id="Europe/Berlin", service_workers="block")
        ctx.route(WORKER + "/**", worker_route)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.clock.set_fixed_time("2026-11-25T11:20:00+01:00")
        def shot(name, full=False):
            pg.wait_for_timeout(450); pg.screenshot(path=str(IMG / f"{name}.png"), full_page=full); print("shot", name)
        pg.goto(BASE + "/#/setup"); pg.wait_for_timeout(1200)
        shot("phone-01-setup-empty")
        pg.get_by_role("button", name="번역 서버 설정").click(); pg.wait_for_timeout(700)
        pg.fill("#sUrl", WORKER); pg.fill("#sToken", "demo-token-0000")
        shot("phone-02-settings", full=True)
        pg.click("#sSave"); pg.wait_for_timeout(500)
        pg.click("#backBtn"); pg.wait_for_timeout(700)
        pg.click("#srvBtn"); pg.wait_for_timeout(1000)
        shot("phone-03-server-sheet")
        pg.locator("[data-id='demo']").click(); pg.wait_for_timeout(2500)
        shot("phone-04-after-import")
        pg.evaluate(SEED, dict(days=days, tone=b64(D.tone_wav(440)), photo=b64(D.photo_jpeg("데모 부스 사진", (60, 120, 170)))))
        pg.goto(BASE + "/#/map"); pg.reload(); pg.wait_for_timeout(2500)
        shot("phone-05-map")
        pg.locator(".hall-pin").nth(1).click(); pg.wait_for_timeout(700)
        shot("phone-06-hall-sheet")
        pg.locator(".hall-sheet button").click(); pg.wait_for_timeout(400)
        pg.click("#tripInfoBtn"); pg.wait_for_timeout(700)
        shot("phone-07-bookings")
        pg.locator("[data-close]").first.click(); pg.wait_for_timeout(400)
        pg.click("#daySel") if False else None
        pg.goto(BASE + "/#/list"); pg.wait_for_timeout(1000)
        shot("phone-08-list", full=True)
        pg.locator("[data-sess]").first.click(); pg.wait_for_timeout(700)
        shot("phone-15-session-sheet")
        pg.click("#sessGo"); pg.wait_for_timeout(700)   # 참석할게요 → 목록에 '참석' 표시
        pg.goto(BASE + "/#/list"); pg.wait_for_timeout(600)
        shot("phone-08-list", full=True)   # '참석' 표시가 보이는 상태로 다시 캡처
        pg.locator(".item:not([data-sess])").first.click(); pg.wait_for_timeout(1200)
        shot("phone-09-company", full=True)
        pg.click("#trBtn"); pg.wait_for_timeout(600)
        pg.fill("#trText", "What is the lead time for the 20 kg payload cobot?")
        pg.click("#trGo"); pg.wait_for_timeout(1200)
        shot("phone-10-translate")
        pg.locator("[data-close]").first.click(); pg.wait_for_timeout(400)
        pg.goto(BASE + "/#/rec"); pg.wait_for_timeout(1000)
        shot("phone-11-rec-pick", full=True)
        pg.goto(BASE + "/#/export"); pg.wait_for_timeout(1000)
        shot("phone-12-export-before", full=True)
        pg.click("#buildBtn"); pg.wait_for_timeout(2500)
        shot("phone-13-export-ready", full=True)
        pg.goto(BASE + "/#/list"); pg.wait_for_timeout(800)
        pg.click("#addBtn"); pg.wait_for_timeout(600)
        pg.fill("#acName", "깜짝부스 테크"); pg.fill("#acHall", "4"); pg.fill("#acBooth", "4Z99")
        shot("phone-14-add-company")
        b.close()
    print(errs)
main()
