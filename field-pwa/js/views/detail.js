// 업체 상세: 사전 메모/질문, 녹음(누적), 내 메모, 사진, 번역
import * as db from "../db.js";
import { esc, icons, pickFile, toast, confirmDialog } from "../ui.js";
import { ensureVisited, formatDuration, formatTime, isVisited, loadCompanyRecords, visitNumber } from "../model.js";
import { Recorder, isRecordingSupported } from "../recorder.js";
import { openTranslate } from "./shared.js";

const recorder = new Recorder();
let recordingCompanyId = null;

export function activeRecordingCompanyId() {
  return recorder.active ? recordingCompanyId : null;
}

async function downscale(file, maxSide = 2000, quality = 0.85) {
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (k >= 1 && file.size < 1_500_000) {
      bmp.close?.();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * k);
    canvas.height = Math.round(bmp.height * k);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close?.();
    const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));
    return blob || file;
  } catch {
    return file;
  }
}

export async function renderDetail(root, ctx, companyId) {
  const { trip, day } = ctx;
  const company = await db.get("companies", companyId);
  if (!company) {
    location.hash = "#/list";
    return;
  }
  const { recordings, memos, photos } = await loadCompanyRecords(company.id);
  const urls = [];
  const objectUrl = (blob) => {
    const u = URL.createObjectURL(blob);
    urls.push(u);
    return u;
  };

  const place = [company.category, company.hall && `홀 ${company.hall}`, company.booth && `부스 ${company.booth}`].filter(Boolean).join(" · ");
  const isRecordingHere = recorder.active && recordingCompanyId === company.id;
  const totalSec = recordings.reduce((s, r) => s + (r.duration || 0), 0);
  const draftKey = `tf.draft.${company.id}`;
  const draft = localStorage.getItem(draftKey) || "";

  // 같은 날 두 번째 이후 녹음은 "이어서" 표시
  const seenDay = new Map();
  const recRows = recordings
    .map((r) => {
      const n = visitNumber(recordings, r);
      const idx = seenDay.get(r.day) || 0;
      seenDay.set(r.day, idx + 1);
      return `
      <div class="rec-row" data-rec="${r.id}">
        <button class="round" data-play="${r.id}" aria-label="녹음 재생" style="color:var(--ink)">${icons.play(18)}</button>
        <div class="item-main"><div class="item-name" style="font-size:15px">${n}차 방문 · ${formatTime(r.createdAt)}${idx > 0 ? " (이어서)" : ""}${r.recovered ? " · 복구됨" : ""}</div><div class="tiny muted">${formatDuration(r.duration)}</div></div>
        <button class="icon-btn" data-del-rec="${r.id}" aria-label="녹음 삭제" style="color:var(--sub)">${icons.trash(20)}</button>
      </div>`;
    })
    .join("");

  root.innerHTML = `
    <div class="appbar">
      <button class="icon-btn" id="backBtn" aria-label="리스트로 돌아가기">${icons.back(24)}</button>
      <div class="appbar-main"><div class="appbar-title">${esc(company.name)}</div><div class="small muted">${esc(place || "정보 없음")}${company.core ? ` <span class="pill core-pill">★ 핵심 업체</span>` : ""}${company.dup ? ` <span class="pill dup-pill">중복 ${company.dup.i}/${company.dup.n}</span>` : ""}</div></div>
      ${isVisited(company, day) ? `<span class="pill pill-blue">오늘 방문함</span>` : `<button class="btn btn-sm" id="visitBtn">방문 체크</button>`}
    </div>
    <div class="scroll" style="padding-top:10px">
      <div class="stack">
        ${company.addedOnSite ? `<div><span class="pill pill-orange">현장 추가</span></div>` : ""}
        ${
          company.preNotes || company.questions?.length
            ? `<div class="card">
                ${company.preNotes ? `<div class="card-title">사전조사 메모</div><div style="line-height:1.6;white-space:pre-wrap;margin-bottom:${company.questions?.length ? 12 : 0}px">${esc(company.preNotes)}</div>` : ""}
                ${
                  company.questions?.length
                    ? `<div class="card-title">사전 질문 체크</div>${company.questions
                        .map((q, i) => `<button class="q-item" data-q="${i}" aria-pressed="${!!q.done}"><span class="box ${q.done ? "on" : ""}">${q.done ? `<span style="color:#fff">${icons.check(14)}</span>` : ""}</span><span style="${q.done ? "color:var(--sub)" : ""}">${esc(q.text)}</span></button>`)
                        .join("")}`
                    : ""
                }
              </div>`
            : ""
        }
        <div class="card">
          <div class="row" style="justify-content:space-between;align-items:baseline"><div class="card-title" style="margin:0">녹음 · ${recordings.length}건 누적</div><div class="tiny muted">총 ${formatDuration(totalSec)}</div></div>
          ${recRows || `<div class="small muted" style="padding:10px 0 2px">아직 녹음이 없어요. 아래 버튼으로 시작하세요.</div>`}
        </div>
        <div class="card">
          <div class="card-title">내 메모 · 보고서에 원문 그대로 반영</div>
          ${memos
            .map(
              (m) => `<div class="row" style="align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--line-soft)">
                <div style="flex:1;line-height:1.55;white-space:pre-wrap">${m.important ? `<span class="pill pill-orange" style="padding:2px 8px;margin-right:6px">${icons.star(12)}중요</span>` : ""}${esc(m.text)}<div class="tiny muted" style="margin-top:2px">Day ${m.day ?? "?"} · ${formatTime(m.createdAt)}</div></div>
                <button class="icon-btn" data-star="${m.id}" aria-label="중요 표시 바꾸기" style="width:36px;height:36px;color:${m.important ? "var(--orange)" : "var(--sub)"}">${icons.star(18)}</button>
                <button class="icon-btn" data-del-memo="${m.id}" aria-label="메모 삭제" style="width:36px;height:36px;color:var(--sub)">${icons.trash(18)}</button>
              </div>`,
            )
            .join("")}
          <div class="stack" style="margin-top:10px;gap:8px">
            <textarea class="textarea" id="memoText" placeholder="직접 메모 (중요한 내용은 직접 적어 두세요)" aria-label="새 메모">${esc(draft)}</textarea>
            <div class="row">
              <button class="star-btn" id="memoStar" aria-pressed="false">${icons.star(14)}중요</button>
              <button class="btn btn-sm btn-dark" id="memoSave" style="margin-left:auto">메모 저장</button>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="row" style="justify-content:space-between"><div class="card-title" style="margin:0">사진 · 명함 ${photos.length ? `(${photos.length}장)` : ""}</div>
            <button class="btn btn-sm" id="photoBtn">${icons.camera(18)}촬영·선택</button></div>
          ${photos.length ? `<div class="thumbs" style="margin-top:10px">${photos.map((p) => `<button data-photo="${p.id}" style="padding:0;border:none;background:none" aria-label="사진 삭제"><img class="thumb" alt="업체 사진" src="${objectUrl(p.blob)}"></button>`).join("")}</div>` : ""}
        </div>
      </div>
    </div>
    <div class="dock">
      <div class="dock-row">
        <div style="flex:1;min-width:0"><div class="timer ${isRecordingHere ? "pulse" : ""}" id="timer">${isRecordingHere ? formatDuration((Date.now() - recorder.startedAt) / 1000) : "00:00"}</div>
          <div class="tiny muted" id="recHint">${isRecordingHere ? "녹음 중 · 화면을 켜 둔 채 두세요" : "탭하면 녹음 시작 · 화면 켜짐 유지"}</div></div>
        <button class="tr-btn" id="trBtn" aria-label="번역 열기">${icons.translate(22)}번역</button>
        <button class="rec-btn ${isRecordingHere ? "recording" : ""}" id="recBtn" aria-label="${isRecordingHere ? "녹음 정지" : "녹음 시작"}" style="color:#fff">${isRecordingHere ? `<span class="stop"></span>` : icons.micFill(32)}</button>
      </div>
    </div>`;

  const $ = (sel) => root.querySelector(sel);
  const timerEl = $("#timer");
  const tick = (sec) => {
    if (timerEl.isConnected) timerEl.textContent = formatDuration(sec);
  };
  if (isRecordingHere) recorder.onTick = tick;

  // ---- 상단 ----
  $("#backBtn").onclick = () => {
    if (recorder.active) return toast("녹음을 끝낸 뒤 이동해 주세요.");
    location.hash = "#/list";
  };
  $("#visitBtn")?.addEventListener("click", async () => {
    await ensureVisited(company, day);
    ctx.rerender();
  });

  // ---- 질문 체크 ----
  root.querySelectorAll("[data-q]").forEach((btn) => {
    btn.onclick = async () => {
      const i = Number(btn.dataset.q);
      company.questions[i].done = !company.questions[i].done;
      await db.put("companies", company);
      ctx.rerender();
    };
  });

  // ---- 녹음 재생 / 삭제 ----
  let audio = null;
  let playingId = null;
  root.querySelectorAll("[data-play]").forEach((btn) => {
    btn.onclick = () => {
      const rec = recordings.find((r) => r.id === btn.dataset.play);
      if (audio && playingId === rec.id) {
        audio.pause();
        return;
      }
      audio?.pause();
      root.querySelectorAll("[data-play]").forEach((b) => (b.innerHTML = icons.play(18)));
      audio = new Audio(objectUrl(rec.blob));
      playingId = rec.id;
      btn.innerHTML = icons.pause(18);
      audio.onended = audio.onpause = () => {
        btn.innerHTML = icons.play(18);
        if (audio && audio.ended) playingId = null;
      };
      audio.play().catch(() => toast("재생하지 못했어요."));
    };
  });
  root.querySelectorAll("[data-del-rec]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("이 녹음을 삭제할까요? 되돌릴 수 없어요.", "삭제"))) return;
      await db.del("recordings", btn.dataset.delRec);
      ctx.rerender();
    };
  });

  // ---- 메모 ----
  let important = false;
  const memoText = $("#memoText");
  memoText.addEventListener("input", () => localStorage.setItem(draftKey, memoText.value));
  $("#memoStar").onclick = (e) => {
    important = !important;
    e.currentTarget.classList.toggle("on", important);
    e.currentTarget.setAttribute("aria-pressed", String(important));
  };
  $("#memoSave").onclick = async () => {
    const text = memoText.value.trim();
    if (!text) return toast("메모를 입력해 주세요.");
    await db.put("memos", { id: db.newId(), tripId: trip.id, companyId: company.id, day, text, important, createdAt: Date.now() });
    await ensureVisited(company, day);
    localStorage.removeItem(draftKey);
    toast("메모를 저장했어요.");
    ctx.rerender();
  };
  root.querySelectorAll("[data-star]").forEach((btn) => {
    btn.onclick = async () => {
      const m = memos.find((x) => x.id === btn.dataset.star);
      m.important = !m.important;
      await db.put("memos", m);
      ctx.rerender();
    };
  });
  root.querySelectorAll("[data-del-memo]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("이 메모를 삭제할까요?", "삭제"))) return;
      await db.del("memos", btn.dataset.delMemo);
      ctx.rerender();
    };
  });

  // ---- 사진 ----
  $("#photoBtn").onclick = async () => {
    const file = await pickFile("image/*", { capture: "environment" });
    if (!file) return;
    const blob = await downscale(file);
    await db.put("photos", { id: db.newId(), tripId: trip.id, companyId: company.id, day, blob, createdAt: Date.now() });
    await ensureVisited(company, day);
    toast("사진을 저장했어요.");
    ctx.rerender();
  };
  root.querySelectorAll("[data-photo]").forEach((btn) => {
    btn.onclick = async () => {
      if (!(await confirmDialog("이 사진을 삭제할까요?", "삭제"))) return;
      await db.del("photos", btn.dataset.photo);
      ctx.rerender();
    };
  });

  // ---- 번역 ----
  $("#trBtn").onclick = () =>
    openTranslate({
      micBusy: () => recorder.active,
      onInsert: ({ source, translation }) => {
        const add = `[번역] ${translation}${source ? `\n(원문: ${source})` : ""}`;
        memoText.value = memoText.value ? `${memoText.value}\n${add}` : add;
        localStorage.setItem(draftKey, memoText.value);
        memoText.scrollIntoView({ block: "center", behavior: "smooth" });
      },
    });

  // ---- 녹음 ----
  const recBtn = $("#recBtn");
  recBtn.onclick = async () => {
    if (recorder.active) {
      recBtn.disabled = true;
      try {
        await recorder.stop();
        toast("녹음을 저장했어요.");
      } catch (e) {
        toast("녹음 저장 중 문제가 생겼어요: " + e.message, 5000);
      }
      recordingCompanyId = null;
      ctx.rerender();
      return;
    }
    if (!isRecordingSupported()) return toast("이 브라우저에서는 녹음을 쓸 수 없어요.", 4000);
    recBtn.disabled = true;
    try {
      await recorder.start({ tripId: trip.id, companyId: company.id, day }, tick);
      recordingCompanyId = company.id;
      await ensureVisited(company, day);
      ctx.rerender();
    } catch (e) {
      recBtn.disabled = false;
      toast(e?.name === "NotAllowedError" ? "마이크 권한을 허용해 주세요." : "녹음을 시작하지 못했어요: " + (e?.message || e), 5000);
    }
  };

  return () => {
    urls.forEach((u) => URL.revokeObjectURL(u));
    audio?.pause();
    if (recorder.onTick === tick) recorder.onTick = null;
  };
}

window.addEventListener("beforeunload", (e) => {
  if (recorder.active) {
    e.preventDefault();
    e.returnValue = "";
  }
});
