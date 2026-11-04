import { h, api, toast, guard, modal, confirmBox, promptModal, download, copyText } from "./core.js";

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

function stats() {
  const cs = P.v.companies;
  const picked = cs.filter((c) => c.picked !== false);
  return { all: cs.length, picked: picked.length, dated: picked.filter((c) => c.day).length, maps: P.v.maps.length, unverified: picked.filter((c) => c.source === "ai" && !c.verified).length };
}

function draw() {
  const { trip } = P.v;
  const s = stats();
  const steps = [
    ["출장 정보", true],
    ["후보 수집", s.all > 0],
    ["후보·일정", s.picked > 0 && s.dated === s.picked],
    ["패키지 확정", getFlag(P.tid)],
  ];
  const nowIdx = steps.findIndex((x) => !x[1]);
  const stepsEl = h("div", { class: "steps" });
  steps.forEach(([label, done], i) => {
    if (i) stepsEl.append(h("div", { class: "bar" }));
    stepsEl.append(h("div", { class: "s " + (done ? "done" : i === nowIdx ? "now" : "") }, h("div", { class: "dot" }, done ? "✓" : String(i + 1)), label));
  });
  P.root.replaceChildren(
    h("div", { class: "top" }, h("h1", {}, "사전조사"), stepsEl),
    h("div", { class: "kpis" },
      kpi("후보 업체", s.all, "AI·CSV·직접 추가 합계"),
      kpi("선택한 업체", s.picked, s.unverified ? `참가 미확인 ${s.unverified}곳` : "폰으로 보낼 업체", true),
      kpi("일정 배정", `${s.dated}/${s.picked}`, trip.days.length + "일 일정"),
      kpi("전시장 지도", s.maps, s.maps ? "대표 1장을 폰에 보내요" : "아직 없어요")),
    h("div", { class: "cols" }, leftCol(s), panel(s)),
  );
}

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
    ["공식 사이트·지도 확보", s.maps > 0],
    ["후보 업체 수집", s.all > 0],
    ["후보 선별·일정 배분", s.picked > 0 && s.dated === s.picked],
    ["패키지 확정 · 폰으로 보내기", getFlag(P.tid)],
  ];
  const now = checks.findIndex((c) => !c[1]);
  return h("div", { class: "leftcol" },
    h("div", { class: "card" }, h("h3", {}, "출장 정보"),
      field("전시회 이름", f.name), field("장소", f.venue), field("날짜", dates), field("목적", f.purpose),
      h("div", { class: "row" }, save),
      h("button", { class: "btn primary", style: "height:46px;font-size:15px", onclick: openKeywordPrompt }, "AI 프롬프트 만들기")),
    h("div", { class: "card" }, h("h4", {}, "진행 상황"),
      ...checks.map(([t, done], i) => h("div", { class: "check " + (done ? "done" : i === now ? "now" : "") }, h("i", {}, done ? "✓" : ""), t)),
      h("div", { style: "height:1px;background:var(--line2)" }),
      h("div", { class: "row" },
        h("button", { class: "btn sm", onclick: () => { P.tab = "map"; redraw(); } }, "맵 PDF 직접 올리기"),
        h("button", { class: "btn sm", onclick: () => { P.tab = "map"; redraw(); } }, "URL 붙여넣기"))),
  );
}

// ---------------- 오른쪽: 탭 ----------------
function panel(s) {
  const tabs = [["cands", `후보 업체 ${s.all}`], ["plan", "일정 배분"], ["map", `전시장 맵 ${s.maps || ""}`.trim()], ["gloss", "용어집"]];
  return h("div", { class: "panel" },
    h("div", { class: "tabs", role: "tablist" }, ...tabs.map(([k, label]) => h("button", { class: P.tab === k ? "on" : "", role: "tab", onclick: () => { P.tab = k; redraw(); } }, label))),
    P.tab === "cands" ? candsTab(s) : P.tab === "plan" ? planTab(s) : P.tab === "map" ? mapTab() : glossTab(),
  );
}

