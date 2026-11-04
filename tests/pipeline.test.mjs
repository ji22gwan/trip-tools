// 폰 앱의 저장·불러오기·내보내기 로직을 Node에서 시험한다 (브라우저 UI/녹음 장치는 제외)
import "fake-indexeddb/auto";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
// jszip.min.js 는 브라우저용 UMD 파일. 루트 package.json 이 ESM 이라 require 가 어긋나므로 직접 평가한다.
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

const db = await import("../field-pwa/js/db.js");
const model = await import("../field-pwa/js/model.js");
const { importTripPackage } = await import("../field-pwa/js/importer.js");
const { buildDayZip, collectDay } = await import("../field-pwa/js/exporter.js");
const { recoverRecordings } = await import("../field-pwa/js/recorder.js");

const samplePath = path.join(here, "..", "sample", "sample_trip_package.zip");

test("날짜 도우미", () => {
  assert.deepEqual(model.isoRange("2026-11-24", "2026-11-26"), ["2026-11-24", "2026-11-25", "2026-11-26"]);
  assert.deepEqual(model.isoRange("2026-11-30", "2026-12-01"), ["2026-11-30", "2026-12-01"]);
  assert.equal(model.dayLabel({ days: ["2026-11-24", "2026-11-25"] }, 2), "Day 2 · 11월 25일");
  assert.equal(model.formatDuration(192), "03:12");
  assert.equal(model.slugify("샘플 전시회"), "샘플_전시회");
  const trip = { days: ["2026-11-24", "2026-11-25"] };
  assert.equal(model.dayOfTimestamp(trip, new Date(2026, 10, 25, 9, 30).getTime()), 2);
  assert.equal(model.dayOfTimestamp(trip, new Date(2026, 10, 30, 9, 30).getTime()), null);
});

let trip;

test("샘플 패키지 불러오기", async () => {
  const buf = fs.readFileSync(samplePath);
  const r = await importTripPackage(buf);
  trip = r.trip;
  assert.equal(r.trip.id, "sample-trip-001");
  assert.equal(r.added, 5);
  assert.equal(r.maps, 1);
  assert.equal(r.trip.glossary.length, 5);
  assert.equal(db.getActiveTripId(), "sample-trip-001");

  const companies = await model.listCompanies(trip.id);
  assert.equal(companies.length, 5);
  const b = companies.find((c) => c.id === "c-b");
  assert.deepEqual(b.questions.map((q) => q.text), ["페이로드", "통신 방식(EtherCAT 여부)", "가격대와 납기"]);
  assert.ok(b.questions.every((q) => q.done === false));

  const maps = await db.getAllByIndex("maps", "tripId", trip.id);
  assert.equal(maps.length, 1);
  assert.ok(maps[0].blob.size > 1000);
});

test("오늘 리스트와 분류", async () => {
  const companies = await model.listCompanies(trip.id);
  const day1 = model.companiesForDay(companies, 1);
  assert.deepEqual(day1.map((c) => c.id).sort(), ["c-a", "c-b"]);
  const groups = model.groupByCategory(day1);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].title, "휴머노이드");
});

test("다시 불러와도 방문 기록과 질문 체크가 남는다", async () => {
  let companies = await model.listCompanies(trip.id);
  const b = companies.find((c) => c.id === "c-b");
  await model.setVisited(b, 1, true);
  b.questions[0].done = true;
  await db.put("companies", b);

  const r = await importTripPackage(fs.readFileSync(samplePath));
  assert.equal(r.added, 0);
  assert.equal(r.updated, 5);

  companies = await model.listCompanies(trip.id);
  const b2 = companies.find((c) => c.id === "c-b");
  assert.equal(model.isVisited(b2, 1), true);
  assert.equal(b2.questions[0].done, true);
  assert.equal(b2.questions[1].done, false);
  assert.equal((await db.getAllByIndex("maps", "tripId", trip.id)).length, 1); // 맵이 중복되지 않음
});

test("잘못된 ZIP은 알기 쉬운 오류", async () => {
  const z = new globalThis.JSZip();
  z.file("hello.txt", "x");
  const buf = await z.generateAsync({ type: "nodebuffer" });
  await assert.rejects(() => importTripPackage(buf), /출장 패키지가 아니에요/);
});

