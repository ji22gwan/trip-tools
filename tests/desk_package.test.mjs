// Trip Desk(노트북)가 만든 패키지를 폰 앱 불러오기 코드가 그대로 받아들이는지 시험한다
import "fake-indexeddb/auto";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
{
  const src = fs.readFileSync(path.join(here, "..", "field-pwa", "vendor", "jszip.min.js"), "utf8");
  const m = { exports: {} };
  new Function("module", "exports", "require", src)(m, m.exports, require);
  globalThis.JSZip = m.exports;
}
const mem = new Map();
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
const { importTripPackage } = await import("../field-pwa/js/importer.js");
const model = await import("../field-pwa/js/model.js");

const py = `
import sys, pathlib
sys.path.insert(0, "desk")
from tripdesk.store import Store
from tripdesk import companies_io, package, travel
s = Store(pathlib.Path(sys.argv[1]))
t = s.create_trip("테스트 전시회", "Messe", "2026-11-24", "2026-11-25", "목적")
s.add_map(t["id"], "plan.png", open(sys.argv[2], "rb").read())
rows, _ = companies_io.parse_companies("l.csv", "업체명,카테고리,홀,부스,일차,질문\\nA사,로봇,3A,1,1,가동 시간; 가격\\nB사,센서,3,2,2,\\n".encode(), t["days"])
s.set_companies(t["id"], companies_io.merge_companies([], rows)[0])
s.set_glossary(t["id"], ["EtherCAT"])
travel.save(s, t["id"], {"hotels": [{"name": "Hotel X", "stars": 4, "address": "Hauptstr. 1", "checkIn": "2026-11-24", "checkOut": "2026-11-25", "confirmation": "H1"}]})
s.update_trip(t["id"], hallPins={"Hall 3A": {"x": 0.25, "y": 0.5, "page": 0}})
name, data = package.build_package(s, t["id"])
sys.stdout.buffer.write(data)
`;

test("Trip Desk 패키지를 폰 앱이 불러온다", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "desk-"));
  const png = path.join(here, "..", "docs", "map_sample.png");
  const mapSrc = fs.existsSync(png) ? png : path.join(tmp, "m.png");
  if (!fs.existsSync(mapSrc)) fs.writeFileSync(mapSrc, Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==", "base64"));
  const buf = execFileSync("python3", ["-I", "-c", py, path.join(tmp, "home"), mapSrc], { cwd: path.join(here, ".."), maxBuffer: 1 << 26 });
  const r = await importTripPackage(buf);
  assert.equal(r.trip.name, "테스트 전시회");
  assert.deepEqual(r.trip.days, ["2026-11-24", "2026-11-25"]);
  assert.equal(r.added, 2);
  assert.equal(r.maps, 1);
  assert.deepEqual(r.trip.glossary, ["EtherCAT"]);
  const cs = await model.listCompanies(r.trip.id);
  // 홀 위치가 폰까지 오고, 1일차 업체가 홀별로 묶여 지도에 표시된다
  assert.deepEqual(r.trip.hallPins["3A"], { x: 0.25, y: 0.5, page: 0 });
  assert.equal(r.trip.bookings.hotels[0].name, "Hotel X");
  assert.deepEqual(r.trip.bookings.flights, []);
  const hm = model.hallMarkers(cs, 1, r.trip.hallPins);
  assert.equal(hm.markers.length, 1);
  assert.equal(hm.markers[0].key, "3A");
  assert.equal(hm.markers[0].companies.length, 1);
  assert.deepEqual(model.hallMarkers(cs, 2, r.trip.hallPins).missing, ["3"]); // 2일차 B사 홀 3 은 위치 미지정
  const a = cs.find((c) => c.name === "A사");
  assert.equal(a.day, 1);
  assert.deepEqual(a.questions.map((q) => q.text), ["가동 시간", "가격"]);
  // 다시 불러오면 갱신으로 처리돼 방문 기록이 이어진다
  await model.setVisited(a, 1, true);
  const again = await importTripPackage(buf);
  assert.equal(again.added, 0);
  assert.equal(again.updated, 2);
  assert.equal(model.isVisited((await model.listCompanies(r.trip.id)).find((c) => c.name === "A사"), 1), true);
});
