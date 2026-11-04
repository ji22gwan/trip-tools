// 여러 화면에서 쓰는 조각: 헤더, 업체 추가 시트, 번역 팝업
import { esc, icons, openSheet, toast } from "../ui.js";
import * as db from "../db.js";
import { addCompany, dayLabel } from "../model.js";
import { LANGUAGES, translateText, translationConfigured, speechRecognitionClass, getLastTiming } from "../translate.js";

export function headerHtml(trip, day, { showGear = true } = {}) {
  const options = trip.days
    .map((_, i) => `<option value="${i + 1}" ${i + 1 === day ? "selected" : ""}>${esc(dayLabel(trip, i + 1))}</option>`)
    .join("");
  return `
    <div class="header">
      <div class="header-row">
        <div>
          <div class="eyebrow">${esc(trip.name)}${trip.venue ? " · " + esc(trip.venue) : ""}</div>
          <label class="day-select"><span class="hidden">날짜 선택</span><select id="daySel" aria-label="날짜 선택">${options}</select></label>
        </div>
        <div class="row" style="gap:0">
          <span class="pill pill-blue pill-offline" id="netPill">온라인</span>
          ${showGear ? `<button class="icon-btn" id="gearBtn" aria-label="설정">${icons.gear(24)}</button>` : ""}
        </div>
      </div>
    </div>`;
}

export function bindHeader(root, trip, ctx) {
  root.querySelector("#daySel")?.addEventListener("change", (e) => {
    db.setSelectedDay(trip.id, Number(e.target.value));
    ctx.rerender();
  });
  root.querySelector("#gearBtn")?.addEventListener("click", () => {
    location.hash = "#/settings";
  });
  const pill = root.querySelector("#netPill");
  if (pill) {
    const update = () => {
      pill.textContent = navigator.onLine ? "온라인" : "오프라인";
    };
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
  }
}

// ---------- 업체 추가 ----------
export function openAddCompany(ctx, { onAdded } = {}) {
  const { trip, day, companies } = ctx;
  const categories = [...new Set(companies.map((c) => c.category).filter(Boolean))];
  const { el, close } = openSheet(
    `
    <div class="sheet-head"><h2 class="sheet-title">업체 추가</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div>
    <div class="field"><label for="acName">업체 이름</label><input id="acName" class="input" autocomplete="off" placeholder="명함이나 부스 간판 그대로"></div>
    <div class="field"><label for="acCat">카테고리</label>
      <input id="acCat" class="input" list="acCats" autocomplete="off" placeholder="예: 휴머노이드, 용접">
      <datalist id="acCats">${categories.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></div>
    <div class="row">
      <div class="field" style="flex:1"><label for="acHall">홀</label><input id="acHall" class="input" placeholder="3A"></div>
      <div class="field" style="flex:1"><label for="acBooth">부스</label><input id="acBooth" class="input" placeholder="215"></div>
    </div>
    <button class="btn btn-primary btn-block" id="acSave">추가하고 열기</button>`,
    { bottom: true },
  );
  el.querySelector("#acName").focus();
  el.querySelector("#acSave").onclick = async () => {
    const name = el.querySelector("#acName").value.trim();
    if (!name) {
      toast("업체 이름을 입력해 주세요.");
      return;
    }
    const c = await addCompany(trip, {
      name,
      category: el.querySelector("#acCat").value,
      hall: el.querySelector("#acHall").value,
      booth: el.querySelector("#acBooth").value,
      day,
    });
    close();
    onAdded?.(c);
    location.hash = `#/company/${c.id}`;
  };
}

