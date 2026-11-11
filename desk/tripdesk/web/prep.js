import { pinsPanel, renderMapForPhone } from "./pins.js";
import { travelTab } from "./travel.js";
import { localTab } from "./local.js";
import { questionPicker } from "./questions.js";
import { sessionsTab } from "./sessions.js";
import { h, api, toast, spinner, guard, modal, confirmBox, promptModal, download, copyText } from "./core.js";

const P = { tab: "cands", cat: "전체", q: "", v: null, tid: null, found: null };
const flagKey = (tid) => "tripdesk.pkg." + tid;
const getFlag = (tid) => { try { return localStorage.getItem(flagKey(tid)) === "1"; } catch { return false; } };

export async function prepView(root, tid, app) {
  if (P.tid !== tid) Object.assign(P, { tid, tab: "cands", cat: "전체", q: "", found: null });
  P.app = app;
  P.root = root;
  P.v = await api("GET", "/trips/" + tid);
  draw();
}

const redraw = () => { const y = window.scrollY; draw(); window.scrollTo(0, y); };

async function saveCompanies(list) {
  P.v = await api("PUT", `/trips/${P.tid}/companies`, list);
  redraw();
  P.app.refreshSide();
}

// 부스가 여러 곳인 업체는 booths 에 담겨 있다. 체크(선택)는 업체 단위, 일정 배분은 부스 단위다.
const bs = (c) => (c.booths?.length ? c.booths : [{ hall: c.hall || "", booth: c.booth || "", day: c.day || null }]);
const bLabel = (b) => [b.hall, b.booth].filter(Boolean).join(" · ") || "위치 미확인";
const setBoothDay = (c, i, val) => P.v.companies.map((x) => (x.id === c.id ? { ...x, picked: val ? true : x.picked, booths: bs(x).map((b, j) => (j === i ? { ...b, day: val } : b)) } : x));

function stats() {
  const cs = P.v.companies;
  const picked = cs.filter((c) => c.picked !== false);
  const stops = picked.flatMap(bs);
  return { all: cs.length, picked: picked.length, stops: stops.length, dated: stops.filter((b) => b.day).length, maps: P.v.maps.length, unverified: picked.filter((c) => c.source === "ai" && !c.verified).length };
}

function draw() {
  const { trip } = P.v;
  const s = stats();
  const steps = [
    ["출장 정보", true, () => { if (WIDE.has(P.tab)) { P.tab = "cands"; redraw(); } P.root.querySelector(".leftcol input")?.focus(); }],
    ["후보 수집", s.all > 0, () => goTab("cands")],
    ["후보·일정", s.picked > 0 && s.dated === s.stops, () => goTab(s.picked ? "plan" : "cands")],
    ["패키지 확정", getFlag(P.tid), confirmPackage],
  ];
  const nowIdx = steps.findIndex((x) => !x[1]);
  const stepsEl = h("div", { class: "steps" });
  steps.forEach(([label, done, go], i) => {
    if (i) stepsEl.append(h("div", { class: "bar" }));
    stepsEl.append(h("button", { class: "s stepbtn " + (done ? "done" : i === nowIdx ? "now" : ""), title: label + "(으)로 이동", onclick: go }, h("div", { class: "dot" }, done ? "✓" : String(i + 1)), label));
  });
  P.root.replaceChildren(
    h("div", { class: "top" },
      h("div", { class: "toplead" }, h("h1", {}, "사전조사"),
        h("button", { class: "btn", onclick: openPlanReport }, "출장 계획서 (Markdown)"),
        h("button", { class: "btn primary", onclick: confirmPackage }, "패키지 확정 · 폰으로 보내기")),
      stepsEl),
    h("div", { class: "kpis" },
      kpi("후보 업체", s.all, "AI·CSV·직접 추가 합계"),
      kpi("선택한 업체", s.picked, s.unverified ? `참가 미확인 ${s.unverified}곳` : "폰으로 보낼 업체", true),
      kpi("일정 배정", `${s.dated}/${s.stops}`, s.stops > s.picked ? `부스 기준 · 업체 ${s.picked}곳` : trip.days.length + "일 일정"),
      kpi("전시장 지도", s.maps, s.maps ? "대표 1장을 폰에 보내요" : "아직 없어요")),
    // 일정 배분·항공·숙소·식사·이동은 내용이 넓어서 왼쪽 '출장 정보' 열 없이 패널을 전체 폭으로 쓴다 (후보 업체 등은 그대로)
    h("div", { class: "cols" }, ...(WIDE.has(P.tab) ? [] : [leftCol(s)]), panel(s)),
  );
}

const WIDE = new Set(["plan", "travel", "local"]);
const goTab = (k) => { P.tab = k; redraw(); P.root.querySelector(".panel")?.scrollIntoView({ behavior: "smooth", block: "start" }); };
const kpi = (label, val, note, accent) => h("div", { class: "kpi" + (accent ? " accent" : "") }, h("span", {}, label), h("b", {}, val), h("em", {}, note));

