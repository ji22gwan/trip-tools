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
          <button class="icon-btn" id="localBtn" aria-label="식사 장소·현지 교통" style="font-size:20px">🍽</button>
          <button class="icon-btn" id="tripInfoBtn" aria-label="항공·숙소 예약" style="font-size:20px">✈</button>
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
  root.querySelector("#tripInfoBtn")?.addEventListener("click", () => openBookings(trip));
  root.querySelector("#localBtn")?.addEventListener("click", () => openLocal(trip));
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

// ---------- 항공·숙소 (Desk 에서 기록한 예약, 읽기 전용 · 오프라인에서도 열려요) ----------
const fmtDT = (x) => String(x || "").replace("T", " ");
const WD = ["일", "월", "화", "수", "목", "금", "토"];
// 24시간제 표기: 11/23(월) 12:55
const when = (dt) => { if (!dt) return ""; const [d, t] = String(dt).split("T"); const w = WD[new Date(d + "T00:00").getDay()]; return `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}(${w})${t ? " " + t : ""}`; };
const span = (m) => (m == null ? "" : m < 0 ? "시각 확인" : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`);
const mins = (a, b) => (a && b && a.includes("T") && b.includes("T") ? Math.round((new Date(b) - new Date(a)) / 6e4) : null);
// 옛 형식(편명이 바로 들어 있는 한 편짜리)도 구간 하나짜리 여정으로 본다
const asJourney = (f) => {
  const segs = Array.isArray(f.segments) && f.segments.length ? f.segments : [f];
  const route = [segs[0].from]; segs.forEach((g) => { if (g.from && g.from !== route[route.length - 1]) route.push(g.from); route.push(g.to); });
  return { ...f, segments: segs, route: f.route || route.filter(Boolean), layovers: f.layovers || segs.slice(1).map((n, i) => ({ at: segs[i].to, minutes: mins(segs[i].arrive, n.depart), airportChange: !!(segs[i].to && n.from && segs[i].to !== n.from), to: n.from })) };
};
const md = (x) => (x ? `${Number(x.slice(5, 7))}/${Number(x.slice(8, 10))}` : "");
const money = (x) => (x.amount == null ? "" : `${Number(x.amount).toLocaleString()} ${esc(x.currency)}`);
const nights = (a, b) => (a && b ? Math.round((new Date(b) - new Date(a)) / 864e5) : 0);

// 같은 업체의 다른 부스(중복)를 한눈에 알아보게 하는 표시. 다른 부스에서 이미 방문했으면 건너뛰어도 된다고 알려 준다.
export function dupBadge(c, companies) {
  if (!c.dup) return { pill: "", line: "", skip: false };
  const byId = new Map(companies.map((x) => [x.id, x]));
  const others = c.dup.others.map((o) => ({ ...o, done: (byId.get(o.id)?.visits || []).length > 0 }));
  const skip = others.some((o) => o.done);
  const where = others.map((o) => `${o.booth || o.hall || "?"}${o.day ? ` (Day ${o.day})` : ""}${o.done ? " ✓" : ""}`).join(", ");
  return {
    skip,
    pill: ` <span class="pill dup-pill">중복 ${c.dup.i}/${c.dup.n}</span>`,
    line: `<div class="item-sub dup-line">${skip ? "다른 부스를 이미 방문했어요 · 바쁘면 건너뛰어도 돼요" : "같은 업체의 다른 부스"}: ${esc(where)}</div>`,
  };
}

export function openBookings(trip) {
  const { flights = [], hotels = [] } = trip.bookings || {};
  const map = (q) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
  const DIR = { outbound: "가는 편", return: "오는 편", other: "항공편" };
  const copyBtn = (v) => (v ? `<button class="btn btn-sm" data-copy="${esc(v)}" aria-label="예약번호 복사">복사</button>` : "");
  const segHtml = (j) => j.segments.map((g, i) => `
      <div class="stack" style="gap:2px;padding:6px 0;border-top:1px solid var(--line,#e5e7eb)">
        <div style="font-weight:800">${esc(g.mode === "ground" ? "지상 이동" : g.flightNo)} <span class="small muted" style="font-weight:400">${esc(g.airline || "")}${g.operatedBy ? " · 운항 " + esc(g.operatedBy) : ""}${g.aircraft ? " · " + esc(g.aircraft) : ""}</span></div>
        <div class="small"><b>${esc(g.from)}</b>${g.fromTerm ? " T" + esc(g.fromTerm) : ""} ${esc(when(g.depart))}</div>
        <div class="small">→ <b>${esc(g.to)}</b>${g.toTerm ? " T" + esc(g.toTerm) : ""} ${esc(g.arrive && g.depart && g.arrive.slice(0, 10) === g.depart.slice(0, 10) ? g.arrive.slice(11) : when(g.arrive))}</div>
        ${g.cabin || g.baggage ? `<div class="small muted">${g.cabin ? "좌석등급 " + esc(g.cabin) : ""}${g.cabin && g.baggage ? " · " : ""}${g.baggage ? "수하물 " + esc(g.baggage) : ""}</div>` : ""}
      </div>${j.layovers[i] ? `<div class="small" style="padding:4px 8px;background:var(--soft,#f3f4f6);border-radius:8px">↳ ${esc(j.layovers[i].at)} 경유 <b>${esc(span(j.layovers[i].minutes))}</b>${j.layovers[i].airportChange ? ` · 공항 변경 → ${esc(j.layovers[i].to)}` : ""}</div>` : ""}`).join("");
  const fl = flights.map(asJourney).sort((a, b) => String(a.segments[0].depart).localeCompare(String(b.segments[0].depart))).map((f) => `
    <div class="card stack" style="gap:4px">
      <div class="row" style="justify-content:space-between"><span class="pill pill-blue">${DIR[f.direction] || "항공편"}</span><span class="small muted">${f.segments.length > 1 ? `경유 ${f.segments.length - 1}회` : "직항"}</span></div>
      <div style="font-weight:800;font-size:18px">${esc(f.route.join(" → "))}</div>
      <div class="small muted">현지 시각 · 24시간제</div>
      ${segHtml(f)}
      <div class="row small" style="justify-content:space-between"><span>예약번호 <b>${esc(f.confirmation || "-")}</b></span>${copyBtn(f.confirmation)}</div>
      ${f.amount != null ? `<div class="small muted">${money(f)}</div>` : ""}
      ${f.note ? `<div class="small muted">${esc(f.note)}</div>` : ""}
    </div>`).join("");
  const ho = [...hotels].sort((a, b) => String(a.checkIn).localeCompare(String(b.checkIn))).map((x) => `
    <div class="card stack" style="gap:4px">
      <div class="row" style="justify-content:space-between"><span class="pill pill-blue">숙소</span><span class="small muted">${esc(md(x.checkIn))} ~ ${esc(md(x.checkOut))}${nights(x.checkIn, x.checkOut) ? ` · ${nights(x.checkIn, x.checkOut)}박` : ""}</span></div>
      <div style="font-weight:800;font-size:17px">${esc(x.name)}${x.stars ? " · " + x.stars + "성" : ""}</div>
      ${x.address ? `<a href="${map(x.name + " " + x.address)}" target="_blank" rel="noopener noreferrer" class="small">${esc(x.address)} · 지도 앱으로 열기</a>` : ""}
      <div class="small">체크인 ${esc(x.checkIn)} · 체크아웃 ${esc(x.checkOut)}</div>
      <div class="row small" style="justify-content:space-between"><span>예약번호 <b>${esc(x.confirmation || "-")}</b></span>${copyBtn(x.confirmation)}</div>
      ${x.amount != null || x.freeCancelUntil ? `<div class="small muted">${money(x)}${x.amount != null && x.freeCancelUntil ? " · " : ""}${x.freeCancelUntil ? "무료취소 ~" + esc(when(x.freeCancelUntil)) : ""}</div>` : ""}
      ${x.note ? `<div class="small muted">${esc(x.note)}</div>` : ""}
    </div>`).join("");
  const body = fl || ho ? `${fl ? `<div class="small muted" style="font-weight:800">항공</div>${fl}` : ""}${ho ? `<div class="small muted" style="font-weight:800;margin-top:6px">숙소</div>${ho}` : ""}`
    : `<div class="card small muted">아직 기록된 예약이 없어요. 노트북 Trip Desk 의 '항공·숙소' 탭에 예약을 기록하고 패키지를 다시 보내면 여기에 나와요.</div>`;
  const { el, close } = openSheet(`<div class="sheet-head"><h2 class="sheet-title">항공·숙소</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div><div class="stack">${body}</div>`);
  el.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); toast("예약번호를 복사했어요."); } catch { toast("복사하지 못했어요. 번호를 길게 눌러 복사해 주세요.", 3500); }
  }));
}

// ---------- 식사 장소·현지 교통 (Desk 에서 정리한 것, 읽기 전용) ----------
// 현재 위치에서 목적지까지 구글 지도 길찾기를 연다 (출발지를 비우면 지도 앱이 '내 위치'를 쓴다)
const dirUrl = (dest, mode) => `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(dest)}&travelmode=${mode}`;
export function openLocal(trip) {
  const { meals = [], routes = [], passes = [], foods = [], notes = "" } = trip.local || {};
  const groups = new Map();
  meals.forEach((m) => { const k = m.group || m.area || "기타"; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(m); });
  const mealHtml = [...groups].map(([g, ms]) => `<div class="small muted" style="font-weight:800;margin-top:6px">${esc(g)}</div>` + ms.map((m) => `
    <a class="card stack" style="gap:3px;text-decoration:none;color:inherit" target="_blank" rel="noopener noreferrer" href="${dirUrl(m.mapQuery || m.name, "walking")}">
      <div class="row" style="justify-content:space-between"><b>${m.fav ? "★ " : ""}${esc(m.name)}</b>${m.meal ? `<span class="pill pill-blue">${esc(m.meal)}</span>` : ""}</div>
      <div class="small muted">${esc([m.cuisine, m.price].filter(Boolean).join(" · "))}</div>
      ${m.rating || m.reviewSummary ? `<div class="small" style="${Number(m.rating) && Number(m.rating) < 4 ? "color:#b45309" : ""}">${m.rating ? `<b>★ ${esc(m.rating)}</b>${m.reviews ? ` (${esc(m.reviews)})` : ""}` : ""}${m.checkedAt ? ` <span class="muted">${esc(m.checkedAt)} 확인</span>` : ""}${m.reviewSummary ? `<div>${esc(m.reviewSummary)}</div>` : ""}${m.dishes ? `<div class="muted">대표 메뉴: ${esc(m.dishes)}</div>` : ""}</div>` : ""}
      ${m.where ? `<div class="small">📍 ${esc(m.where)}</div>` : ""}${m.hours ? `<div class="small">🕒 ${esc(m.hours)}</div>` : ""}
      ${m.why ? `<div class="small">${esc(m.why)}</div>` : ""}${m.tip ? `<div class="small muted">팁: ${esc(m.tip)}</div>` : ""}
      <div class="small" style="color:var(--blue,#2563eb);font-weight:700">🧭 내 위치에서 길찾기 (구글 지도)</div>
    </a>`).join("")).join("");
  const foodHtml = foods.map((f) => `
    <div class="card stack" style="gap:2px">
      <div><b>${esc(f.name)}</b>${f.local ? ` <span class="muted small">${esc(f.local)}</span>` : ""}${f.price ? ` <span class="pill">${esc(f.price)}</span>` : ""}</div>
      ${f.desc ? `<div class="small">${esc(f.desc)}</div>` : ""}${f.order ? `<div class="small">🍴 ${esc(f.order)}</div>` : ""}${f.where ? `<div class="small muted">📍 ${esc(f.where)}</div>` : ""}
    </div>`).join("");
  const routeHtml = routes.map((r) => `
    <div class="card stack" style="gap:3px">
      <div class="row" style="justify-content:space-between"><b>${r.fav ? "★ " : ""}${esc(r.label || `${r.from} → ${r.to}`)}</b></div>
      <div class="small">${esc([r.mode, r.line].filter(Boolean).join(" · "))}</div>
      ${r.boardStation || r.alightStation ? `<div class="small">🚉 <b>${esc(r.boardStation || "?")}</b> 승차 → <b>${esc(r.alightStation || "?")}</b> 하차</div>` : ""}
      <div class="small muted">${esc([r.durationMin ? `약 ${r.durationMin}분` : "", r.frequency, r.firstLast].filter(Boolean).join(" · "))}</div>
      ${r.fare || r.ticket ? `<div class="small">💶 ${esc([r.fare, r.ticket].filter(Boolean).join(" · "))}</div>` : ""}
      ${r.whereToBuy ? `<div class="small muted">표 구입: ${esc(r.whereToBuy)}</div>` : ""}${r.taxi ? `<div class="small muted">택시: ${esc(r.taxi)}</div>` : ""}
      ${(r.steps || []).length ? `<ol class="small" style="margin:2px 0;padding-left:18px">${r.steps.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>` : ""}
      ${r.tips ? `<div class="small muted">팁: ${esc(r.tips)}</div>` : ""}
      <a class="small" target="_blank" rel="noopener noreferrer" href="${dirUrl(r.to || r.alightStation || "", "transit")}">🧭 내 위치에서 대중교통 길찾기 (구글 지도)</a>
    </div>`).join("");
  const passHtml = passes.map((p) => `<div class="card stack" style="gap:2px"><b>${esc(p.name)}${p.price ? " · " + esc(p.price) : ""}</b>${p.valid ? `<div class="small muted">유효: ${esc(p.valid)}</div>` : ""}${p.whereToBuy ? `<div class="small muted">구입: ${esc(p.whereToBuy)}</div>` : ""}${p.note ? `<div class="small muted">${esc(p.note)}</div>` : ""}</div>`).join("");
  const sec = (t, b) => (b ? `<div class="small muted" style="font-weight:800;margin-top:8px">${t}</div>${b}` : "");
  const body = mealHtml || foodHtml || routeHtml || passHtml ? `${sec("식사 장소 — 누르면 내 위치에서 길찾기", mealHtml)}${sec("현지 음식 가이드", foodHtml)}${sec("현지 교통", routeHtml)}${sec("표·패스", passHtml)}${notes ? `<div class="card small muted">${esc(notes)}</div>` : ""}`
    : `<div class="card small muted">아직 정리된 식사 장소·교통 정보가 없어요. 노트북 Trip Desk 의 '식사·이동' 탭에서 정리하고 패키지를 다시 보내면 여기에 나와요.</div>`;
  openSheet(`<div class="sheet-head"><h2 class="sheet-title">식사·이동</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div><div class="stack">${body}</div>`);
}

// 세션(세미나·컨퍼런스) 상세: 시간·장소·연사·주제, 홀이 있으면 맵에서 보기
export function openSession(x, trip, onChange) {
  if (!x) return;
  const when = `${x.date.slice(5).replace("-", "/")} ${x.start || "시간 미정"}${x.end ? "~" + x.end : ""}`;
  const { el, close } = openSheet(`<div class="sheet-head"><h2 class="sheet-title">세션</h2><button class="icon-btn" data-close aria-label="닫기" style="margin-right:-8px">${icons.close(22)}</button></div>
    <div class="stack">
      <div style="font-weight:800;font-size:18px">${esc(x.title)}</div>
      <div class="small"><b>${esc(when)}</b></div>
      <div class="small">${esc([x.place, x.hall && `홀 ${x.hall}`].filter(Boolean).join(" · ") || "장소 미정")}</div>
      ${x.speaker ? `<div class="small">연사 ${esc(x.speaker)}</div>` : ""}
      ${x.topic ? `<div class="small muted" style="line-height:1.6">${esc(x.topic)}</div>` : ""}
      <button class="btn btn-block ${x.going ? "" : "btn-primary"}" id="sessGo">${x.going ? "✓ 참석 예정 (누르면 취소)" : "참석할게요"}</button>
      ${x.hall ? `<button class="btn btn-block" id="sessMap">맵에서 홀 ${esc(x.hall)} 보기</button>` : ""}
    </div>`);
  el.querySelector("#sessGo").onclick = async () => {
    x.going = !x.going;
    trip.sessions = trip.sessions.map((o) => (o.id === x.id ? { ...o, going: x.going } : o));
    await db.put("trips", trip);
    close(); onChange?.();
  };
  const b = el.querySelector("#sessMap");
  if (b) b.onclick = () => { try { sessionStorage.setItem("tf.focusHall", x.hall); } catch { /* 무시 */ } close(); location.hash = "#/map"; };
}
