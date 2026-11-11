// 맵 화면: 공식 평면도(PDF/PNG)를 그대로 띄우고 이동·확대·축소만 한다.
import * as db from "../db.js";
import { esc, icons, pickFile, toast } from "../ui.js";
import { isVisited, hallMarkers, hallKey } from "../model.js";
import { importMapFile } from "../importer.js";
import { PanZoom } from "../panzoom.js";
import { headerHtml, bindHeader, openAddCompany } from "./shared.js";

const viewStates = new Map(); // 맵별 마지막 확대/위치 (같은 세션 동안 유지)
let activeMapId = null;

export async function renderMap(root, ctx) {
  const { trip, day, companies } = ctx;
  const todays = companies.filter((c) => c.day === day || isVisited(c, day));
  const done = todays.filter((c) => isVisited(c, day)).length;
  const onsite = todays.filter((c) => c.addedOnSite).length;

  const maps = (await db.getAllByIndex("maps", "tripId", trip.id)).sort((a, b) => a.order - b.order);
  if (!maps.find((m) => m.id === activeMapId)) activeMapId = maps[0]?.id || null;
  const map = maps.find((m) => m.id === activeMapId);

  root.innerHTML = `
    ${headerHtml(trip, day)}
    <div class="map-wrap">
      ${
        map
          ? `<div class="pz-viewport" id="pz"><img class="pz-img" id="pzImg" alt="전시장 평면도" draggable="false"></div>
             <div class="map-badge">${maps.length > 1 ? maps.map((m) => `<button class="map-tab ${m.id === map.id ? "active" : ""}" data-map="${m.id}">${esc(m.name)}</button>`).join("") : `공식 평면도`}</div>
             <div class="map-zoom"><button id="zIn" aria-label="확대">+</button><button id="zOut" aria-label="축소">−</button><button id="zFit" aria-label="맞춤" style="font-size:13px;font-weight:800">맞춤</button></div>
             <div class="map-hint">드래그로 이동 · 두 손가락으로 확대/축소</div>`
          : `<div class="empty">
               ${icons.map(40)}
               <div style="font-weight:800;color:var(--ink);font-size:17px">전시장 맵이 아직 없어요</div>
               <div class="small">공식 사이트에서 받은 PDF나 PNG 파일을 불러오세요.</div>
               <button class="btn btn-dark" id="loadMap">맵 파일 불러오기</button>
             </div>`
      }
    </div>
    <div class="map-bar"><div><b>오늘 ${todays.length - onsite}곳</b><span class="muted"> · 완료 ${done}${onsite ? ` · 현장 추가 ${onsite}` : ""}</span>
      <div class="tiny muted"><i class="lg todo"></i>남은 <i class="lg done"></i>완료</div></div>
      <button class="btn btn-primary" id="fabAdd">${icons.plus(18)}업체 추가</button></div>`;

  bindHeader(root, trip, ctx);
  root.querySelector("#fabAdd").onclick = () => openAddCompany(ctx);

  if (!map) {
    root.querySelector("#loadMap").onclick = async () => {
      const file = await pickFile(".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*");
      if (!file) return;
      toast("맵을 변환하고 있어요…", 8000);
      try {
        const n = await importMapFile(trip.id, file);
        toast(`맵 ${n}장을 불러왔어요.`);
        ctx.rerender();
      } catch (e) {
        toast(e.message, 5000);
      }
    };
    return;
  }

  const img = root.querySelector("#pzImg");
  const url = URL.createObjectURL(map.blob);
  img.src = url;
  const pz = new PanZoom(root.querySelector("#pz"), img, {
    initial: viewStates.get(map.id),
    onChange: (s) => viewStates.set(map.id, s),
  });
  // 홀 표시: 오늘 가는 업체를 홀별로 묶어 지도 위에 얹는다 (Desk 에서 정한 위치 사용)
  const pageIdx = Math.max(0, maps.findIndex((m) => m.id === map.id));
  const { markers, missing } = hallMarkers(companies, day, trip.hallPins || {});
  const layer = document.createElement("div");
  layer.className = "hall-layer";
  root.querySelector("#pz").append(layer);
  const mine = markers.filter((m) => m.page === pageIdx);
  const pins = mine.map((m) => {
    const b = document.createElement("button");
    b.className = "hall-pin" + (m.done === m.companies.length ? " done" : "");
    b.innerHTML = `<b>${esc(m.key)}</b><i>${m.companies.length - m.done}</i>`;
    b.setAttribute("aria-label", `홀 ${m.key} 업체 ${m.companies.length}곳`);
    b.onclick = (e) => { e.stopPropagation(); showHall(root, m, day); };
    layer.append(b);
    return [b, m];
  });
  // 세션 상세의 '맵에서 홀 보기'로 들어오면 그 홀을 깜박여 보여 준다
  let focus = "";
  try { focus = sessionStorage.getItem("tf.focusHall") || ""; sessionStorage.removeItem("tf.focusHall"); } catch { /* 무시 */ }
  if (focus) {
    const hit = pins.find(([, m]) => m.key === hallKey(focus));
    if (hit) { hit[0].classList.add("flash"); showHall(root, hit[1], day); } else toast(`홀 ${focus} 은(는) 오늘 방문할 업체가 없거나 맵에 위치가 없어요.`, 3500);
  }
  const place = () => {
    const w = img.naturalWidth || map.width, hh = img.naturalHeight || map.height;
    for (const [b, m] of pins) b.style.transform = `translate(${pz.x + m.x * w * pz.scale}px, ${pz.y + m.y * hh * pz.scale}px) translate(-50%,calc(-100% - 16px))`;
  };
  pz.onChange = (s) => { viewStates.set(map.id, s); place(); };
  if (img.complete) place(); else img.addEventListener("load", place);
  place();
  const hint = root.querySelector(".map-hint");
  if (hint && missing.length) hint.textContent = `위치 미지정 홀: ${missing.join(", ")} · 드래그로 이동`;
  root.querySelector("#zIn").onclick = () => pz.zoomBy(1.6);
  root.querySelector("#zOut").onclick = () => pz.zoomBy(1 / 1.6);
  root.querySelector("#zFit").onclick = () => pz.reset();
  root.querySelectorAll("[data-map]").forEach((b) => {
    b.onclick = () => {
      activeMapId = b.dataset.map;
      ctx.rerender();
    };
  });
  return () => {
    pz.destroy();
    URL.revokeObjectURL(url);
  };
}

function showHall(root, m, day) {
  root.querySelector(".hall-sheet")?.remove();
  const el = document.createElement("div");
  el.className = "hall-sheet";
  el.innerHTML = `<div class="hs-h"><b>홀 ${esc(m.key)}</b><span>${m.done}/${m.companies.length} 완료</span><button aria-label="닫기">×</button></div>` +
    m.companies.map((c) => `<div class="hs-r${isVisited(c, day) ? " done" : ""}">${esc(c.name)}<small>${esc(c.booth || "")}${c.dup ? ` · ⚠ 중복 ${c.dup.i}/${c.dup.n}` : ""}</small></div>`).join("");
  el.querySelector("button").onclick = () => el.remove();
  root.querySelector(".map-wrap").append(el);
}
