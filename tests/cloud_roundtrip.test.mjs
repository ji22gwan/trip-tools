// Desk(파이썬)가 Worker 보관함에 올린 패키지를 폰 코드가 목록으로 보고 내려받아 불러오는지, 처음부터 끝까지 시험한다
import "fake-indexeddb/auto";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const execFileP = promisify(execFile);
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
{
  const src = fs.readFileSync(path.join(here, "..", "field-pwa", "vendor", "jszip.min.js"), "utf8");
  const m = { exports: {} };
  new Function("module", "exports", "require", src)(m, m.exports, require);
  globalThis.JSZip = m.exports;
}
const mem = new Map();
globalThis.localStorage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const worker = (await import("../worker/src/index.js")).default;
const kv = new Map();
const env = {
  TOKENS: "tok-desk-1", PACKAGES: {
    async put(k, v, o) { kv.set(k, { v, meta: o?.metadata }); },
    async get(k) { return kv.get(k)?.v ?? null; },
    async delete(k) { kv.delete(k); },
    async list({ prefix }) { return { keys: [...kv].filter(([k]) => k.startsWith(prefix)).map(([name, x]) => ({ name, metadata: x.meta })) }; },
  },
};
// Worker 코드를 그대로 실제 HTTP 서버에 연결한다
const server = http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks);
  const r = await worker.fetch(new Request(`http://${req.headers.host}${req.url}`, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body }), env);
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = `http://127.0.0.1:${server.address().port}`;

test("Desk 업로드 → 서버 목록 → 폰 불러오기", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cloud-"));
  fs.mkdirSync(path.join(tmp, "home"));
  fs.writeFileSync(path.join(tmp, "home", "install.env"), `WORKER_URL="${url}"\nKV_ID="abc"\nTOKEN="tok-desk-1"\n`);
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==", "base64");
  fs.writeFileSync(path.join(tmp, "m.png"), png);
  const py = `
import sys, pathlib
sys.path.insert(0, "desk")
from tripdesk.store import Store
from tripdesk import companies_io, package, cloud
s = Store(pathlib.Path(sys.argv[1] + "/data"))
t = s.create_trip("서버 시험 출장", "Messe", "2026-11-24", "2026-11-25", "목적")
s.add_map(t["id"], "plan.png", open(sys.argv[2], "rb").read())
rows, _ = companies_io.parse_companies("l.csv", "업체명,카테고리,홀,부스,일차\\nA사,로봇,3A,1,1\\n".encode(), t["days"])
s.set_companies(t["id"], companies_io.merge_companies([], rows)[0])
print(cloud.status()["ready"])
name, data = package.build_package(s, t["id"])
print(cloud.upload_package(t["id"], t["name"], data)["id"])
`;
  // 같은 프로세스의 서버가 응답해야 하므로 비동기로 실행한다
  const out = (await execFileP("python3", ["-I", "-c", py, tmp, path.join(tmp, "m.png")], { cwd: path.join(here, ".."), env: { ...process.env, TRIP_TOOLS_HOME: path.join(tmp, "home") } })).stdout.trim().split("\n");
  assert.equal(out[0], "True");
  const tripId = out[1];
  assert.match(tripId, /^trip-/);

  // 폰 쪽: 설정에 서버 주소와 토큰이 있다고 하고 목록 → 내려받기 → 불러오기
  const db = await import("../field-pwa/js/db.js");
  db.saveSettings({ workerUrl: url, token: "tok-desk-1" });
  const cloud = await import("../field-pwa/js/cloud.js");
  const { importTripPackage } = await import("../field-pwa/js/importer.js");
  const list = await cloud.listServerPackages();
  assert.equal(list.length, 1);
  assert.equal(list[0].name, "서버 시험 출장");
  const r = await importTripPackage(await cloud.downloadServerPackage(list[0].id));
  assert.equal(r.trip.name, "서버 시험 출장");
  assert.equal(r.added, 1);
  assert.equal(r.maps, 1);

  // 틀린 토큰이면 알아듣게 실패한다
  db.saveSettings({ workerUrl: url, token: "wrong" });
  await assert.rejects(cloud.listServerPackages(), /토큰이 맞지 않아요/);
  server.close();
});
