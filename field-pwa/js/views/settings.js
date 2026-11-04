// 설정: 번역 서버, 저장공간, 출장 관리
import * as db from "../db.js";
import { esc, icons, pickFile, toast, confirmDialog } from "../ui.js";
import { formatBytes } from "../model.js";
import { testConnection } from "../translate.js";
import { importMapFile } from "../importer.js";

export async function renderSettings(root, ctx) {
  const s = db.loadSettings();
  const trips = (await db.getAll("trips")).sort((a, b) => b.createdAt - a.createdAt);
  const activeId = db.getActiveTripId();

  let storageText = "확인할 수 없어요";
  let persisted = null;
  try {
    const est = await navigator.storage?.estimate?.();
    if (est?.usage != null) storageText = `${formatBytes(est.usage)} 사용 중${est.quota ? ` / 여유 한도 약 ${formatBytes(est.quota)}` : ""}`;
    persisted = await navigator.storage?.persisted?.();
  } catch {
    /* 무시 */
  }

  root.innerHTML = `
    <div class="appbar"><button class="icon-btn" id="backBtn" aria-label="돌아가기">${icons.back(24)}</button><div class="appbar-main"><div class="appbar-title">설정</div></div></div>
    <div class="scroll"><div class="stack">
      <div class="card stack">
        <div style="font-weight:800;font-size:17px">번역 서버</div>
        <div class="small muted">팀에서 정한 Cloudflare Worker 주소와, 나에게 발급된 토큰을 입력하세요. Gemini 키는 앱에 저장되지 않아요.</div>
        <div class="field"><label for="sUrl">서버 주소</label><input id="sUrl" class="input" inputmode="url" autocapitalize="off" autocomplete="off" placeholder="https://trip-translate.example.workers.dev" value="${esc(s.workerUrl)}"></div>
        <div class="field"><label for="sToken">토큰 (또는 설치 때 받은 설정 링크 전체)</label><input id="sToken" class="input" type="password" autocapitalize="off" autocomplete="off" value="${esc(s.token)}"></div>
        <div class="row"><button class="btn btn-block" id="sTest">연결 시험</button><button class="btn btn-dark btn-block" id="sSave">저장</button></div>
        <div class="small" id="sResult" aria-live="polite"></div>
      </div>

      <div class="card stack">
        <div style="font-weight:800;font-size:17px">저장공간</div>
        <div class="small">${esc(storageText)}</div>
        <div class="small muted">${persisted ? "이 기기는 데이터를 자동으로 지우지 않도록 설정되어 있어요." : "브라우저가 오래 쓰지 않은 데이터를 지울 수 있어요. 매일 저녁 내보내기를 꼭 해 주세요."}</div>
        ${persisted ? "" : `<button class="btn btn-block" id="persistBtn">자동 삭제 방지 요청</button>`}
      </div>

      <div class="card stack">
        <div style="font-weight:800;font-size:17px">출장 관리</div>
        ${trips
          .map(
            (t) => `<div class="row" style="min-height:48px">
              <div class="item-main"><div class="item-name" style="font-size:15px">${esc(t.name)}${t.id === activeId ? ` <span class="pill pill-blue" style="padding:2px 8px">사용 중</span>` : ""}</div><div class="tiny muted">${esc(t.days[0])} ~ ${esc(t.days[t.days.length - 1])}</div></div>
              ${t.id === activeId ? "" : `<button class="btn btn-sm" data-use="${t.id}">전환</button>`}
              <button class="icon-btn" data-del="${t.id}" aria-label="출장 삭제" style="color:var(--sub)">${icons.trash(20)}</button>
            </div>`,
          )
          .join("")}
        ${activeId ? `<button class="btn btn-block" id="mapBtn">맵 파일 다시 불러오기 (PDF/PNG)</button>` : ""}
        <button class="btn btn-block" id="newBtn">${icons.plus(18)}새 출장 · 패키지 불러오기</button>
      </div>
      <div class="tiny muted" style="text-align:center">Trip Field v0.1</div>
    </div></div>`;

  const $ = (sel) => root.querySelector(sel);
  $("#backBtn").onclick = () => (location.hash = ctx.trip ? "#/map" : "#/setup");

  const saveFromForm = () => db.saveSettings({ workerUrl: $("#sUrl").value.trim(), token: $("#sToken").value.trim().replace(/^.*[?#&]t=/, "") });  // 설정 링크 전체를 붙여 넣어도 토큰만 저장한다
  $("#sSave").onclick = () => {
    saveFromForm();
    toast("저장했어요.");
  };
  $("#sTest").onclick = async (e) => {
    saveFromForm();
    const btn = e.currentTarget;
    const out = $("#sResult");
    btn.disabled = true;
    out.style.color = "var(--sub)";
    out.textContent = "확인 중…";
    try {
      out.textContent = await testConnection();
      out.style.color = "var(--blue)";
    } catch (err) {
      out.textContent = err.message;
      out.style.color = "var(--orange)";
    } finally {
      btn.disabled = false;
    }
  };

  $("#persistBtn")?.addEventListener("click", async () => {
    const ok = await navigator.storage?.persist?.();
    toast(ok ? "자동 삭제 방지를 켰어요." : "이 브라우저에서는 허용되지 않았어요. 홈 화면에 추가하면 도움이 돼요.", 4000);
    ctx.rerender();
  });

  root.querySelectorAll("[data-use]").forEach((b) => {
    b.onclick = () => {
      db.setActiveTripId(b.dataset.use);
      location.hash = "#/map";
      ctx.rerender();
    };
  });
  root.querySelectorAll("[data-del]").forEach((b) => {
    b.onclick = async () => {
      const t = trips.find((x) => x.id === b.dataset.del);
      if (!(await confirmDialog(`'${t.name}' 출장과 모든 기록(녹음·메모·사진)을 이 폰에서 삭제할까요? 먼저 내보내기를 했는지 확인하세요.`, "삭제"))) return;
      for (const store of ["companies", "recordings", "memos", "photos", "maps", "exports"]) {
        if (store === "recordings") {
          const recs = await db.getAllByIndex("recordings", "tripId", t.id);
          for (const r of recs) await db.delAllByIndex("chunks", "recId", r.id);
        }
        await db.delAllByIndex(store, "tripId", t.id);
      }
      await db.del("trips", t.id);
      if (activeId === t.id) localStorage.removeItem("tf.activeTripId");
      toast("삭제했어요.");
      location.hash = "#/map";
      ctx.rerender();
    };
  });
  $("#newBtn").onclick = () => (location.hash = "#/setup");
  $("#mapBtn")?.addEventListener("click", async () => {
    const file = await pickFile(".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*");
    if (!file) return;
    toast("맵을 변환하고 있어요…", 8000);
    try {
      const n = await importMapFile(activeId, file);
      toast(`맵 ${n}장을 불러왔어요.`);
    } catch (err) {
      toast(err.message, 5000);
    }
  });
}
