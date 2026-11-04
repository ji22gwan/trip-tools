// 정적 검사: 모든 JS 문법, 상대 import 경로, 서비스 워커 캐시 목록이 실제 파일과 맞는지 확인
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "field-pwa");
let failures = 0;
const fail = (m) => {
  failures++;
  console.error("FAIL:", m);
};

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]));
}

const files = walk(root);
const appJs = files.filter((f) => f.endsWith(".js") && !f.includes(`${path.sep}vendor${path.sep}`));

// 1) 문법
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "chk-"));
for (const f of appJs) {
  const copy = path.join(tmp, path.relative(root, f).replace(/[\\/]/g, "__") + ".mjs");
  fs.copyFileSync(f, copy);
  try {
    execFileSync(process.execPath, ["--check", copy], { stdio: "pipe" });
  } catch (e) {
    fail(`syntax ${path.relative(root, f)}\n${e.stderr?.toString()}`);
  }
}

// 2) import 경로
const importRe = /(?:import\s+(?:[^'"]*?\sfrom\s+)?|import\()\s*["'](\.[^"']+)["']/g;
for (const f of appJs) {
  const src = fs.readFileSync(f, "utf8");
  for (const m of src.matchAll(importRe)) {
    const target = path.resolve(path.dirname(f), m[1]);
    if (!fs.existsSync(target)) fail(`${path.relative(root, f)} imports missing ${m[1]}`);
  }
}

// 3) 서비스 워커 캐시 목록
const sw = fs.readFileSync(path.join(root, "sw.js"), "utf8");
const shell = [...sw.slice(sw.indexOf("const SHELL"), sw.indexOf("];")).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
for (const s of shell) {
  if (s === "./") continue;
  if (!fs.existsSync(path.join(root, s))) fail(`sw.js lists missing file ${s}`);
}
const mustCache = files
  .map((f) => path.relative(root, f).replace(/\\/g, "/"))
  .filter((r) => /\.(js|css|mjs|png|webmanifest|html)$/.test(r) && r !== "sw.js");
for (const r of mustCache) if (!shell.includes(r)) fail(`sw.js does not cache ${r}`);

// 4) index.html / manifest 참조
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
for (const m of html.matchAll(/(?:href|src)="([^"#]+)"/g)) {
  if (/^(https?:)?\/\//.test(m[1])) continue;
  if (!fs.existsSync(path.join(root, m[1]))) fail(`index.html references missing ${m[1]}`);
}
const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.webmanifest"), "utf8"));
for (const i of manifest.icons) if (!fs.existsSync(path.join(root, i.src))) fail(`manifest icon missing ${i.src}`);

// 5) 화면이 쓰는 id 와 코드가 쓰는 id 가 어긋나지 않는지(오탈자 방지): querySelector("#x") 대상이 템플릿에 있는지
for (const f of appJs.filter((x) => x.includes(`${path.sep}views${path.sep}`))) {
  const src = fs.readFileSync(f, "utf8");
  const used = new Set([...src.matchAll(/(?:\$|querySelector)\(\s*["']#([A-Za-z0-9_-]+)["']\s*\)/g)].map((m) => m[1]));
  for (const id of used) {
    if (!new RegExp(`id="${id}"`).test(src) && !src.includes(`id=\\"${id}\\"`)) {
      // shared.js 에서 만든 헤더 요소는 다른 파일에서 쓸 수 있음
      if (!["daySel", "gearBtn", "netPill"].includes(id)) fail(`${path.relative(root, f)} uses #${id} but never defines it`);
    }
  }
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log(failures ? `\n${failures} problem(s)` : `static check OK (${appJs.length} js files, ${shell.length} cached files)`);
process.exit(failures ? 1 : 0);