function dayLabel(d) { return d ? "Day " + d : "미배정"; }

function dayPicker(c) {
  const { days } = P.v.trip;
  const sel = h("select", { class: "dayb" + (c.day ? " set" : ""), "aria-label": c.name + " 방문일", onchange: () => {
    const val = sel.value ? Number(sel.value) : null;
    const list = P.v.companies.map((x) => (x.id === c.id ? { ...x, day: val, picked: val ? true : x.picked } : x));
    guard(() => saveCompanies(list));
  } }, h("option", { value: "" }, "미배정"), ...days.map((d, i) => h("option", { value: i + 1 }, `Day ${i + 1}`)));
  sel.value = c.day || "";
  return sel;
}

function candsTab(s) {
  const cs = P.v.companies;
  if (!cs.length) {
    return h("div", { class: "empty" }, h("b", {}, "아직 후보 업체가 없어요"),
      h("div", {}, "키워드를 적어 Claude Chat 용 프롬프트를 만들고, 받은 답을 붙여 넣으면 후보가 채워져요. CSV/Excel 업체 목록을 가져와도 돼요."),
      h("div", { class: "row", style: "justify-content:center" },
        h("button", { class: "btn primary", onclick: openKeywordPrompt }, "AI 프롬프트 만들기"),
        csvButton(), h("button", { class: "btn", onclick: () => openCompanyEditor(null) }, "+ 업체 직접 추가")));
  }
  const cats = new Map();
  cs.forEach((c) => cats.set(c.category || "기타", (cats.get(c.category || "기타") || 0) + 1));
  const chips = [["전체", cs.length], ["선택됨", s.picked], ...[...cats.entries()].sort((a, b) => b[1] - a[1])];
  const q = P.q.trim().toLowerCase();
  const shown = cs.filter((c) => {
    if (P.cat === "선택됨" && c.picked === false) return false;
    if (P.cat !== "전체" && P.cat !== "선택됨" && (c.category || "기타") !== P.cat) return false;
    return !q || (c.name + " " + c.category + " " + (c.reason || "")).toLowerCase().includes(q);
  });
  const header = h("div", { class: "tr head" }, h("div"), h("div", {}, "업체"), h("div", {}, "카테고리"), h("div", {}, "홀 · 부스"), h("div", {}, "선별 이유"), h("div", {}, "방문일"), h("div"));
  const rows = shown.map((c) => {
    const on = c.picked !== false;
    const cb = h("button", { class: "cb" + (on ? " on" : ""), role: "checkbox", "aria-checked": String(on), "aria-label": c.name + " 선택", onclick: () => {
      guard(() => saveCompanies(P.v.companies.map((x) => (x.id === c.id ? { ...x, picked: !on } : x))));
    } }, on ? "✓" : "");
    const loc = c.hall || c.booth ? `${c.hall || "?"} · ${c.booth || "?"}` : "미확인";
    const why = [c.reason || c.preNotes?.split("\n")[0] || ""];
    return h("div", { class: "tr" + (on ? "" : " off") }, cb,
      h("div", { class: "nm" }, c.name,
        c.source === "ai" ? (c.verified ? h("span", { class: "tag green" }, "참가 확인") : h("span", { class: "tag" }, "AI 추정")) : c.source === "csv" ? null : h("span", { class: "tag" }, "내가 추가")),
      h("div", {}, c.category || "기타"), h("div", { class: c.hall || c.booth ? "" : "sub" }, loc),
      h("div", { class: "why" }, why[0], c.sourceUrl ? h("span", {}, " ", h("a", { href: c.sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "출처")) : null),
      dayPicker(c),
      h("button", { class: "btn sm ghost", "aria-label": c.name + " 편집", onclick: () => openCompanyEditor(c), style: "padding:0" }, "✎"));
  });
  const perDay = P.v.trip.days.map((_, i) => cs.filter((c) => c.picked !== false && c.day === i + 1).length);
  return h("div", { style: "display:flex;flex-direction:column" },
    h("div", { class: "chips" }, ...chips.map(([name, n]) => h("button", { class: "chip" + (P.cat === name ? " on" : ""), onclick: () => { P.cat = name; redraw(); } }, `${name} ${n}`)),
      h("input", { type: "search", placeholder: "이름·이유 검색", value: P.q, style: "width:180px;height:34px;margin-left:auto", oninput: (e) => { P.q = e.target.value; const pos = e.target.selectionStart; redraw(); const el = P.root.querySelector('input[type=search]'); el.focus(); el.setSelectionRange(pos, pos); } })),
    h("div", { class: "table" }, header, ...(rows.length ? rows : [h("div", { class: "empty" }, "조건에 맞는 업체가 없어요.")])),
    h("div", { class: "foot" },
      h("div", {}, h("b", {}, `선택 ${s.picked}곳` + perDay.map((n, i) => (n ? ` · Day ${i + 1} ${n}곳` : "")).join("")),
        h("div", { class: "sub" }, s.picked - s.dated ? `일정 미배정 ${s.picked - s.dated}곳 · '일정 배분' 탭에서 한 번에 나눌 수 있어요` : "모든 선택 업체에 방문일이 있어요")),
      h("div", { class: "row" },
        h("button", { class: "btn", onclick: () => openCompanyEditor(null) }, "+ 업체 직접 추가"), csvButton(),
        h("button", { class: "btn primary", onclick: confirmPackage }, "패키지 확정 · 폰으로 보내기"))));
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
  const move = (c, to) => guard(() => saveCompanies(P.v.companies.map((x) => (x.id === c.id ? { ...x, day: to } : x))));
  const card = (c) => {
    const d = c.day || 0;
    return h("div", { class: "card2" }, h("div", { class: "t" }, c.name), h("div", { class: "m" }, `${c.category || "기타"} · ${c.hall || c.booth ? `${c.hall || "?"} ${c.booth || ""}` : "위치 미확인"}`),
      h("div", { class: "mv" },
        h("button", { "aria-label": "앞 일차로", disabled: d <= 0, onclick: () => move(c, d - 1 || null) }, "◀"),
        h("button", { "aria-label": "다음 일차로", disabled: d >= days.length, onclick: () => move(c, d + 1) }, "▶")));
  };
  const col = (title, list) => h("div", { class: "col" }, h("h4", {}, title, h("span", {}, list.length + "곳")), ...list.map(card));
  return h("div", { style: "display:flex;flex-direction:column" },
    h("div", { class: "pad", style: "padding-bottom:0" }, h("div", { class: "row" },
      h("button", { class: "btn primary sm", onclick: autoAssign }, "홀 기준으로 자동 배분"),
      h("span", { class: "sub" }, "아직 일차가 없는 업체만 같은 홀끼리 묶어 나눠요. 이미 정한 일정은 그대로 둬요."))),
    h("div", { class: "board" }, col("미배정", picked.filter((c) => !c.day)), ...days.map((d, i) => col(`Day ${i + 1} · ${d.slice(5)}`, picked.filter((c) => c.day === i + 1)))));
}

function autoAssign() {
  const n = P.v.trip.days.length;
  const todo = P.v.companies.filter((c) => c.picked !== false && !c.day).sort((a, b) => (a.hall || "~").localeCompare(b.hall || "~") || (a.booth || "").localeCompare(b.booth || "", undefined, { numeric: true }));
  if (!todo.length) return toast("나눌 업체가 없어요.");
  const load = P.v.trip.days.map((_, i) => P.v.companies.filter((c) => c.picked !== false && c.day === i + 1).length);
  const total = load.reduce((a, b) => a + b, 0) + todo.length;
  const target = Math.ceil(total / n);
  const assign = new Map();
  let d = 0;
  todo.forEach((c, i) => {
    while (d < n - 1 && load[d] >= target && !(todo[i - 1] && todo[i - 1].hall === c.hall && c.hall && load[d] < target + 3)) d++;
    assign.set(c.id, d + 1);
    load[d]++;
  });
  guard(() => saveCompanies(P.v.companies.map((c) => (assign.has(c.id) ? { ...c, day: assign.get(c.id) } : c))));
  toast(`${todo.length}곳을 나눴어요. 필요하면 ◀ ▶ 로 옮기세요.`);
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
    h("div", { class: "row" }, file, h("button", { class: "btn", onclick: () => file.click() }, "내 컴퓨터의 지도 파일 올리기"), h("span", { class: "sub" }, "PDF·PNG·JPG")));
}

