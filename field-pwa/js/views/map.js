// 맵 화면: 공식 평면도(PDF/PNG)를 그대로 띄우고 이동·확대·축소만 한다.
import * as db from "../db.js";
import { esc, icons, pickFile, toast } from "../ui.js";
import { isVisited } from "../model.js";
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
    <div class="header" style="padding-top:0"><div class="chips">
      <div class="chip">오늘 ${todays.length - onsite}곳</div><div class="chip">완료 ${done}</div><div class="chip">현장 추가 ${onsite}</div>
    </div></div>
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
      <button class="fab" id="fabAdd">${icons.plus(18)}업체 추가</button>
    </div>`;

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