// ---------------- 왼쪽: 출장 정보 / 진행 ----------------
function leftCol(s) {
  const { trip } = P.v;
  const f = {
    name: h("input", { value: trip.name }), venue: h("input", { value: trip.venue }),
    purpose: h("textarea", { value: trip.purpose, placeholder: "예) 휴머노이드, 용접 로봇, 조선소 자동화 적용 후보 탐색" }),
  };
  const field = (label, el) => h("div", { class: "field" }, h("label", {}, label), el);
  const dates = h("input", { value: `${trip.days[0]} ~ ${trip.days[trip.days.length - 1]}`, disabled: true });
  const save = h("button", { class: "btn sm", onclick: () => guard(async () => {
    P.v = await api("PATCH", "/trips/" + P.tid, { name: f.name.value, venue: f.venue.value, purpose: f.purpose.value });
    toast("저장했어요.");
    redraw();
    P.app.refreshSide();
  }) }, "정보 저장");
  const checks = [
    ["공식 사이트·지도 확보", s.maps > 0, () => goTab("map")],
    ["후보 업체 수집", s.all > 0, () => goTab("cands")],
    ["후보 선별·일정 배분", s.picked > 0 && s.dated === s.stops, () => goTab(s.picked ? "plan" : "cands")],
    ["패키지 확정 · 폰으로 보내기", getFlag(P.tid), confirmPackage],
  ];
  const now = checks.findIndex((c) => !c[1]);
  return h("div", { class: "leftcol" },
    h("div", { class: "card" }, h("h3", {}, "출장 정보"),
      field("전시회 이름", f.name), field("장소", f.venue), field("날짜", dates), field("목적", f.purpose),
      h("div", { class: "row" }, save),
      h("button", { class: "btn primary", style: "height:46px;font-size:15px", onclick: openKeywordPrompt }, "AI 프롬프트 만들기")),
    h("div", { class: "card" }, h("h4", {}, "진행 상황"),
      ...checks.map(([t, done, go], i) => h("button", { class: "check chk-btn " + (done ? "done" : i === now ? "now" : ""), title: t + "(으)로 이동", onclick: go }, h("i", {}, done ? "✓" : ""), t)),
      h("div", { style: "height:1px;background:var(--line2)" }),
      h("div", { class: "row" },
        h("button", { class: "btn sm", onclick: () => { P.tab = "map"; redraw(); } }, "맵 PDF 직접 올리기"),
        h("button", { class: "btn sm", onclick: () => { P.tab = "map"; redraw(); } }, "URL 붙여넣기"))),
  );
}

// ---------------- 오른쪽: 탭 ----------------
function panel(s) {
  const tabs = [["cands", `후보 업체 ${s.all}`], ["plan", "일정 배분"], ["map", `전시장 맵 ${s.maps || ""}`.trim()], ["sessions", `세션·행사 ${(P.v.sessions || []).length || ""}`.trim()], ["travel", "항공·숙소"], ["local", "식사·이동"], ["gloss", "용어집"]];
  return h("div", { class: "panel" + (WIDE.has(P.tab) ? " wide" : "") },
    h("div", { class: "tabs", role: "tablist" }, ...tabs.map(([k, label]) => h("button", { class: P.tab === k ? "on" : "", role: "tab", onclick: () => { P.tab = k; redraw(); } }, label))),
    P.tab === "cands" ? candsTab(s) : P.tab === "plan" ? planTab(s) : P.tab === "map" ? mapTab() : P.tab === "sessions" ? sessionsTab(P, redraw) : P.tab === "travel" ? travelTab(P) : P.tab === "local" ? localTab(P) : glossTab(),
  );
}

function dayLabel(d) { return d ? "Day " + d : "미배정"; }

function dayPicker(c, i = 0) {
  const { days } = P.v.trip;
  const cur = bs(c)[i].day;
  const sel = h("select", { class: "dayb" + (cur ? " set" : ""), "aria-label": `${c.name} ${bs(c).length > 1 ? bLabel(bs(c)[i]) + " " : ""}방문일`, onchange: () => {
    const val = sel.value ? Number(sel.value) : null;
    guard(() => saveCompanies(setBoothDay(c, i, val)));
  } }, h("option", { value: "" }, "미배정"), ...days.map((d, k) => h("option", { value: k + 1 }, `Day ${k + 1}`)));
  sel.value = cur || "";
  return sel;
}

