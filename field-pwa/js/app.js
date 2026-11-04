// Trip Field 앱 진입점: 화면 전환(해시 라우터), 탭바, 서비스 워커
import * as db from "./db.js";
import { currentDay, listCompanies, loadActiveTrip } from "./model.js";
import { recoverRecordings } from "./recorder.js";
import { icons, toast } from "./ui.js";
import { renderMap } from "./views/map.js";
import { renderList } from "./views/list.js";
import { renderRecPick } from "./views/recpick.js";
import { renderDetail, activeRecordingCompanyId } from "./views/detail.js";
import { renderExport } from "./views/export.js";
import { renderSetup } from "./views/setup.js";
import { renderSettings } from "./views/settings.js";

const app = document.getElementById("app");
const ctx = { trip: null, day: 1, companies: [], rerender: () => render() };

let cleanup = null;
let rendering = false;
let again = false;

const TABS = [
  { name: "map", label: "맵", icon: icons.map },
  { name: "list", label: "리스트", icon: icons.list },
  { name: "rec", label: "녹음", icon: icons.mic },
  { name: "export", label: "내보내기", icon: icons.upload },
];

function parseRoute() {
  const parts = (location.hash.replace(/^#\/?/, "") || "map").split("/").filter(Boolean);
  return { name: parts[0] || "map", arg: parts[1] };
}

function tabbarHtml(active) {
  return `<nav class="tabbar" aria-label="메뉴">${TABS.map(
    (t) => `<a class="tab ${t.name === active ? "active" : ""}" href="#/${t.name}" ${t.name === active ? 'aria-current="page"' : ""}>${t.icon(24)}${t.label}</a>`,
  ).join("")}</nav>`;
}

async function renderOnce() {
  try {
    cleanup?.();
  } catch {
    /* 무시 */
  }
  cleanup = null;

  ctx.trip = await loadActiveTrip();
  if (ctx.trip) {
    ctx.day = currentDay(ctx.trip);
    ctx.companies = await listCompanies(ctx.trip.id);
  } else {
    ctx.companies = [];
  }

  let r = parseRoute();

  // 녹음 중에는 해당 업체 화면에 머무르게 한다
  const recId = activeRecordingCompanyId();
  if (recId && !(r.name === "company" && r.arg === recId)) {
    r = { name: "company", arg: recId };
    history.replaceState(null, "", `#/company/${recId}`);
  }
  // 출장이 없으면 시작 화면
  if (!ctx.trip && r.name !== "setup" && r.name !== "settings") {
    r = { name: "setup" };
    history.replaceState(null, "", "#/setup");
  }

  const showTabs = ["map", "list", "rec", "export"].includes(r.name);
  app.innerHTML = `<div class="screen"><div class="screen-body" id="body"></div>${showTabs ? tabbarHtml(r.name) : ""}</div>`;
  const body = app.querySelector("#body");

  const views = {
    map: () => renderMap(body, ctx),
    list: () => renderList(body, ctx),
    rec: () => renderRecPick(body, ctx),
    export: () => renderExport(body, ctx),
    company: () => renderDetail(body, ctx, r.arg),
    setup: () => renderSetup(body, ctx),
    settings: () => renderSettings(body, ctx),
  };
  const view = views[r.name] || views.map;
  cleanup = (await view()) || null;
}

async function render() {
  if (rendering) {
    again = true;
    return;
  }
  rendering = true;
  try {
    do {
      again = false;
      try {
        await renderOnce();
      } catch (e) {
        console.error(e);
        app.innerHTML = `<div class="header"><h1 class="title">문제가 생겼어요</h1><div class="small muted">${String(e?.message || e)}</div><button class="btn btn-dark" onclick="location.reload()">다시 시작</button></div>`;
      }
    } while (again);
  } finally {
    rendering = false;
  }
}

window.addEventListener("hashchange", () => render());

// 설치할 때 배포된 config.json 에 내 서버 주소가 있으면 설정에 미리 채운다 (이미 입력된 값은 건드리지 않는다)
async function prefillServer() {
  try {
    if (db.loadSettings().workerUrl) return;
    const res = await fetch("config.json", { cache: "no-cache" });
    if (!res.ok) return;
    const cfg = await res.json();
    if (typeof cfg.workerUrl === "string" && /^https:\/\//.test(cfg.workerUrl)) db.saveSettings({ workerUrl: cfg.workerUrl });
  } catch {
    /* 없으면 직접 입력 */
  }
}

// 설치 끝에 나오는 '설정 링크'(주소 뒤 ?t=토큰)를 폰에서 열면 토큰이 저장된다. 긴 토큰을 직접 입력할 필요가 없다.
function takeTokenFromLink() {
  const m = /^\?(?:.*&)?t=([A-Za-z0-9_-]{8,128})(?:&.*)?$/.exec(location.search);
  if (!m) return false;
  db.saveSettings({ token: m[1] });
  // 주소의 ?t=… 는 일부러 지우지 않는다: iPhone 은 '홈 화면에 추가'한 앱의 저장공간이 사파리와 따로라, 이 주소로 추가해야 토큰이 따라간다.
  return true;
}

async function boot() {
  const gotToken = takeTokenFromLink();
  await prefillServer();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("SW 등록 실패", e));
  }
  try {
    await navigator.storage?.persist?.();
  } catch {
    /* 무시 */
  }
  try {
    const n = await recoverRecordings();
    await render();
    if (gotToken) toast("서버 연결 정보를 저장했어요. 설정에서 '연결 시험'을 눌러 확인해 보세요.", 5000);
    if (n) toast(`중단됐던 녹음 ${n}건을 복구했어요.`, 4500);
  } catch (e) {
    console.error(e);
    await render();
  }
}

boot();