// ---------------- 용어집 ----------------
function glossTab() {
  const ta = h("textarea", { style: "min-height:260px", placeholder: "한 줄에 하나씩\nEtherCAT\npayload\n협동로봇" }, P.v.glossary.join("\n"));
  return h("div", { class: "pad" },
    h("div", { class: "msg" }, "여기 적은 용어는 ① 폰의 번역 힌트, ② 녹음 전사·AI 교정에서 '이렇게 적어 달라'는 기준으로 쓰여요. 회사명, 제품명, 약어를 넣어 두세요."),
    ta, h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => guard(async () => { P.v = await api("PUT", `/trips/${P.tid}/glossary`, ta.value.split("\n")); redraw(); toast("저장했어요."); }) }, "저장"),
      h("span", { class: "sub" }, `${P.v.glossary.length}개`)));
}

// ---------------- 업체 편집/추가 ----------------
function openCompanyEditor(c) {
  modal(c ? "업체 편집" : "업체 직접 추가", (m, close) => {
    const f = {
      name: h("input", { value: c?.name || "" }), category: h("input", { value: c?.category || "", placeholder: "예) 협동로봇" }),
      hall: h("input", { value: c?.hall || "" }), booth: h("input", { value: c?.booth || "" }),
      preNotes: h("textarea", { value: c?.preNotes || "", placeholder: "사전 메모 (폰에서 업체 화면에 보여요)" }),
      questions: h("textarea", { value: (c?.questions || []).join("\n"), placeholder: "확인할 질문 (한 줄에 하나)" }),
    };
    const fld = (l, el) => h("div", { class: "field" }, h("label", {}, l), el);
    m.append(fld("업체명", f.name), h("div", { class: "row" }, h("div", { class: "grow" }, fld("카테고리", f.category)), h("div", { style: "width:100px" }, fld("홀", f.hall)), h("div", { style: "width:100px" }, fld("부스", f.booth))),
      fld("사전 메모", f.preNotes), fld("확인할 질문", f.questions));
    if (c?.reason) m.append(h("div", { class: "msg" }, "AI가 적은 이유: " + c.reason));
    m.append(h("div", { class: "row", style: "justify-content:space-between" },
      c ? h("button", { class: "btn danger", onclick: () => confirmBox("업체 삭제", `'${c.name}' 을(를) 목록에서 지울까요?`, "삭제", () => guard(() => saveCompanies(P.v.companies.filter((x) => x.id !== c.id))), true) }, "삭제") : h("span"),
      h("button", { class: "btn primary", onclick: () => {
        if (!f.name.value.trim()) return toast("업체명을 입력해 주세요.", true);
        const data = { name: f.name.value.trim(), category: f.category.value.trim() || "기타", hall: f.hall.value.trim(), booth: f.booth.value.trim(), preNotes: f.preNotes.value, questions: f.questions.value.split("\n").map((x) => x.trim()).filter(Boolean) };
        const list = c ? P.v.companies.map((x) => (x.id === c.id ? { ...x, ...data } : x))
          : [...P.v.companies, { id: "c-" + Math.random().toString(16).slice(2, 10), day: null, picked: true, source: "manual", ...data }];
        close();
        guard(() => saveCompanies(list));
      } }, "저장")));
  });
}