test("현장 추가 + 녹음/메모/사진 -> 하루치 ZIP", async () => {
  const added = await model.addCompany(trip, { name: "즉석 업체 G", category: "", hall: "3", booth: "220", day: 1 });
  assert.equal(added.addedOnSite, true);
  assert.equal(added.category, "기타");

  const audio = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
  const t0 = new Date(2026, 10, 24, 10, 24).getTime();
  await db.put("recordings", { id: "r1", tripId: trip.id, companyId: "c-b", day: 1, mime: "audio/mp4", createdAt: t0, duration: 192, status: "done", blob: new Blob([audio], { type: "audio/mp4" }) });
  await db.put("recordings", { id: "r2", tripId: trip.id, companyId: "c-b", day: 1, mime: "audio/mp4", createdAt: t0 + 900_000, duration: 108, status: "done", blob: new Blob([audio], { type: "audio/mp4" }) });
  await db.put("recordings", { id: "r3", tripId: trip.id, companyId: "c-b", day: 2, mime: "audio/mp4", createdAt: t0 + 86_400_000, duration: 60, status: "done", blob: new Blob([audio], { type: "audio/mp4" }) });
  await db.put("recordings", { id: "r4", tripId: trip.id, companyId: "c-a", day: 1, mime: "audio/webm", createdAt: t0, duration: 5, status: "recording" }); // 미완료는 제외
  await db.put("memos", { id: "m1", tripId: trip.id, companyId: "c-b", day: 1, text: "납기는 직접 확인할 것", important: true, createdAt: t0 + 1000 });
  await db.put("photos", { id: "p1", tripId: trip.id, companyId: added.id, day: 1, createdAt: t0, blob: new Blob([audio], { type: "image/jpeg" }) });

  const data = await collectDay(trip, 1);
  assert.deepEqual(data.companies.map((c) => c.id).sort(), ["c-b", added.id].sort());
  assert.equal(data.recordings.length, 2);

  const { blob, filename, counts, visits } = await buildDayZip(trip, 1);
  assert.equal(filename, "샘플_전시회_day1_2026-11-24.zip");
  assert.equal(counts.recordings, 2);
  assert.equal(counts.newCompanies, 1);
  assert.equal(counts.memos, 1);

  const zip = await globalThis.JSZip.loadAsync(Buffer.from(await blob.arrayBuffer()));
  const names = Object.keys(zip.files).filter((n) => !zip.files[n].dir).sort();
  const root = "trip_샘플_전시회/days/day1";
  assert.ok(names.includes(`${root}/visits.json`));
  const audioFiles = names.filter((n) => n.includes("/audio/"));
  assert.equal(audioFiles.length, 2);
  assert.ok(audioFiles.every((n) => n.endsWith(".m4a")));
  assert.equal(names.filter((n) => n.includes("/photos/")).length, 1);

  const parsed = JSON.parse(await zip.files[`${root}/visits.json`].async("string"));
  assert.equal(parsed.day, 1);
  assert.equal(parsed.date, "2026-11-24");
  const cb = parsed.companies.find((c) => c.id === "c-b");
  assert.equal(cb.recordings.length, 2);
  assert.equal(cb.memos[0].important, true);
  assert.equal(cb.visited, true);
  assert.ok(cb.recordings[0].file.startsWith("audio/"));
  const bytes = await zip.files[`${root}/${cb.recordings[0].file}`].async("uint8array");
  assert.deepEqual([...bytes], [...audio]);
  assert.equal(visits.companies.find((c) => c.addedOnSite).name, "즉석 업체 G");
});

test("방문 차수 계산", async () => {
  const recs = (await db.getAllByIndex("recordings", "companyId", "c-b")).filter((r) => r.status === "done").sort((a, b) => a.createdAt - b.createdAt);
  assert.deepEqual(recs.map((r) => model.visitNumber(recs, r)), [1, 1, 2]);
});

test("중단된 녹음 복구", async () => {
  await db.put("recordings", { id: "rx", tripId: trip.id, companyId: "c-a", day: 1, mime: "audio/webm", createdAt: Date.now(), duration: 0, status: "recording" });
  await db.put("chunks", { recId: "rx", seq: 1, blob: new Blob([new Uint8Array([4, 5])]) });
  await db.put("chunks", { recId: "rx", seq: 0, blob: new Blob([new Uint8Array([1, 2, 3])]) });
  await db.put("recordings", { id: "ry", tripId: trip.id, companyId: "c-a", day: 1, mime: "audio/webm", createdAt: Date.now(), duration: 0, status: "recording" }); // 조각 없음 -> 버림

  const n = await recoverRecordings();
  assert.equal(n, 1);
  const rx = await db.get("recordings", "rx");
  assert.equal(rx.status, "done");
  assert.equal(rx.recovered, true);
  assert.deepEqual([...new Uint8Array(await rx.blob.arrayBuffer())], [1, 2, 3, 4, 5]); // 순서대로 합쳐짐
  assert.equal(await db.get("recordings", "ry"), undefined);
  assert.equal((await db.getAllByIndex("chunks", "recId", "rx")).length, 0);
});

test("직접 출장 만들기", async () => {
  const t = await model.createTrip({ name: "직접 출장", venue: "X", startDate: "2026-12-01", endDate: "2026-12-03" });
  assert.equal(t.days.length, 3);
  assert.equal((await model.loadActiveTrip()).id, t.id);
});
