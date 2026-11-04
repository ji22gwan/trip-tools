import { h, api, toast, guard, modal, confirmBox, fmtDate } from "./core.js";
import { prepView } from "./prep.js";
import { importView, dailyView, finalView } from "./days.js";

const side = document.getElementById("side");
const main = document.getElementById("main");
let trips = [];
let timer = null;

const KEY = "tripdesk.current";
const getCur = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const setCur = (id) => { try { localStorage.setItem(KEY, id); } catch {} };

const app = {
  go(hash) { if (location.hash === hash) route(); else location.hash = hash; },
  poll(fn, ms) { clearTimeout(timer); timer = setTimeout(fn, ms); },
  async refreshSide() { try { trips = (await api("GET", "/trips")).trips; } catch {} drawSide(); },
};

function parse() {
  const p = location.hash.replace(/^#\/?/, "").split("/");
  return { page: p[0] || "trips", tid: p[1] || null, n: Number(p[2]) || null };
}

function drawSide() {
  const { page, tid } = parse();
  const id = tid || getCur();
  const trip = trips.find((t) => t.id === id);
  const days = trip?.dayStats || [];
  const got = days.filter((d) => d.imported);
  const lastDay = got.length ? got[got.length - 1].day : 1;
  const item = (label, hash, key, badge, needTrip) =>
    h("button", { class: "nav" + (page === key ? " on" : ""), disabled: needTrip && !trip, onclick: () => app.go(hash) }, label, badge ? h("small", {}, badge) : null);
  side.replaceChildren(
    h("div", { class: "brand" }, h("b", {}, "Trip Desk"), h("span", {}, "출장 데이터 정리 도구")),
    item("출장 목록", "#/trips", "trips"),
    item("사전조사", trip ? `#/prep/${trip.id}` : "#/trips", "prep", trip ? `${trip.pickedCount}곳` : "", true),
    item("일간 import", trip ? `#/import/${trip.id}` : "#/trips", "import", trip ? `${got.length}/${days.length}` : "", true),
    item("일간 보고서", trip ? `#/daily/${trip.id}/${lastDay}` : "#/trips", "daily", "", true),
    item("최종 보고서", trip ? `#/final/${trip.id}` : "#/trips", "final", "", true),
    h("div", { class: "grow" }),
    trip ? h("div", { class: "cur" }, h("i", {}, "현재 출장"), h("b", {}, trip.name), h("i", {}, trip.venue || fmtDate(trip.days[0]))) : null);
}

async function route() {
  clearTimeout(timer);
  document.querySelectorAll(".modalbg").forEach((m) => m.remove());
  const { page, tid, n } = parse();
  if (tid) setCur(tid);
  if (!trips.length) await app.refreshSide();
  drawSide();
  window.scrollTo(0, 0);
  const view = { trips: () => tripsView(), prep: () => prepView(main, tid, app), import: () => importView(main, tid, app),
    daily: () => dailyView(main, tid, n || 1, app), final: () => finalView(main, tid, app) }[page];
  if (!view) return app.go("#/trips");
  try {
    await view();
  } catch (e) {
    main.replaceChildren(h("div", { class: "top" }, h("h1", {}, "열 수 없어요")), h("div", { class: "msg err" }, e.message), h("a", { class: "btn", href: "#/trips" }, "출장 목록으로"));
  }
  drawSide();
}

async function tripsView() {
  await app.refreshSide();
  const t = trips;
  const got = t.reduce((a, x) => a + x.dayStats.filter((d) => d.imported).length, 0);
  const rec = t.reduce((a, x) => a + x.dayStats.reduce((b, d) => b + (d.recordings || 0), 0), 0);
  const tr = t.reduce((a, x) => a + x.dayStats.reduce((b, d) => b + (d.transcribed || 0), 0), 0);
  const kpi = (l, v, note, acc) => h("div", { class: "kpi" + (acc ? " accent" : "") }, h("span", {}, l), h("b", {}, v), h("em", {}, note));
  const cards = t.map((x) => {
    const imported = x.dayStats.filter((d) => d.imported).length;
    const pct = (imported / x.days.length) * 100;
    return h("div", { class: "tripcard", role: "button", tabindex: "0", onclick: () => app.go(`#/prep/${x.id}`), onkeydown: (e) => e.key === "Enter" && app.go(`#/prep/${x.id}`) },
      h("div", {}, h("h3", {}, x.name), h("div", { class: "sub" }, `${x.venue || "장소 미정"} · ${x.days[0]} ~ ${x.days[x.days.length - 1]}`)),
      h("div", { class: "mini" }, h("span", { class: "pill" + (x.mapCount ? " ok" : " warn") }, x.mapCount ? `지도 ${x.mapCount}장` : "지도 없음"), h("span", { class: "pill" }, `선택 ${x.pickedCount}곳`),
        h("span", { class: "pill" + (imported ? " ok" : " gray") }, `일차 ${imported}/${x.days.length}`)),
      h("div", {}, h("div", { class: "row sub", style: "justify-content:space-between" }, h("span", {}, "일간 데이터 가져옴"), h("span", {}, `${imported}/${x.days.length}`)), h("div", { class: "bar" }, h("i", { style: `width:${pct}%` }))),
      h("div", { class: "row" },
        h("button", { class: "btn sm", onclick: (e) => { e.stopPropagation(); app.go(`#/prep/${x.id}`); } }, "사전조사"),
        h("button", { class: "btn sm", disabled: !imported, onclick: (e) => { e.stopPropagation(); app.go(`#/daily/${x.id}/${x.dayStats.find((d) => d.imported).day}`); } }, "보고서"),
        h("span", { class: "grow" }),
        h("button", { class: "btn sm ghost danger", onclick: (e) => { e.stopPropagation(); confirmBox("출장 삭제", `'${x.name}' 의 모든 데이터(업체 목록, 지도, 가져온 녹음·사진)가 이 컴퓨터에서 지워져요. 되돌릴 수 없어요.`, "삭제", () => guard(async () => { await api("DELETE", "/trips/" + x.id); trips = []; route(); }), true); } }, "삭제")));
  });
  main.replaceChildren(
    h("div", { class: "top" }, h("h1", {}, "출장 목록"), h("button", { class: "btn primary", onclick: newTrip }, "+ 새 출장")),
    h("div", { class: "kpis" }, kpi("출장", t.length, "만든 출장 수"), kpi("선택한 업체", t.reduce((a, x) => a + x.pickedCount, 0), "방문 계획 합계"),
      kpi("가져온 일차", got, "폰에서 내보낸 날"), kpi("전사 완료", `${tr}/${rec}`, "녹음 기준", true)),
    t.length ? h("div", { class: "tripgrid" }, ...cards)
      : h("div", { class: "panel" }, h("div", { class: "empty" }, h("b", {}, "첫 출장을 만들어 볼까요?"), h("div", {}, "전시회 이름과 날짜만 있으면 돼요. 알려진 전시회는 공식 사이트가 자동으로 채워져요."), h("button", { class: "btn primary", onclick: newTrip }, "+ 새 출장"))));
}

function newTrip() {
  modal("새 출장", (m, close) => {
    const f = { name: h("input", { placeholder: "예) SPS 2026" }), venue: h("input", { placeholder: "예) Nuremberg Messe, 독일" }),
      start: h("input", { type: "date" }), end: h("input", { type: "date" }), purpose: h("textarea", { placeholder: "예) 휴머노이드, 용접 로봇, 조선소 자동화 적용 후보 탐색" }) };
    f.start.addEventListener("change", () => { if (!f.end.value) f.end.value = f.start.value; });
    const fld = (l, e) => h("div", { class: "field" }, h("label", {}, l), e);
    m.append(fld("전시회 이름", f.name), fld("장소", f.venue), h("div", { class: "row" }, h("div", { class: "grow" }, fld("시작일", f.start)), h("div", { class: "grow" }, fld("종료일", f.end))), fld("목적", f.purpose),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: close }, "취소"), h("button", { class: "btn primary", onclick: () => guard(async () => {
        const r = await api("POST", "/trips", { name: f.name.value, venue: f.venue.value, start: f.start.value, end: f.end.value || f.start.value, purpose: f.purpose.value });
        close(); trips = []; app.go(`#/prep/${r.trip.id}`);
      }) }, "만들기")));
    f.name.focus();
  });
}

window.addEventListener("hashchange", route);
route();