function candsTab(s) {
  const cs = P.v.companies;
  if (!cs.length) {
    return h("div", { class: "empty" }, h("b", {}, "아직 후보 업체가 없어요"),
      h("div", {}, "키워드를 적어 AI 챗봇용 프롬프트를 만들고, 받은 답을 붙여 넣으면 후보가 채워져요. CSV/Excel 업체 목록을 가져와도 돼요."),
      h("div", { class: "row", style: "justify-content:center" },
        h("button", { class: "btn primary", onclick: openKeywordPrompt }, "AI 프롬프트 만들기"),
        csvButton(), h("button", { class: "btn", onclick: () => openCompanyEditor(null) }, "+ 업체 직접 추가")));
  }
  const cats = new Map();
  cs.forEach((c) => cats.set(c.category || "기타", (cats.get(c.category || "기타") || 0) + 1));
  const coreN = cs.filter((c) => c.core).length;
  const chips = [["전체", cs.length], ...(coreN ? [["★ 핵심", coreN]] : []), ["선택됨", s.picked], ...[...cats.entries()].sort((a, b) => b[1] - a[1])];
  const q = P.q.trim().toLowerCase();
  const shown = cs.filter((c) => {
    if (P.cat === "선택됨" && c.picked === false) return false;
    if (P.cat === "★ 핵심") return !!c.core && (!q || (c.name + " " + c.category + " " + (c.reason || "")).toLowerCase().includes(q));
    if (P.cat !== "전체" && P.cat !== "선택됨" && (c.category || "기타") !== P.cat) return false;
    return !q || (c.name + " " + c.category + " " + (c.reason || "")).toLowerCase().includes(q);
  }).sort((a, b) => (b.core ? 1 : 0) - (a.core ? 1 : 0));   // 핵심 키워드 업체를 위로 (그 안에서는 원래 순서)
  const header = h("div", { class: "tr head" }, h("div"), h("div", {}, "업체"), h("div", {}, "카테고리"), h("div", {}, "홀 · 부스"), h("div", {}, "선별 이유"), h("div", {}, "방문일"), h("div"));
  const rows = shown.map((c) => {
    const on = c.picked !== false;
    const cb = h("button", { class: "cb" + (on ? " on" : ""), role: "checkbox", "aria-checked": String(on), "aria-label": c.name + " 선택", onclick: () => {
      guard(() => saveCompanies(P.v.companies.map((x) => (x.id === c.id ? { ...x, picked: !on } : x))));
    } }, on ? "✓" : "");
    const bl = bs(c), multi = bl.length > 1;
    const locEl = h("div", { class: bl.some((b) => b.hall || b.booth) ? "" : "sub" }, ...bl.map((b) => h("div", {}, b.hall || b.booth ? `${b.hall || "?"} · ${b.booth || "?"}` : "미확인")));
    const why = [c.reason || c.preNotes?.split("\n")[0] || ""];
    return h("div", { class: "tr" + (on ? "" : " off") + (c.core ? " core" : "") }, cb,
      h("div", { class: "nm" }, c.core ? h("span", { class: "tag core", title: "핵심 키워드: " + (c.keywords || []).join(", ") }, "★ 핵심") : null, c.name, multi ? h("span", { class: "tag dup" }, `부스 ${bl.length}곳`) : null,
        c.source === "ai" ? (c.verified ? h("span", { class: "tag green" }, "참가 확인") : h("span", { class: "tag" }, "AI 추정")) : c.source === "csv" ? null : h("span", { class: "tag" }, "내가 추가")),
      h("div", {}, c.category || "기타"), locEl,
      h("div", { class: "why" }, why[0], c.sourceUrl ? h("span", {}, " ", h("a", { href: c.sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "출처")) : null),
      h("div", { style: "display:flex;flex-direction:column;gap:4px" }, ...bl.map((_, i) => dayPicker(c, i))),
      h("button", { class: "btn sm ghost", "aria-label": c.name + " 편집", onclick: () => openCompanyEditor(c), style: "padding:0" }, "✎"));
  });
  const ids = new Set(shown.map((c) => c.id));
  const selN = shown.filter((c) => c.picked !== false).length;
  const setAll = (on) => guard(() => saveCompanies(P.v.companies.map((x) => (ids.has(x.id) ? { ...x, picked: on } : x))));
  const openDelete = () => modal("업체 삭제", (m, close) => {
    const off = shown.filter((c) => c.picked === false), on = shown.filter((c) => c.picked !== false);
    const del = (list, label) => confirmBox("업체 삭제", `${label} ${list.length}곳을 목록에서 지울까요? 되돌릴 수 없어요.`, "삭제", () => { close(); guard(() => saveCompanies(P.v.companies.filter((x) => !list.some((d) => d.id === x.id)))); }, true);
    m.append(h("div", { class: "msg" }, `지금 보이는 ${shown.length}곳(필터·검색 적용)이 대상이에요. 필터를 '전체'로 두면 모든 후보가 대상이에요.`),
      h("div", { class: "stack", style: "display:flex;flex-direction:column;gap:8px" },
        h("button", { class: "btn", disabled: !off.length, onclick: () => del(off, "선택하지 않은 후보") }, `선택 안 한 후보 ${off.length}곳 삭제 (정리)`),
        h("button", { class: "btn danger", disabled: !on.length, onclick: () => del(on, "선택한 업체") }, `선택한 업체 ${on.length}곳 삭제`)),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: close }, "닫기")));
  });
  const bulk = h("div", { class: "row", style: "padding:6px 2px;gap:8px" },
    h("button", { class: "btn sm", disabled: selN === shown.length, onclick: () => setAll(true) }, `전체 선택 (${shown.length}곳)`),
    h("button", { class: "btn sm", disabled: !selN, onclick: () => setAll(false) }, "전체 해제"),
    h("button", { class: "btn sm danger", onclick: openDelete }, "삭제…"),
    h("span", { class: "sub" }, `보이는 ${shown.length}곳 중 ${selN}곳 선택`));
  const perDay = P.v.trip.days.map((_, i) => cs.filter((c) => c.picked !== false).flatMap(bs).filter((b) => b.day === i + 1).length);
  return h("div", { style: "display:flex;flex-direction:column" },
    h("div", { class: "chips" }, ...chips.map(([name, n]) => h("button", { class: "chip" + (P.cat === name ? " on" : ""), onclick: () => { P.cat = name; redraw(); } }, `${name} ${n}`)),
      h("input", { type: "search", placeholder: "이름·이유 검색", value: P.q, style: "width:180px;height:34px;margin-left:auto", oninput: (e) => { P.q = e.target.value; const pos = e.target.selectionStart; redraw(); const el = P.root.querySelector('input[type=search]'); el.focus(); el.setSelectionRange(pos, pos); } })),
    bulk,
    h("div", { class: "table" }, header, ...(rows.length ? rows : [h("div", { class: "empty" }, "조건에 맞는 업체가 없어요.")])),
    h("div", { class: "foot" },
      h("div", {}, h("b", {}, `선택 ${s.picked}곳` + (s.stops > s.picked ? ` (방문 지점 ${s.stops}곳)` : "") + perDay.map((n, i) => (n ? ` · Day ${i + 1} ${n}곳` : "")).join("")),
        h("div", { class: "sub" }, s.stops - s.dated ? `일정 미배정 ${s.stops - s.dated}곳 · '일정 배분' 탭에서 한 번에 나눌 수 있어요` : "모든 선택 업체에 방문일이 있어요")),
      h("div", { class: "row" },
        h("button", { class: "btn", onclick: () => openCompanyEditor(null) }, "+ 업체 직접 추가"), csvButton())));
}

function csvButton() {
  const inp = h("input", { type: "file", accept: ".csv,.xlsx,.tsv,.txt", style: "display:none", onchange: () => {
    const f = inp.files[0];
    if (!f) return;
    guard(async () => {
      const r = await api("POST", `/trips/${P.tid}/companies/import?filename=${encodeURIComponent(f.name)}`, await f.arrayBuffer(), { raw: true });
      P.v = r;
      redraw();
      toast(`${r.import.added}곳 추가, ${r.import.updated}곳 갱신` + (r.import.warnings.length ? ` · 주의 ${r.import.warnings.length}건` : ""));
      r.import.warnings.slice(0, 3).forEach((w) => toast(w, true));
    });
    inp.value = "";
  } });
  return h("span", { class: "row", style: "gap:6px" }, inp,
    h("button", { class: "btn", onclick: () => inp.click() }, "CSV/Excel 가져오기"),
    h("a", { class: "sub", href: "/api/template.csv", style: "color:var(--blue)" }, "양식"));
}