// ---------- 번역 팝업 ----------
// micBusy: 녹음 중이면 true 를 돌려주는 함수. 마이크를 이미 쓰고 있을 때 음성 인식을 켜면 녹음이 끊길 수 있어 막는다.
export function openTranslate({ initialText = "", onInsert, micBusy } = {}) {
  const s = db.loadSettings();
  const langOptions = (sel) => LANGUAGES.map((l) => `<option value="${l.code}" ${l.code === sel ? "selected" : ""}>${l.label}</option>`).join("");
  const SR = speechRecognitionClass();
  const busy = !!micBusy?.();
  const { el, close } = openSheet(`
    <div class="sheet-head"><h2 class="sheet-title">번역</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div>
    <div class="lang-row">
      <select class="select" id="trFrom" aria-label="원문 언어">${langOptions(s.fromLang)}</select>
      <button class="icon-btn" id="trSwap" aria-label="언어 바꾸기" style="background:var(--bg)">${icons.swap(20)}</button>
      <select class="select" id="trTo" aria-label="번역 언어">${langOptions(s.toLang)}</select>
    </div>
    <div class="tr-src">
      <div class="tr-label">원문 · 입력하거나 말하기</div>
      <textarea id="trText" placeholder="번역할 문장" aria-label="원문">${esc(initialText)}</textarea>
      <div class="row">
        ${SR && !busy ? `<button class="btn btn-sm" id="trSpeak">${icons.mic(16)}<span>말해서 입력</span></button>` : ""}
        ${busy ? `<span class="tiny muted">녹음 중에는 직접 입력해 주세요. (음성 입력이 녹음을 끊을 수 있어요)</span>` : ""}
        <button class="btn btn-sm btn-dark" id="trGo" style="margin-left:auto">번역</button>
      </div>
    </div>
    <div class="tr-out"><div class="tr-label">번역</div><div class="text" id="trOut" aria-live="polite">—</div><div class="tiny muted" id="trTime"></div></div>
    <div class="row">
      <button class="btn btn-block" id="trCopy">복사</button>
      ${onInsert ? `<button class="btn btn-dark btn-block" id="trInsert">내 메모에 추가</button>` : ""}
    </div>
    <div class="tiny muted" style="line-height:1.5">현장 이해용 간이 번역이에요. 온라인일 때만 동작하고, 정확한 내용은 저녁 보고서 단계에서 다시 교정합니다.${translationConfigured() ? "" : " 설정에서 번역 서버 주소와 토큰을 먼저 입력해 주세요."}</div>
  `);

  const $ = (id) => el.querySelector(id);
  let controller = null;
  let recognition = null;

  const saveLangs = () => db.saveSettings({ fromLang: $("#trFrom").value, toLang: $("#trTo").value });
  $("#trFrom").onchange = saveLangs;
  $("#trTo").onchange = saveLangs;
  $("#trSwap").onclick = () => {
    const f = $("#trFrom").value;
    $("#trFrom").value = $("#trTo").value;
    $("#trTo").value = f;
    const out = $("#trOut").textContent;
    if (out && out !== "—") {
      $("#trText").value = out;
      $("#trOut").textContent = "—";
    }
    saveLangs();
  };

  async function run() {
    const text = $("#trText").value.trim();
    if (!text) {
      toast("번역할 문장을 입력해 주세요.");
      return;
    }
    controller?.abort();
    controller = new AbortController();
    $("#trGo").disabled = true;
    $("#trOut").textContent = "번역 중…";
    try {
      $("#trTime").textContent = "";
      $("#trOut").textContent = await translateText(text, $("#trFrom").value, $("#trTo").value, { signal: controller.signal });
      const t = getLastTiming();
      if (t) $("#trTime").textContent = `${(t.total / 1000).toFixed(1)}초${t.upstream != null ? ` (Gemini ${(t.upstream / 1000).toFixed(1)}초)` : ""} · ${t.model}`;
    } catch (e) {
      if (e?.name === "AbortError") return;
      $("#trOut").textContent = "—";
      toast(e.message, 4000);
    } finally {
      $("#trGo").disabled = false;
    }
  }
  $("#trGo").onclick = run;

  if (SR && !busy) {
    $("#trSpeak").onclick = () => {
      if (recognition) {
        recognition.stop();
        return;
      }
      const lang = LANGUAGES.find((l) => l.code === $("#trFrom").value)?.speech || "en-US";
      recognition = new SR();
      recognition.lang = lang;
      recognition.interimResults = false;
      recognition.onresult = (ev) => {
        const t = [...ev.results].map((r) => r[0].transcript).join(" ");
        $("#trText").value = t;
        run();
      };
      recognition.onerror = () => toast("음성 인식에 실패했어요. 직접 입력해 주세요.");
      recognition.onend = () => {
        recognition = null;
        const b = $("#trSpeak");
        if (b) b.querySelector("span").textContent = "말해서 입력";
      };
      $("#trSpeak").querySelector("span").textContent = "듣는 중… (탭하면 종료)";
      try {
        recognition.start();
      } catch {
        recognition = null;
      }
    };
  }

  $("#trCopy").onclick = async () => {
    const out = $("#trOut").textContent;
    if (!out || out === "—") return;
    try {
      await navigator.clipboard.writeText(out);
      toast("복사했어요.");
    } catch {
      toast("복사하지 못했어요. 길게 눌러 직접 복사해 주세요.");
    }
  };
  if (onInsert) {
    $("#trInsert").onclick = () => {
      const out = $("#trOut").textContent;
      if (!out || out === "—") {
        toast("먼저 번역해 주세요.");
        return;
      }
      onInsert({ source: $("#trText").value.trim(), translation: out });
      toast("메모에 추가했어요.");
      close();
    };
  }
  if (initialText) setTimeout(run, 0);
  return close;
}