// ---------------- AI 프롬프트(키워드) ----------------
function openKeywordPrompt() {
  const kw = h("input", { placeholder: "예) 휴머노이드, 용접 로봇, 비전 센서", value: "" });
  const count = h("select", {}, ...[10, 20, 30, 40].map((n) => h("option", { value: n }, `${n}곳`)));
  count.value = "20";
  let last = "";
  promptModal({
    title: "키워드로 참가업체 찾기 (Claude Chat 용)",
    intro: "Desk 가 AI를 직접 부르지는 않아요. 키워드를 적으면 Claude Chat 에 붙여 넣을 프롬프트를 만들어 주고, Claude 의 답을 붙여 넣으면 후보 목록에 쌓여요. 이미 목록에 있는 업체는 프롬프트에서 제외돼요.",
    auto: false,
    extraTop: (ctl) => h("div", { class: "row" },
      h("div", { class: "grow field" }, h("label", {}, "찾고 싶은 키워드 (쉼표로 구분)"), kw),
      h("div", { class: "field", style: "width:110px" }, h("label", {}, "개수"), count),
      h("button", { class: "btn primary", style: "align-self:flex-end", onclick: () => { last = kw.value; ctl.load(); } }, "프롬프트 만들기")),
    getPrompts: async () => {
      const r = await api("POST", `/trips/${P.tid}/prompt/exhibitors`, { keywords: kw.value, count: Number(count.value) });
      return [r.prompt];
    },
    onPaste: async (text) => {
      const r = await api("POST", `/trips/${P.tid}/paste/exhibitors`, { text, keywords: last || kw.value });
      P.v = r;
      P.tab = "cands";
      P.cat = "전체";
      redraw();
      P.app.refreshSide();
      const p = r.pasted;
      toast(`후보 ${p.added}곳을 추가했어요` + (p.existing ? ` (이미 있던 ${p.existing}곳은 제외)` : "") + (p.unverified ? ` · 참가 미확인 ${p.unverified}곳` : ""));
      if (p.notes) toast("Claude 메모: " + p.notes);
    },
  });
}