// ---------------- 일정 배분 ----------------
function planTab(s) {
  const { days } = P.v.trip;
  const picked = P.v.companies.filter((c) => c.picked !== false);
  if (!picked.length) return h("div", { class: "empty" }, h("b", {}, "선택한 업체가 없어요"), h("div", {}, "'후보 업체' 탭에서 방문할 업체를 체크하세요."));
  // 부스 하나 = 카드 하나. 부스가 여러 곳인 업체는 카드가 여러 장이라 '선택한 업체 수'보다 카드가 더 많을 수 있다.
  const stops = picked.flatMap((c) => bs(c).map((b, i) => ({ c, b, i, n: bs(c).length })));
  const move = (x, to) => guard(() => saveCompanies(setBoothDay(x.c, x.i, to)));
  const card = (x) => {
    const d = x.b.day || 0;
    const others = bs(x.c).map((b, j) => ({ b, j })).filter((o) => o.j !== x.i);
    const mv = [];
    if (d > 0) mv.push(h("button", { onclick: () => move(x, d - 1 || null) }, d === 1 ? "← 미배정" : `← Day ${d - 1}`));
    if (d < days.length) mv.push(h("button", { onclick: () => move(x, d + 1) }, `Day ${d + 1} →`));
    return h("div", { class: "card2" + (x.n > 1 ? " dupc" : "") }, h("div", { class: "t" }, x.c.name),
      x.n > 1 ? h("div", { class: "dupnote" }, h("b", {}, `⚠ 중복 업체 ${x.i + 1}/${x.n}`), ` · 다른 부스: ${others.map((o) => `${o.b.booth || o.b.hall || "?"}${o.b.day ? ` (Day ${o.b.day})` : ""}`).join(", ")}`) : null,
      h("div", { class: "m" }, `${x.c.category || "기타"} · ${bLabel(x.b)}`),
      h("div", { class: "mv" }, ...mv));
  };
  const loads = days.map((_, i) => stops.filter((x) => x.b.day === i + 1).length);
  const peak = Math.max(1, ...loads);
  const col = (title, list, bar) => h("div", { class: "col" }, h("h4", {}, title, h("span", {}, list.length + "곳")),
    bar == null ? null : h("div", { class: "load", "aria-hidden": "true" }, h("i", { style: `width:${Math.round((bar / peak) * 100)}%` })), ...list.map(card));
  const unassigned = stops.filter((x) => !x.b.day);
  const help = `아직 일차가 없는 곳만 같은 홀끼리 묶어 날짜별로 고르게 나눠요. 한 날에 몰리면 2·3일차 쪽으로 가요(첫날은 둘러볼 시간). 이미 정한 일정은 그대로 둬요.${s.stops > s.picked ? ` 선택한 업체 ${s.picked}곳 중 부스가 여럿인 업체가 있어 카드(지점)는 ${s.stops}곳이에요.` : ""}`;
  return h("div", { style: "display:flex;flex-direction:column" },
    h("div", { class: "pad", style: "padding-bottom:0" }, h("div", { class: "row", style: "flex-wrap:wrap" },
      h("button", { class: "btn primary sm", onclick: autoAssign }, "홀 기준으로 자동 배분"),
      h("span", { class: "sub" }, "같은 홀끼리 묶어 날짜별로 고르게 나눠요. 몰리면 2·3일차로 보내요."),
      h("button", { class: "btn sm ghost", "aria-expanded": String(!!P.planHelp), onclick: () => { P.planHelp = !P.planHelp; redraw(); } }, P.planHelp ? "접기" : "자세히"),
      unassigned.length ? null : h("span", { class: "pill ok", style: "margin-left:auto" }, "✓ 미배정 0곳 — 모두 배정됨")),
      P.planHelp ? h("div", { class: "msg", style: "margin-top:8px" }, help) : null),
    // 미배정이 없으면 빈 열을 숨겨 일차 열을 넓게 쓴다
    h("div", { class: "board" }, ...(unassigned.length ? [col("미배정", unassigned)] : []), ...days.map((d, i) => col(`Day ${i + 1} · ${d.slice(5)}`, stops.filter((x) => x.b.day === i + 1), loads[i]))));
}

function autoAssign() {
  const n = P.v.trip.days.length;
  const all = P.v.companies.filter((c) => c.picked !== false).flatMap((c) => bs(c).map((b, i) => ({ c, b, i })));
  const todo = all.filter((x) => !x.b.day);
  if (!todo.length) return toast("나눌 업체가 없어요.");
  const load = P.v.trip.days.map((_, i) => all.filter((x) => x.b.day === i + 1).length);
  const total = load.reduce((a, b) => a + b, 0) + todo.length;
  const cap = Math.ceil(total / n);
  // 같은 홀끼리 묶어 두되(한 번에 둘러보기), 한 홀이 너무 크면 나눈다.
  const byHall = new Map();
  todo.forEach((x) => { const k = x.b.hall || "?"; byHall.set(k, [...(byHall.get(k) || []), x]); });
  const groups = [];
  for (const list of byHall.values()) {
    list.sort((a, b) => (a.b.booth || "").localeCompare(b.b.booth || "", undefined, { numeric: true }));
    for (let i = 0; i < list.length; i += cap) groups.push(list.slice(i, i + cap));
  }
  // 큰 묶음부터 가장 한가한 날에 넣는다. 같은 수면 뒤쪽 날을 고른다 → 한 날에 몰려도 그날은 2·3일차가 되고 첫날은 가벼워진다.
  const assign = new Map();
  groups.sort((a, b) => b.length - a.length).forEach((g) => {
    let d = 0;
    for (let k = 1; k < n; k++) if (load[k] <= load[d]) d = k;
    g.forEach((x) => assign.set(`${x.c.id}#${x.i}`, d + 1));
    load[d] += g.length;
  });
  guard(() => saveCompanies(P.v.companies.map((c) => ({ ...c, booths: bs(c).map((b, i) => (assign.has(`${c.id}#${i}`) ? { ...b, day: assign.get(`${c.id}#${i}`) } : b)) }))));
  toast(`${todo.length}곳을 나눴어요. 필요하면 카드의 이동 버튼으로 옮기세요.`);
}

