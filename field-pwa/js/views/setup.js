// 첫 화면 / 새 출장: 패키지 ZIP 불러오기 또는 직접 만들기
import * as db from "../db.js";
import { esc, icons, openSheet, pickFile, toast } from "../ui.js";
import { listServerPackages, downloadServerPackage } from "../cloud.js";
import { createTrip, todayISO } from "../model.js";
import { importTripPackage } from "../importer.js";

export async function renderSetup(root, ctx) {
  const hasTrip = !!ctx.trip;
  const today = todayISO();
  root.innerHTML = `
    ${
      hasTrip
        ? `<div class="appbar"><button class="icon-btn" id="backBtn" aria-label="돌아가기">${icons.back(24)}</button><div class="appbar-main"><div class="appbar-title">새 출장 · 패키지</div></div></div>`
        : `<div class="header"><div class="eyebrow">Trip Field</div><h1 class="title">출장을 시작해 볼까요?</h1><div class="small muted">노트북에서 만든 패키지를 불러오거나, 직접 만들 수 있어요.</div></div>`
    }
    <div class="scroll"><div class="stack">
      <div class="card stack">
        <div style="font-weight:800;font-size:17px">출장 패키지 불러오기</div>
        <div class="small muted">노트북(Trip Desk)에서 만든 ZIP 파일이에요. 전시장 맵, 후보 업체, 일정이 한 번에 들어와요. 다시 불러와도 방문 기록은 지워지지 않아요.</div>
        <button class="btn btn-primary btn-block" id="srvBtn">서버에서 불러오기</button>
        <div class="tiny muted">Desk 에서 '폰으로 보내기'를 누른 출장이 목록에 나와요. 설정에 서버 주소와 토큰이 있어야 해요.</div>
        <button class="btn btn-block" id="pkgBtn">ZIP 파일 선택</button>
      </div>
      <div class="card stack">
        <div style="font-weight:800;font-size:17px">직접 만들기</div>
        <div class="field"><label for="tName">출장 이름</label><input id="tName" class="input" placeholder="예: SPS 2026" autocomplete="off"></div>
        <div class="field"><label for="tVenue">장소</label><input id="tVenue" class="input" placeholder="예: Nuremberg Messe" autocomplete="off"></div>
        <div class="row">
          <div class="field" style="flex:1"><label for="tStart">시작일</label><input id="tStart" class="input" type="date" value="${today}"></div>
          <div class="field" style="flex:1"><label for="tEnd">종료일</label><input id="tEnd" class="input" type="date" value="${today}"></div>
        </div>
        <button class="btn btn-dark btn-block" id="createBtn">출장 만들기</button>
        <div class="tiny muted">만든 뒤 맵 화면에서 공식 평면도(PDF/PNG)를 불러올 수 있어요.</div>
      </div>
      <button class="btn btn-block" id="settingsBtn">${icons.gear(18)}번역 서버 설정</button>
    </div></div>`;

  root.querySelector("#backBtn")?.addEventListener("click", () => (location.hash = "#/map"));
  root.querySelector("#settingsBtn").onclick = () => (location.hash = "#/settings");

  root.querySelector("#srvBtn").onclick = async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const items = await listServerPackages();
      if (!items.length) { toast("서버에 올라온 출장이 없어요. Desk 에서 '폰으로 보내기'를 먼저 눌러 주세요.", 4500); return; }
      const when = (t) => (t ? new Date(t).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
      const { el, close } = openSheet(`<div class="sheet-head"><h2 class="sheet-title">서버의 출장</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div>
        <div class="stack">${items.map((p) => `<button class="btn btn-block" data-id="${esc(p.id)}" style="text-align:left;display:block"><b>${esc(p.name || p.id)}</b><div class="small muted">${esc(when(p.at))} 업로드 · ${Math.round((p.size || 0) / 1024)}KB</div></button>`).join("")}</div>`);
      el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = async () => {
        b.disabled = true;
        try {
          const r = await importTripPackage(await downloadServerPackage(b.dataset.id));
          close();
          toast(`'${r.trip.name}' 불러옴 · 업체 ${r.added + r.updated}곳 · 맵 ${r.maps}장`, 4000);
          location.hash = "#/map";
          ctx.rerender();
        } catch (err) { toast(err.message, 5000); b.disabled = false; }
      }));
    } catch (err) {
      toast(err.message, 5000);
    } finally {
      btn.disabled = false;
    }
  };

  root.querySelector("#pkgBtn").onclick = async (e) => {
    const btn = e.currentTarget; // await 뒤에는 currentTarget 이 null 이 되므로 먼저 잡아 둔다
    const file = await pickFile(".zip,application/zip");
    if (!file) return;
    btn.disabled = true;
    btn.textContent = "불러오는 중…";
    try {
      const r = await importTripPackage(file);
      toast(`'${r.trip.name}' 불러옴 · 업체 ${r.added + r.updated}곳 · 맵 ${r.maps}장`, 4000);
      location.hash = "#/map";
      ctx.rerender();
    } catch (err) {
      toast(err.message, 5000);
      btn.disabled = false;
      btn.textContent = "ZIP 파일 선택";
    }
  };

  root.querySelector("#createBtn").onclick = async () => {
    const name = root.querySelector("#tName").value.trim();
    const start = root.querySelector("#tStart").value;
    const end = root.querySelector("#tEnd").value || start;
    if (!name) return toast("출장 이름을 입력해 주세요.");
    if (!start) return toast("시작일을 입력해 주세요.");
    await createTrip({ name, venue: root.querySelector("#tVenue").value, startDate: start, endDate: end });
    location.hash = "#/map";
    ctx.rerender();
  };
}