// ---------------- 패키지 ----------------
function confirmPackage() {
  const s = stats();
  const warns = P.v.warnings;
  modal("패키지 확정", (m, close) => {
    m.append(h("div", { class: "msg" }, `선택한 ${s.picked}곳, 대표 지도 ${s.maps ? "1장" : "없음"}, 용어 ${P.v.glossary.length}개가 들어가요.`));
    if (warns.length) m.append(h("div", { class: "msg warn" }, h("b", {}, "확인해 주세요"), h("ul", { style: "margin:6px 0 0;padding-left:18px" }, ...warns.map((w) => h("li", {}, w)))));
    m.append(h("div", { class: "msg" }, h("b", {}, "폰으로 옮기는 방법"), h("ol", { style: "margin:6px 0 0;padding-left:18px;line-height:1.7" },
      h("li", {}, "내려받은 ZIP 파일을 AirDrop·메일·USB 등으로 폰에 보내세요."),
      h("li", {}, "폰에서 Trip Field → 설정 → '새 출장 · 패키지 불러오기'로 그 파일을 선택하세요."),
      h("li", {}, "폰에서 오프라인으로도 열리는지 비행기 모드로 한 번 확인해 두면 안심이에요."))));
    m.append(h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: close }, "취소"),
      h("button", { class: "btn primary", disabled: !s.picked && false, onclick: () => {
        download(`/trips/${P.tid}/package`);
        try { localStorage.setItem(flagKey(P.tid), "1"); } catch {}
        close();
        setTimeout(redraw, 200);
      } }, "ZIP 내려받기")));
  });
}