// ---------------- 지도 ----------------
function mapTab() {
  const { trip, maps } = P.v;
  const site = h("input", { value: trip.siteUrl || "", placeholder: "https://sps.mesago.com/..." });
  const url = h("input", { placeholder: "지도 PDF/이미지 주소를 붙여 넣기" });
  const file = h("input", { type: "file", accept: ".pdf,.png,.jpg,.jpeg,.webp", style: "display:none", onchange: () => {
    const f = file.files[0];
    if (!f) return;
    guard(async () => { P.v = await api("POST", `/trips/${P.tid}/maps/upload?filename=${encodeURIComponent(f.name)}`, await f.arrayBuffer(), { raw: true }); redraw(); toast("지도를 추가했어요."); P.app.refreshSide(); });
    file.value = "";
  } });
  const found = P.found;
  const pinHost = h("div");
  if (maps.length) pinsPanel(P, redraw).then((c) => { if (c && pinHost.isConnected) pinHost.append(c); });
  return h("div", { class: "pad" },
    maps.length ? h("div", { class: "maps", style: "padding:0" }, ...maps.map((m) => h("div", { class: "mapr" },
      h("div", { class: "ic" }, m.name.split(".").pop().toUpperCase()),
      h("div", { class: "grow" }, h("div", { style: "font-weight:800;overflow-wrap:anywhere" }, m.name), h("div", { class: "sub" }, `${(m.size / 1024).toFixed(0)}KB`)),
      m.primary ? h("span", { class: "pill ok" }, "폰에 보낼 대표") : h("button", { class: "btn sm", onclick: () => guard(async () => { P.v = await api("PUT", `/trips/${P.tid}/primary-map`, { name: m.name }); redraw(); }) }, "대표로 지정"),
      h("a", { class: "btn sm", href: `/api/trips/${P.tid}/maps/${encodeURIComponent(m.name)}`, target: "_blank", rel: "noopener" }, "열어 보기"),
      h("button", { class: "btn sm danger", onclick: () => confirmBox("지도 삭제", `'${m.name}' 을(를) 삭제할까요?`, "삭제", () => guard(async () => { P.v = await api("DELETE", `/trips/${P.tid}/maps/${encodeURIComponent(m.name)}`); redraw(); }), true) }, "삭제"))))
      : h("div", { class: "msg warn" }, "아직 지도가 없어요. 아래에서 공식 사이트로 자동 찾기를 해 보세요."),
    h("div", { class: "msg" }, "여러 장을 받아도 폰에는 '대표' 1장만 가요. 대표는 언제든 바꿀 수 있어요."),
    h("div", { class: "field" }, h("label", {}, "공식 사이트 주소"), h("div", { class: "row" }, h("div", { class: "grow" }, site),
      h("button", { class: "btn primary", onclick: (e) => { e.target.disabled = true; guard(async () => {
        const r = await api("POST", `/trips/${P.tid}/maps/find`, { siteUrl: site.value.trim() });
        P.v = r.view; P.found = r;
        if (r.downloaded.length) toast(`지도 ${r.downloaded.length}장을 받았어요.`);
        r.messages.forEach((m) => toast(m, true));
        redraw();
      }).finally(() => { e.target.disabled = false; }); } }, "지도 자동 찾기"))),
    found && found.candidates?.length ? h("div", { class: "card", style: "padding:12px" }, h("h4", {}, "찾은 후보 (눈으로 확인하고 받으세요)"),
      ...found.candidates.map((c) => h("div", { class: "row" }, h("div", { class: "grow", style: "overflow-wrap:anywhere;font-size:13px" }, h("b", {}, c.text || c.url.split("/").pop()), h("div", { class: "sub" }, c.url)),
        h("button", { class: "btn sm", onclick: () => guard(async () => { const r = await api("POST", `/trips/${P.tid}/maps/download`, { url: c.url }); P.v = r.view; redraw(); toast("받았어요."); }) }, "받기")))) : null,
    h("div", { class: "field" }, h("label", {}, "주소로 직접 받기"), h("div", { class: "row" }, h("div", { class: "grow" }, url),
      h("button", { class: "btn", onclick: () => guard(async () => { const r = await api("POST", `/trips/${P.tid}/maps/download`, { url: url.value.trim() }); P.v = r.view; redraw(); toast("받았어요."); }) }, "받기"))),
    h("div", { class: "row" }, file, h("button", { class: "btn", onclick: () => file.click() }, "내 컴퓨터의 지도 파일 올리기"), h("span", { class: "sub" }, "PDF·PNG·JPG")),
    pinHost);
}

// ---------------- 용어집 ----------------
function glossTab() {
  const ta = h("textarea", { style: "min-height:260px", placeholder: "한 줄에 하나씩\nEtherCAT\npayload\n협동로봇" }, P.v.glossary.join("\n"));
  return h("div", { class: "pad" },
    h("div", { class: "msg" }, "여기 적은 용어는 ① 폰의 번역 힌트, ② 녹음 전사·AI 교정에서 '이렇게 적어 달라'는 기준으로 쓰여요. 회사명, 제품명, 약어를 넣어 두세요."),
    ta, h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => guard(async () => { P.v = await api("PUT", `/trips/${P.tid}/glossary`, ta.value.split("\n")); redraw(); toast("저장했어요."); }) }, "저장"),
      h("span", { class: "sub" }, `${P.v.glossary.length}개`)));
}

