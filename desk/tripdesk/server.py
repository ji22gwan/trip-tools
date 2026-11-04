"""로컬 웹 서버(표준 라이브러리만 사용). 127.0.0.1 에만 열린다."""
import json
import mimetypes

mimetypes.add_type("text/javascript", ".mjs")  # 일부 환경에서 .mjs 가 text/plain 으로 나와 모듈 로딩이 막힌다
import os
import re
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import companies_io, daily, dayai, mapfinder, package, reports, research, transcribe, travel
from .store import Store, StoreError

WEB = Path(__file__).parent / "web"
MAX_BODY = 100 * 1024 * 1024  # 일반 요청 상한
MAX_IMPORT = 8 * 1024**3  # 일간 ZIP 은 파일로 흘려 받는다
ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn.__name__))
        return fn
    return deco


def jbody(body) -> dict:
    d = json.loads(body or b"{}")
    if not isinstance(d, dict):
        raise ValueError("객체 형태의 JSON 이 필요해요")
    return d


class Api:
    """요청 처리 로직. 핸들러와 분리해 두면 서버 없이도 시험할 수 있다."""

    def __init__(self, store: Store):
        self.store = store
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.last_ping = 0.0  # 화면이 보낸 마지막 신호(앱 창 자동 종료 판단용)
        self.httpd = None

    def trip_view(self, tid):
        s = self.store
        return {
            "trip": s.get_trip(tid),
            "companies": s.get_companies(tid),
            "glossary": s.get_glossary(tid),
            "maps": [
                {"name": p.name, "size": p.stat().st_size, "primary": p == s.primary_map(tid)} for p in s.list_maps(tid)
            ],
            "warnings": package.check(s, tid),
        }

    @route("GET", r"/api/ping")
    def ping(self, m, q, body):
        self.last_ping = time.time()
        return {"tripdesk": True}

    @route("POST", r"/api/quit")
    def quit(self, m, q, body):
        """화면의 '종료' 버튼. 응답을 보낸 뒤 서버를 끈다."""
        if self.httpd:
            threading.Timer(0.3, self.httpd.shutdown).start()
        return {"ok": True}

    @route("GET", r"/api/trips")
    def list_trips(self, m, q, body):
        out = []
        for t in self.store.list_trips():
            cs = self.store.get_companies(t["id"])
            t["pickedCount"] = len(package.picked(cs))
            t["dayStats"] = daily.list_days(self.store, t["id"])
            out.append(t)
        return {"trips": out}

    @route("POST", r"/api/trips")
    def create_trip(self, m, q, body):
        d = jbody(body)
        t = self.store.create_trip(d.get("name"), d.get("venue", ""), d.get("start", ""), d.get("end"), d.get("purpose", ""))
        known = mapfinder.known_source(t["name"], int(t["days"][0][:4]))
        if known:
            self.store.update_trip(t["id"], siteUrl=known["siteUrl"])
        return {"trip": self.store.get_trip(t["id"])}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)")
    def get_trip(self, m, q, body):
        return self.trip_view(m["tid"])

    def travel_view(self, tid):
        trip = self.store.get_trip(tid)
        tr = travel.get(self.store, tid)
        return {"travel": tr, "links": travel.links(trip, tr), "summary": travel.summary(tr, trip)}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/travel")
    def get_travel(self, m, q, body):
        return self.travel_view(m["tid"])

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/travel")
    def put_travel(self, m, q, body):
        travel.save(self.store, m["tid"], jbody(body))
        return self.travel_view(m["tid"])

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/travel/prompt")
    def travel_prompt(self, m, q, body):
        d = jbody(body)
        trip, tr = self.store.get_trip(m["tid"]), travel.get(self.store, m["tid"])
        kind = d.get("kind")
        if kind == "flights":
            return {"prompt": travel.build_flight_prompt(trip, tr)}
        if kind == "hotels":
            return {"prompt": travel.build_hotel_prompt(trip, tr)}
        if kind == "booking":
            if not str(d.get("text") or "").strip():
                raise StoreError("예약 확인 메일·문자 내용을 붙여 넣어 주세요.")
            return {"prompt": travel.build_booking_prompt(d["text"])}
        raise StoreError("알 수 없는 종류예요.")

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/travel/paste")
    def travel_paste(self, m, q, body):
        d = jbody(body)
        if d.get("kind") not in ("flights", "hotels", "booking"):
            raise StoreError("알 수 없는 종류예요.")
        try:
            r = travel.paste(self.store, m["tid"], d["kind"], str(d.get("text") or ""))
        except research.ResearchError as e:
            raise StoreError(str(e))
        return dict(self.travel_view(m["tid"]), pasted=r)

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/hall-pins")
    def put_hall_pins(self, m, q, body):
        self.store.update_trip(m["tid"], hallPins=jbody(body))
        return self.trip_view(m["tid"])

    @route("PATCH", r"/api/trips/(?P<tid>[^/]+)")
    def patch_trip(self, m, q, body):
        self.store.update_trip(m["tid"], **jbody(body))
        return self.trip_view(m["tid"])

    @route("DELETE", r"/api/trips/(?P<tid>[^/]+)")
    def delete_trip(self, m, q, body):
        self.store.delete_trip(m["tid"])
        return {"ok": True}

    # ---- 지도 ----
    @route("POST", r"/api/trips/(?P<tid>[^/]+)/maps/find")
    def find_maps(self, m, q, body):
        """알려진 공식 주소가 있으면 바로 받고, 없으면 공식 사이트에서 후보를 찾아 보여준다."""
        tid = m["tid"]
        trip = self.store.get_trip(tid)
        d = jbody(body)
        year = int(trip["days"][0][:4])
        site = (d.get("siteUrl") or trip.get("siteUrl") or "").strip()
        result = {"downloaded": [], "candidates": [], "messages": []}
        known = mapfinder.known_source(trip["name"], year)
        if known and not d.get("siteUrl"):
            site = site or known["siteUrl"]
            for url in known["mapUrls"]:
                try:
                    self._save_map(tid, url, result)
                except mapfinder.MapError as e:
                    result["messages"].append(f"알려진 공식 주소 실패: {e}")
        if site:
            self.store.update_trip(tid, siteUrl=site)
            if not result["downloaded"]:
                try:
                    result["candidates"] = mapfinder.find_map_candidates(site)
                    if not result["candidates"]:
                        result["messages"].append("그 사이트에서 지도로 보이는 파일을 찾지 못했어요. 지도 파일 링크를 직접 붙여 넣거나 파일을 올려 주세요.")
                except mapfinder.MapError as e:
                    result["messages"].append(str(e))
        elif not result["downloaded"]:
            result["messages"].append("공식 사이트 주소를 입력해 주세요. (Claude Chat 에 '<전시회 이름> 공식 사이트'를 물어봐도 돼요.)")
        result["view"] = self.trip_view(tid)
        return result

    def _save_map(self, tid, url, result):
        data, ext = mapfinder.download_map(url)
        name = self.store.add_map(tid, mapfinder.filename_for(url, ext), data, source=url)
        result["downloaded"].append({"name": name, "size": len(data), "url": url})

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/maps/download")
    def download_map(self, m, q, body):
        d = jbody(body)
        result = {"downloaded": [], "messages": []}
        self._save_map(m["tid"], d.get("url", ""), result)
        result["view"] = self.trip_view(m["tid"])
        return result

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/maps/upload")
    def upload_map(self, m, q, body):
        fname = q.get("filename", "map.pdf")
        ext = mapfinder.sniff(body)
        if not ext:
            raise mapfinder.MapError("PDF 또는 이미지 파일이 아니에요.")
        stem = Path(fname).stem or "map"
        self.store.add_map(m["tid"], stem + ext, body)
        return self.trip_view(m["tid"])

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/maps/(?P<name>[^/]+)")
    def get_map(self, m, q, body):
        name = urllib.parse.unquote(m["name"])
        for p in self.store.list_maps(m["tid"]):
            if p.name == name:
                return ("file", p)
        raise StoreError("지도 파일을 찾을 수 없어요.")

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/primary-map")
    def set_primary_map(self, m, q, body):
        self.store.set_primary_map(m["tid"], jbody(body).get("name", ""))
        return self.trip_view(m["tid"])

    @route("DELETE", r"/api/trips/(?P<tid>[^/]+)/maps/(?P<name>[^/]+)")
    def delete_map(self, m, q, body):
        self.store.delete_map(m["tid"], urllib.parse.unquote(m["name"]))
        return self.trip_view(m["tid"])

    # ---- 업체 / 용어 ----
    @route("POST", r"/api/trips/(?P<tid>[^/]+)/companies/import")
    def import_companies(self, m, q, body):
        trip = self.store.get_trip(m["tid"])
        try:
            rows, warns = companies_io.parse_companies(q.get("filename", "list.csv"), body, trip["days"])
        except companies_io.ImportError_ as e:
            raise StoreError(str(e)) from e
        merged, added, updated = companies_io.merge_companies(self.store.get_companies(m["tid"]), rows)
        for c in merged:
            c.setdefault("source", "csv")
        self.store.set_companies(m["tid"], merged)
        v = self.trip_view(m["tid"])
        v["import"] = {"added": added, "updated": updated, "warnings": warns}
        return v

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/companies")
    def put_companies(self, m, q, body):
        items = json.loads(body or b"[]")
        clean = []
        for c in items:
            if not str(c.get("name", "")).strip() or not c.get("id"):
                continue
            q_ = c.get("questions") or []
            clean.append({
                "id": str(c["id"]), "name": str(c["name"]).strip(), "category": str(c.get("category") or "기타").strip(),
                "hall": str(c.get("hall") or "").strip(), "booth": str(c.get("booth") or "").strip(),
                "day": c["day"] if isinstance(c.get("day"), int) else None,
                "preNotes": str(c.get("preNotes") or ""), "questions": [str(x) for x in q_ if str(x).strip()],
                "picked": c.get("picked") is not False, "source": str(c.get("source") or "")[:10],
                "reason": str(c.get("reason") or "")[:300], "sourceUrl": str(c.get("sourceUrl") or "")[:500],
                "verified": c.get("verified") is True, "keywords": [str(k)[:40] for k in (c.get("keywords") or [])][:8],
            })
        self.store.set_companies(m["tid"], clean)
        return self.trip_view(m["tid"])

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/glossary")
    def put_glossary(self, m, q, body):
        self.store.set_glossary(m["tid"], json.loads(body or b"[]"))
        return self.trip_view(m["tid"])

    # ---- 키워드 → Claude Chat 프롬프트 → 붙여넣기 ----
    @route("POST", r"/api/trips/(?P<tid>[^/]+)/prompt/exhibitors")
    def exhibitor_prompt(self, m, q, body):
        tid = m["tid"]
        trip = self.store.get_trip(tid)
        d = jbody(body)
        kws = research.split_keywords(d.get("keywords", ""))
        names = [c["name"] for c in self.store.get_companies(tid)]
        try:
            prompt = research.build_keyword_prompt(trip, kws, int(d.get("count") or 20), trip.get("siteUrl", ""), names)
        except research.ResearchError as e:
            raise StoreError(str(e)) from e
        return {"prompt": prompt, "keywords": kws}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/paste/exhibitors")
    def paste_exhibitors(self, m, q, body):
        tid = m["tid"]
        d = jbody(body)
        try:
            items, notes = research.sanitize(research.extract_json(d.get("text", "")))
        except research.ResearchError as e:
            raise StoreError(str(e)) from e
        if not items:
            raise StoreError("붙여 넣은 내용에서 업체를 찾지 못했어요. 답변 전체를 붙여 넣었는지 확인해 주세요.")
        merged, added, existing = research.add_candidates(self.store.get_companies(tid), items, research.split_keywords(d.get("keywords", "")))
        self.store.set_companies(tid, merged)
        v = self.trip_view(tid)
        v["pasted"] = {"added": added, "existing": existing, "notes": notes, "unverified": sum(1 for i in items if not i["verified"])}
        return v

    @route("GET", r"/api/template\.csv")
    def template(self, m, q, body):
        return ("bytes", companies_io.template_csv().encode("utf-8"), "text/csv; charset=utf-8", "업체목록_양식.csv")

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/package")
    def get_package(self, m, q, body):
        name, data = package.build_package(self.store, m["tid"])
        return ("bytes", data, "application/zip", name)

    # ---- 일간 데이터 ----
    @route("POST", r"/api/trips/(?P<tid>[^/]+)/days/import")
    def import_days(self, m, q, zip_path):
        res = daily.import_zip(self.store, m["tid"], zip_path)
        return {"imported": res, "days": daily.list_days(self.store, m["tid"])}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days")
    def list_days(self, m, q, body):
        return {"days": daily.list_days(self.store, m["tid"])}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)")
    def get_day(self, m, q, body):
        tid, n = m["tid"], int(m["n"])
        return {"report": reports.build_day(self.store, tid, n), "job": self.jobs.get(f"tr:{tid}:{n}", {"status": "idle", "message": ""})}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/file/(?P<rel>.+)")
    def day_file(self, m, q, body):
        return ("file", daily.file_path(self.store, m["tid"], int(m["n"]), urllib.parse.unquote(m["rel"])))

    @route("GET", r"/api/transcribe")
    def transcribe_info(self, m, q, body):
        ok, why = transcribe.available()
        st = self.store.get_settings()
        return {"available": ok, "reason": why, "models": transcribe.MODELS, "languages": transcribe.LANGUAGES,
                "model": st.get("whisperModel") or transcribe.DEFAULT_MODEL}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/transcribe")
    def start_transcribe(self, m, q, body):
        tid, n = m["tid"], int(m["n"])
        d = jbody(body)
        visits = daily.get_visits(self.store, tid, n)
        if not visits:
            raise StoreError("이 일차 데이터를 먼저 가져와 주세요.")
        ok, why = transcribe.available()
        if not ok:
            raise StoreError(why)
        lang = d.get("language") if d.get("language") in transcribe.LANGUAGES else "ko"
        model = d.get("model") if d.get("model") in transcribe.MODELS else transcribe.DEFAULT_MODEL
        self.store.save_settings(whisperModel=model)
        key = f"tr:{tid}:{n}"
        with self._lock:
            if self.jobs.get(key, {}).get("status") == "running":
                raise StoreError("이미 전사 중이에요.")
            self.jobs[key] = {"status": "running", "message": "시작하는 중…"}
        prompt = ", ".join(self.store.get_glossary(tid))[:800]  # 용어집을 힌트로 주면 전문 용어 인식이 좋아진다
        redo = bool(d.get("redo"))

        def work():
            st = daily.get_state(self.store, tid, n)
            try:
                done, errors = transcribe.run_day(
                    visits, st, lambda f: daily.file_path(self.store, tid, n, f), lang, prompt, model, redo,
                    lambda msg: self.jobs[key].update(message=msg), lambda: daily.save_state(self.store, tid, n, st))
                msg = f"{done}건 전사 완료" + (f" · 실패 {len(errors)}건: " + " / ".join(errors) if errors else "")
                self.jobs[key] = {"status": "error" if errors and not done else "done", "message": msg}
            except Exception as e:  # noqa: BLE001 - 백그라운드 작업이 조용히 죽지 않게 알린다
                self.jobs[key] = {"status": "error", "message": f"예상치 못한 오류: {e}"}

        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/transcribe")
    def transcribe_status(self, m, q, body):
        return {"job": self.jobs.get(f"tr:{m['tid']}:{m['n']}", {"status": "idle", "message": ""}),
                "summary": daily.day_summary(self.store, m["tid"], int(m["n"]))}

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/recording")
    def put_recording(self, m, q, body):
        d = jbody(body)
        daily.set_recording(self.store, m["tid"], int(m["n"]), d.get("file", ""), **{k: d[k] for k in ("text", "corrected") if k in d})
        return {"report": reports.build_day(self.store, m["tid"], int(m["n"]))}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/prompt")
    def day_prompt(self, m, q, body):
        tid, n = m["tid"], int(m["n"])
        visits = daily.get_visits(self.store, tid, n)
        if not visits:
            raise StoreError("이 일차 데이터를 먼저 가져와 주세요.")
        try:
            prompts = dayai.build_prompts(self.store.get_trip(tid), n, visits, daily.get_state(self.store, tid, n),
                                          self.store.get_glossary(tid), self.store.get_companies(tid))
        except research.ResearchError as e:
            raise StoreError(str(e)) from e
        return {"prompts": prompts}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/paste")
    def day_paste(self, m, q, body):
        tid, n = m["tid"], int(m["n"])
        d = jbody(body)
        visits = daily.get_visits(self.store, tid, n)
        if not visits:
            raise StoreError("이 일차 데이터를 먼저 가져와 주세요.")
        st = daily.get_state(self.store, tid, n)
        try:
            res = dayai.apply_reply(d.get("text", ""), visits, st, d.get("mode", "replace"))
        except research.ResearchError as e:
            raise StoreError(str(e)) from e
        daily.save_state(self.store, tid, n, st)
        return {"applied": res, "report": reports.build_day(self.store, tid, n)}

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/report")
    def put_day_report(self, m, q, body):
        tid, n = m["tid"], int(m["n"])
        d = jbody(body)
        st = daily.get_state(self.store, tid, n)
        if isinstance(d.get("summary"), str):
            st["summary"] = d["summary"].strip()
        if isinstance(d.get("tomorrow"), str):
            st["tomorrow"] = d["tomorrow"].strip()
        elif d.get("tomorrow") is None and "tomorrow" in d:
            st["tomorrow"] = None  # 자동 문장으로 되돌리기
        for cid, pts in (d.get("points") or {}).items():
            st["points"][cid] = [str(p).strip() for p in pts if str(p).strip()]
        daily.save_state(self.store, tid, n, st)
        return {"report": reports.build_day(self.store, tid, n)}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/report\.md")
    def day_md(self, m, q, body):
        r = reports.build_day(self.store, m["tid"], int(m["n"]))
        return ("bytes", reports.day_markdown(r).encode("utf-8"), "text/markdown; charset=utf-8", f"{r['tripName']}_day{r['day']}_보고서.md")

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/days/(?P<n>\d+)/report\.docx")
    def day_docx(self, m, q, body):
        r = reports.build_day(self.store, m["tid"], int(m["n"]))
        data = reports.day_docx(self.store, m["tid"], r)
        return ("bytes", data, DOCX, f"{r['tripName']}_day{r['day']}_보고서.docx")

    # ---- 최종 보고서 ----
    @route("GET", r"/api/trips/(?P<tid>[^/]+)/final")
    def get_final(self, m, q, body):
        return {"report": reports.build_final(self.store, m["tid"])}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/final/prompt")
    def final_prompt(self, m, q, body):
        r = reports.build_final(self.store, m["tid"])
        if not r["days"]:
            raise StoreError("가져온 일간 데이터가 없어요.")
        return {"prompt": dayai.build_final_prompt(self.store.get_trip(m["tid"]), r)}

    @route("POST", r"/api/trips/(?P<tid>[^/]+)/final/paste")
    def final_paste(self, m, q, body):
        try:
            out = dayai.apply_final(jbody(body).get("text", ""))
        except research.ResearchError as e:
            raise StoreError(str(e)) from e
        daily._write(self.store._dir(m["tid"]) / "final.json", out)
        return {"report": reports.build_final(self.store, m["tid"])}

    @route("PUT", r"/api/trips/(?P<tid>[^/]+)/final")
    def put_final(self, m, q, body):
        d = jbody(body)
        out = {"overview": str(d.get("overview") or "").strip(),
               "highlights": [str(x).strip() for x in d.get("highlights") or [] if str(x).strip()],
               "followups": [str(x).strip() for x in d.get("followups") or [] if str(x).strip()]}
        daily._write(self.store._dir(m["tid"]) / "final.json", out)
        return {"report": reports.build_final(self.store, m["tid"])}

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/final\.md")
    def final_md(self, m, q, body):
        r = reports.build_final(self.store, m["tid"])
        return ("bytes", reports.final_markdown(r).encode("utf-8"), "text/markdown; charset=utf-8", f"{r['tripName']}_최종보고서.md")

    @route("GET", r"/api/trips/(?P<tid>[^/]+)/final\.docx")
    def final_docx(self, m, q, body):
        r = reports.build_final(self.store, m["tid"])
        return ("bytes", reports.final_docx(self.store, m["tid"], r), DOCX, f"{r['tripName']}_최종보고서.docx")


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def make_handler(api: Api, port_getter):
    class H(BaseHTTPRequestHandler):
        server_version = "TripDesk"

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode())

        def _host_ok(self):
            port = port_getter()
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _handle(self, method):
            if not self._host_ok():
                return self._json(403, {"error": "허용되지 않은 접근이에요."})
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if method != "GET" and self.headers.get("X-TripDesk") != "1":
                return self._json(403, {"error": "잘못된 요청이에요."})
            if method == "GET" and not u.path.startswith("/api/"):
                return self._static(u.path)
            n = int(self.headers.get("Content-Length") or 0)
            streamed = method == "POST" and re.search(r"/days/import$", u.path)
            if n > (MAX_IMPORT if streamed else MAX_BODY):
                return self._json(413, {"error": "파일이 너무 커요."})
            tmp = None
            if streamed:  # 큰 ZIP 은 메모리에 올리지 않고 임시 파일로 받는다
                fd, tmp = tempfile.mkstemp(suffix=".zip")
                with os.fdopen(fd, "wb") as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                body = tmp
            else:
                body = self.rfile.read(n) if n else b""
            for meth, pat, fn in ROUTES:
                m = pat.match(u.path)
                if meth == method and m:
                    try:
                        out = getattr(api, fn)(m.groupdict(), q, body)
                    except (StoreError, mapfinder.MapError) as e:
                        return self._json(400, {"error": str(e)})
                    except (ValueError, KeyError, TypeError) as e:
                        return self._json(400, {"error": f"요청 내용이 올바르지 않아요: {e}"})
                    finally:
                        if tmp:
                            try:
                                os.unlink(tmp)
                            except OSError:
                                pass
                    if isinstance(out, tuple) and out[0] == "file":
                        return self._send_file(out[1])
                    if isinstance(out, tuple) and out[0] == "bytes":
                        _, data, ctype, fname = out
                        cd = "attachment; filename*=UTF-8''" + urllib.parse.quote(fname)
                        return self._send(200, data, ctype, {"Content-Disposition": cd})
                    return self._json(200, out)
            self._json(404, {"error": "없는 주소예요."})

        def _send_file(self, p):
            """오디오 탐색(재생 위치 이동)을 위해 Range 요청을 지원한다."""
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() == ".m4a":
                ctype = "audio/mp4"
            size = p.stat().st_size
            rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if rng and (rng.group(1) or rng.group(2)):
                a = int(rng.group(1)) if rng.group(1) else max(0, size - int(rng.group(2)))
                b = min(int(rng.group(2)), size - 1) if rng.group(1) and rng.group(2) else size - 1
                if a > b or a >= size:
                    return self._send(416, b"", ctype, {"Content-Range": f"bytes */{size}"})
                with open(p, "rb") as f:
                    f.seek(a)
                    data = f.read(b - a + 1)
                return self._send(206, data, ctype, {"Content-Range": f"bytes {a}-{b}/{size}", "Accept-Ranges": "bytes"})
            return self._send(200, p.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

        def _static(self, path):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            p = (WEB / rel).resolve()
            if WEB.resolve() not in p.parents or not p.is_file():
                return self._json(404, {"error": "없는 파일이에요."})
            self._send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "text/plain")

        def do_GET(self): self._handle("GET")
        def do_POST(self): self._handle("POST")
        def do_PUT(self): self._handle("PUT")
        def do_PATCH(self): self._handle("PATCH")
        def do_DELETE(self): self._handle("DELETE")

    return H


def serve(store: Store | None = None, port: int = 0, with_api: bool = False):
    api = Api(store or Store())
    holder = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api, lambda: holder["port"]))
    api.httpd = httpd
    holder["port"] = httpd.server_address[1]
    return (httpd, holder["port"], api) if with_api else (httpd, holder["port"])