// ---------------- 출장 계획서 (Markdown → PDF 1~2쪽) ----------------
function openPlanReport() {
  guard(async () => {
    const V = await api("GET", `/trips/${P.tid}/plan`);
    modal("출장 계획서", (m, close) => {
      const goals = h("textarea", { style: "min-height:90px", placeholder: "한 줄에 하나" }, (V.goals.length ? V.goals : V.defaults.goals).join("\n"));
      const exp = h("textarea", { style: "min-height:90px", placeholder: "한 줄에 하나" }, (V.expected.length ? V.expected : V.defaults.expected).join("\n"));
      const lines = (t) => t.value.split("\n").map((x) => x.trim()).filter(Boolean);
      const save = () => api("PUT", `/trips/${P.tid}/plan`, { goals: lines(goals), expected: lines(exp) });
      m.append(h("div", { class: "msg" }, "출장 정보(행사·장소·기간·항공·숙소)와 방문 후보 업체(선별 사유 포함)는 자동으로 채워져요. 목표와 예상 결과만 확인·수정하세요. 처음 보이는 문장은 출장 목적과 선택한 업체로 만든 초안이에요."),
        h("div", { class: "field" }, h("label", {}, "출장 목표 (한 줄에 하나)"), goals), h("div", { class: "field" }, h("label", {}, "예상 결과 (한 줄에 하나)"), exp),
        h("div", { class: "sub" }, "내려받은 .md 를 PDF 로 바꾸려면: docs/manual/md2pdf.sh 파일.md (1~2쪽 A4 서식). 또는 VS Code 의 Markdown PDF 확장, 브라우저 인쇄도 돼요."),
        h("div", { class: "row", style: "justify-content:flex-end" },
          h("button", { class: "btn", onclick: () => guard(async () => { await save(); toast("저장했어요."); }) }, "저장"),
          h("button", { class: "btn primary", onclick: () => guard(async () => { await save(); download(`/trips/${P.tid}/plan.md`); }) }, "저장하고 Markdown 내려받기")));
    });
  });
}

// ---------------- 서버 보관함 관리(올려 둔 패키지 지우기) ----------------
function openCloudPackages() {
  modal("서버 보관함", (m, close) => {
    const list = h("div", { style: "display:flex;flex-direction:column;gap:8px;min-height:60px" });
    const wrap = h("div", { class: "busybox" }, list);
    const fmt = (t) => (t ? new Date(t).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "");
    // 작업 중에는 목록을 흐리게 하고 가운데에 돌아가는 원을 띄운다
    const busy = (label) => {
      wrap.classList.add("on"); wrap.append(h("div", { class: "busyov" }, spinner(label)));
      return () => { wrap.classList.remove("on"); wrap.querySelector(".busyov")?.remove(); };
    };
    const draw = (items) => list.replaceChildren(...(items.length ? items.map((p) => h("div", { class: "row" },
      h("div", { class: "grow" }, h("b", {}, p.name || p.localName || p.id), h("div", { class: "sub" }, `${fmt(p.at)} 업로드 · ${p.size ? (p.size / 1024).toFixed(0) + "KB" : ""}`)),
      h("button", { class: "btn sm danger", onclick: () => confirmBox("서버에서 삭제", `'${p.name || p.id}' 패키지를 서버 보관함에서 지울까요? 이미 폰에 불러온 출장은 그대로 남아 있어요.`, "삭제", () => remove(p), true) }, "삭제")))
      : [h("div", { class: "sub" }, "서버에 올라간 패키지가 없어요.")]));
    const load = async (label) => {
      const done = busy(label);
      try { draw((await api("GET", "/cloud/packages")).packages); }
      catch (e) { list.replaceChildren(h("div", { class: "msg err" }, e.message), h("button", { class: "btn sm", style: "align-self:flex-start", onclick: () => load("다시 불러오는 중…") }, "다시 시도")); }
      finally { done(); }
    };
    const remove = async (p) => {
      const done = busy("서버에서 지우는 중…");
      try { await api("DELETE", `/cloud/packages/${encodeURIComponent(p.id)}`); }
      catch (e) { done(); toast(e.message || String(e), true); return; }
      done();
      toast("서버에서 지웠어요.");
      await load("목록 새로고침 중…");   // 삭제가 끝나면 서버 목록을 다시 받아 자동으로 갱신
    };
    m.append(h("div", { class: "msg" }, "'폰으로 보내기 (서버)'로 올린 패키지 목록이에요. 올린 뒤 90일이 지나면 서버가 알아서 지우고, 여기서 바로 지울 수도 있어요. 이 컴퓨터의 출장 데이터와 폰에 이미 불러온 출장은 지워지지 않아요."),
      wrap,
      h("div", { class: "row", style: "justify-content:space-between" },
        h("button", { class: "btn", onclick: () => load("새로고침 중…") }, "새로고침"), h("button", { class: "btn", onclick: close }, "닫기")));
    load("불러오는 중…");
  });
}

// ---------------- 업체 편집/추가 ----------------
function openCompanyEditor(c) {
  modal(c ? "업체 편집" : "업체 직접 추가", (m, close) => {
    const f = {
      name: h("input", { value: c?.name || "" }), category: h("input", { value: c?.category || "", placeholder: "예) 협동로봇" }),
      preNotes: h("textarea", { value: c?.preNotes || "", placeholder: "사전 메모 (폰에서 업체 화면에 보여요)" }),
    };
    const qp = questionPicker(c?.questions || []);
    const fld = (l, el) => h("div", { class: "field" }, h("label", {}, l), el);
    // 부스가 여러 곳이면 줄을 늘린다. 업체(체크박스)는 1개로 세고, 일정 배분만 부스별로 나뉜다.
    const rows = [];
    const boothBox = h("div", { style: "display:flex;flex-direction:column;gap:6px" });
    const addRow = (b) => {
      const r = { b, hall: h("input", { value: b.hall || "", placeholder: "홀 (예: 5)", "aria-label": "홀" }), booth: h("input", { value: b.booth || "", placeholder: "부스 (예: 5-210)", "aria-label": "부스" }) };
      r.el = h("div", { class: "row", style: "gap:6px" }, h("div", { style: "width:110px" }, r.hall), h("div", { class: "grow" }, r.booth),
        h("button", { class: "btn sm ghost", "aria-label": "부스 줄 삭제", onclick: () => { if (rows.length < 2) { r.hall.value = ""; r.booth.value = ""; return; } rows.splice(rows.indexOf(r), 1); r.el.remove(); } }, "×"));
      rows.push(r); boothBox.append(r.el);
    };
    (c ? bs(c) : [{}]).forEach(addRow);
    m.append(fld("업체명", f.name), fld("카테고리", f.category), h("div", { class: "field" }, h("label", {}, "홀 · 부스 (여러 곳이면 + 로 추가)"), boothBox,
      h("button", { class: "btn sm", style: "align-self:flex-start;margin-top:4px", onclick: () => addRow({}) }, "+ 부스 추가")),
      fld("사전 메모", f.preNotes), fld("확인할 질문 (폰에서 영어·현지어로 번역해 보여줘요)", qp.el));
    if (c?.reason) m.append(h("div", { class: "msg" }, "AI가 적은 이유: " + c.reason));
    m.append(h("div", { class: "row", style: "justify-content:space-between" },
      c ? h("button", { class: "btn danger", onclick: () => confirmBox("업체 삭제", `'${c.name}' 을(를) 목록에서 지울까요?`, "삭제", () => guard(() => saveCompanies(P.v.companies.filter((x) => x.id !== c.id))), true) }, "삭제") : h("span"),
      h("button", { class: "btn primary", onclick: () => {
        if (!f.name.value.trim()) return toast("업체명을 입력해 주세요.", true);
        const data = { name: f.name.value.trim(), category: f.category.value.trim() || "기타", booths: rows.map((r) => ({ ...r.b, hall: r.hall.value.trim(), booth: r.booth.value.trim() })).filter((b) => b.hall || b.booth), preNotes: f.preNotes.value, questions: qp.get() };
        const list = c ? P.v.companies.map((x) => (x.id === c.id ? { ...x, ...data } : x))
          : [...P.v.companies, { id: "c-" + Math.random().toString(16).slice(2, 10), picked: true, source: "manual", ...data }];
        close();
        guard(() => saveCompanies(list));
      } }, "저장")));
  });
}

// ---------------- AI 프롬프트(키워드) ----------------
function openKeywordPrompt() {
  // 저장된 키워드를 칩으로 보여 주고, 칩의 ×로 삭제·입력칸으로 추가한다. 바뀔 때마다 출장에 저장돼 다음에도 남는다.
  let kws = [...(P.v.trip.keywords || [])];
  let core = [...(P.v.trip.coreKeywords || [])];   // ★ 표시한 핵심 키워드 — 여기에 맞는 업체는 중요도 높음
  const chips = h("div", { class: "row", style: "flex-wrap:wrap;gap:6px;margin-bottom:6px" });
  const kw = h("input", { placeholder: kws.length ? "키워드 추가 (쉼표나 Enter 로 확정)" : "예) 휴머노이드, 용접 로봇, 비전 센서 (쉼표나 Enter 로 확정)", value: "" });
  const count = h("select", {}, ...[10, 20, 30, 40, 50, 100].map((n) => h("option", { value: n }, `최대 ${n}곳`)));
  count.value = String(P.v.trip.keywordCount || 20);
  const persist = () => api("PUT", `/trips/${P.tid}/keywords`, { keywords: kws, core, count: Number(count.value) }).then((r) => { P.v = r; redraw(); }).catch(() => {});
  const drawChips = () => chips.replaceChildren(...kws.map((k) => {
    const on = core.includes(k);
    return h("span", { class: "pill" + (on ? " corepill" : ""), style: "display:inline-flex;gap:6px;align-items:center" },
      h("button", { class: "btn sm ghost starbtn" + (on ? " on" : ""), "aria-pressed": String(on), "aria-label": k + (on ? " 핵심 해제" : " 핵심 키워드로 지정"), title: on ? "핵심 키워드 (누르면 해제)" : "핵심 키워드로 지정", style: "padding:0 4px;min-height:0", onclick: () => { core = on ? core.filter((x) => x !== k) : [...core, k]; drawChips(); persist(); } }, on ? "★" : "☆"),
      k,
      h("button", { class: "btn sm ghost", "aria-label": k + " 삭제", style: "padding:0 4px;min-height:0", onclick: () => { kws = kws.filter((x) => x !== k); core = core.filter((x) => x !== k); drawChips(); persist(); } }, "×"));
  }));
  const commit = () => {
    const add = kw.value.split(/[,\n;/、]+/).map((x) => x.trim()).filter(Boolean);
    if (!add.length) return;
    for (const a of add) if (!kws.includes(a) && kws.length < 12) kws.push(a);
    kw.value = ""; drawChips(); persist();
  };
  kw.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } });
  kw.addEventListener("input", () => { if (/[,;、]$/.test(kw.value)) commit(); });
  count.addEventListener("change", persist);
  drawChips();
  let last = "";
  promptModal({
    title: "키워드로 참가업체 찾기 (AI 챗봇용)",
    intro: "Desk 가 AI를 직접 부르지는 않아요. 키워드를 적으면 AI 챗봇에 붙여 넣을 프롬프트를 만들어 주고, AI 의 답을 붙여 넣으면 후보 목록에 쌓여요. 이미 목록에 있는 업체는 프롬프트에서 제외돼요.",
    auto: false,
    extraTop: (ctl) => h("div", { class: "row" },
      h("div", { class: "grow field" }, h("label", {}, "찾고 싶은 키워드 (☆ 를 눌러 핵심 키워드로 · × 로 삭제)"), chips, kw),
      h("div", { class: "field", style: "width:130px" }, h("label", {}, "업체 수"), count),
      h("button", { class: "btn primary", style: "align-self:flex-end", onclick: () => { commit(); last = kws.join(", "); ctl.load(); } }, "프롬프트 만들기")),
    getPrompts: async () => {
      const r = await api("POST", `/trips/${P.tid}/prompt/exhibitors`, { keywords: kws.join(", "), core, count: Number(count.value) });
      return [r.prompt];
    },
    onPaste: async (text) => {
      const r = await api("POST", `/trips/${P.tid}/paste/exhibitors`, { text, keywords: last || kws.join(", ") });
      P.v = r;
      P.tab = "cands";
      P.cat = "전체";
      redraw();
      P.app.refreshSide();
      const p = r.pasted;
      toast(`후보 ${p.added}곳을 추가했어요` + (p.existing ? ` (이미 있던 ${p.existing}곳은 제외)` : "") + (p.unverified ? ` · 참가 미확인 ${p.unverified}곳` : ""));
      if (p.notes) toast("AI 메모: " + p.notes);
    },
  });
}

// ---------------- 패키지 ----------------
function confirmPackage() {
  const s = stats();
  const warns = P.v.warnings;
  modal("패키지 확정", (m, close) => {
    m.append(h("div", { class: "msg" }, `선택한 ${s.picked}곳, 대표 지도 ${s.maps ? "1장" : "없음"}, 용어 ${P.v.glossary.length}개가 들어가요.`));
    const shownWarns = warns.filter((w) => !w.includes("폰용 이미지로 아직")); // 이 창에서 자동으로 바꾸므로 따로 알리지 않는다
    if (shownWarns.length) m.append(h("div", { class: "msg warn" }, h("b", {}, "확인해 주세요"), h("ul", { style: "margin:6px 0 0;padding-left:18px" }, ...shownWarns.map((w) => h("li", {}, w)))));
    const status = h("div", { class: "sub" }, "서버 연결 확인 중…");
    // 지도가 PDF 면 폰용 이미지로 한 번만 바꿔 둔다(폰 불러오기가 빨라지고 용량도 줄어요). 끝나기 전에는 보내기 버튼을 막는다.
    let mapReady = false, cloudReady = false;
    const mapStatus = h("div", { class: "sub" }, "지도 확인 중…");
    const refreshBtns = () => { send.disabled = !(mapReady && cloudReady); zipBtn.disabled = !mapReady; };
    const mark = () => { try { localStorage.setItem(flagKey(P.tid), "1"); } catch {} setTimeout(redraw, 200); };
    const zipBtn = h("button", { class: "btn", disabled: true, onclick: () => { download(`/trips/${P.tid}/package`); mark(); close(); } }, "ZIP 내려받기");
    const send = h("button", { class: "btn primary", disabled: true, onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      const t0 = Date.now(), tick = setInterval(() => { status.textContent = `서버에 올리는 중… ${Math.round((Date.now() - t0) / 1000)}초 (최대 약 2분 30초, 넘으면 자동으로 멈추고 이유를 알려 줘요)`; }, 500);
      const r = await guard(() => api("POST", `/trips/${P.tid}/package/upload`, {})).finally(() => clearInterval(tick));
      if (r) { toast(`서버에 올렸어요 (${(r.size / 1024).toFixed(0)}KB${r.uploadSec ? `, ${r.uploadSec}초` : ""}). 폰에서 '서버에서 불러오기'를 누르세요.`, 5000); mark(); close(); } else { btn.disabled = false; status.textContent = "올리지 못했어요. 위 안내를 확인해 주세요."; }
    } }, "폰으로 보내기 (서버)");
    api("GET", "/cloud").then((c) => { cloudReady = !!c.ready; refreshBtns(); status.textContent = c.ready ? "서버 보관함 사용 가능" : (c.hasToken ? "서버 보관함이 없어요. install-worker 를 다시 실행하면 만들어져요." : "서버 설치 기록을 찾지 못했어요. ZIP 으로 옮길 수 있어요."); }).catch(() => { status.textContent = "서버 상태를 확인하지 못했어요."; });
    m.append(h("div", { class: "msg" }, h("b", {}, "폰으로 보내는 방법"), h("ol", { style: "margin:6px 0 0;padding-left:18px;line-height:1.7" },
      h("li", {}, "아래 '폰으로 보내기'를 누르면 서버에 올라가요."),
      h("li", {}, "폰에서 Trip Field → 설정 → '새 출장' → '서버에서 불러오기'를 누르세요."),
      h("li", {}, "인터넷이 안 될 땐 ZIP 으로 내려받아 AirDrop·메일·USB 로 옮기세요."))), status);
    m.append(h("div", { class: "row", style: "justify-content:flex-end;flex-wrap:wrap" }, h("button", { class: "btn", onclick: close }, "취소"),
      h("button", { class: "btn", onclick: openCloudPackages }, "서버 보관함 관리"), zipBtn, send));
    m.append(mapStatus);
    renderMapForPhone(P.tid, (p, n) => { mapStatus.textContent = `지도를 폰용 이미지로 바꾸는 중… ${p}/${n}쪽 (처음 한 번만)`; })
      .then((did) => { mapStatus.textContent = did ? "지도를 폰용 이미지로 바꿨어요." : "지도 준비됨"; mapReady = true; refreshBtns(); })
      .catch((e) => { mapStatus.textContent = "지도를 바꾸지 못했어요(" + (e.message || e) + "). 그대로 보내면 폰이 대신 변환하느라 오래 걸려요."; mapReady = true; refreshBtns(); });
  });
}
