// 식사·이동 탭: 경유 공항·숙소 주변 식사 장소, 공항↔숙소↔행사장 교통편 (AI 챗봇 프롬프트 → 붙여넣기 → 저장)
import { h, api, toast, guard, confirmBox, promptModal, spinner } from "./core.js";

const WD = ["일", "월", "화", "수", "목", "금", "토"];
const when = (dt) => {
  if (!dt) return "";
  const [d, t] = dt.split("T");
  return `${+d.slice(5, 7)}/${+d.slice(8, 10)}(${WD[new Date(d + "T00:00").getDay()]})${t ? " " + t : ""}`;
};
const span = (m) => (m == null ? "" : m < 0 ? "시각 확인 필요" : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`);
const mapUrl = (q) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
// 선 아이콘 (이모지는 운영체제마다 모양이 달라서 SVG 로 그린다). 고정된 문자열만 쓴다.
const PATHS = {
  pin: '<path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  money: '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>',
  train: '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14M8 21l2-4M16 21l-2-4"/>',
  star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
};
const ico = (name, { size = 16, fill = false, width = 2 } = {}) => {
  const s = h("span", { class: "ico", "aria-hidden": "true" });
  s.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="${fill ? "currentColor" : "none"}" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${PATHS[name]}</svg>`;
  return s;
};
const line = (name, text) => h("div", { class: "ln" }, ico(name), h("span", {}, text));
const link = (href, text) => h("a", { class: "btn sm", href, target: "_blank", rel: "noopener noreferrer" }, text);

export function localTab(P) {
  const host = h("div", { class: "pad", style: "display:flex;flex-direction:column;gap:14px;background:var(--bg)" }, spinner("불러오는 중…"));
  const base = `/trips/${P.tid}/local`;
  let V = null;
  const picked = { meals: null, legs: null };   // 체크 상태는 다시 그려도 유지
  const draw = (v) => { V = v || V; paint(); };
  const load = async () => draw(await api("GET", base));
  const put = (patch) => guard(async () => { draw(await api("PUT", base, patch)); return true; });

  function paint() {
    const { local: L, targets: T, legs } = V;
    if (!picked.meals) picked.meals = new Set([...T.airports.map((a) => a.ref), ...T.hotels.map((x) => x.ref)]);   // 행사장은 직접 켠다
    if (!picked.legs) picked.legs = new Set(["arr-hotel", "hotel-venue", "hotel-dep"]);
    const prefs = h("input", { value: L.prefs || "", placeholder: "예) 한식 좋아함 · 혼밥 · 1끼 25유로 이내 · 밤 늦게 이동은 피하고 싶음", style: "flex:1" });
    const savePrefs = () => { if (prefs.value !== (L.prefs || "")) put({ prefs: prefs.value }); };
    prefs.addEventListener("change", savePrefs);

    // 고른 대상을 칩으로 보여 준다 (체크하면 파란 칩, 해제하면 흰 칩). 상세는 칩 아래 설명에 둔다.
    const check = (set, key, label, sub) => {
      const cb = h("input", { type: "checkbox", checked: set.has(key), onchange: () => { cb.checked ? set.add(key) : set.delete(key); chip.classList.toggle("off", !cb.checked); btnSync(); } });
      const chip = h("label", { class: "chk" + (set.has(key) ? "" : " off"), title: sub || "" }, cb, h("span", {}, label));
      return chip;
    };
    const btnSync = () => { const m = host.querySelector("[data-act=meals]"), r = host.querySelector("[data-act=routes]"); if (m) m.disabled = !picked.meals.size; if (r) r.disabled = !picked.legs.size; };

    // ---- 식사 ----
    const airRows = T.airports.map((a) => check(picked.meals, a.ref, `${a.code} 경유 · ${a.direction === "return" ? "오는 편" : "가는 편"} · 대기 ${span(a.minutes) || "?"}${a.airportChange ? " · 공항 변경" : ""}`,
      `${a.flight} · ${when(a.arrive)} 도착${a.arrTerm ? " T" + a.arrTerm : ""} → ${when(a.depart)} 출발${a.depTerm ? " T" + a.depTerm : ""} · 대기 ${span(a.minutes) || "?"}${a.airportChange ? " · ⚠ 공항 변경" : ""}`));
    const hotRows = T.hotels.map((x) => check(picked.meals, x.ref, `${x.name} 주변`, `${x.address || "주소 미입력"} · ${x.checkIn || "?"} ~ ${x.checkOut || "?"}`));
    const hints = [airRows.length ? null : "경유 공항이 없어요(항공·숙소 탭에 경유 항공편을 기록하면 경유 공항별로 고를 수 있어요).", hotRows.length ? null : "숙소 기록이 없어요(항공·숙소 탭에 숙소를 기록하세요)."].filter(Boolean);
    const targets = h("div", {}, h("div", { class: "chips" }, ...airRows, ...hotRows, check(picked.meals, "venue", `행사장 안팎`, `행사장(${T.venue.name}) — 전시 중 점심: 식당가·가까운 외부 식당`)),
      ...hints.map((t) => h("div", { class: "sub", style: "margin-top:6px" }, t)));
    const askMeals = () => promptModal({
      title: "식사 장소 찾기 (AI 챗봇용)",
      intro: "고른 곳마다 따로 추천해 달라는 프롬프트예요. AI 챗봇에 붙여 넣고(웹 검색 켜기) 답변 전체를 아래에 붙여 넣으면 저장돼요.",
      getPrompts: async () => [(await api("POST", base + "/prompt", { kind: "meals", targets: [...picked.meals], prefs: prefs.value })).prompt],
      onPaste: async (text) => { const r = await api("POST", base + "/paste", { kind: "meals", text }); draw(r); toast(`식사 장소 ${r.pasted.added}곳 추가` + (r.pasted.updated ? `, ${r.pasted.updated}곳 갱신` : "") + "했어요."); },
    });

    const groups = new Map();
    L.meals.forEach((m) => { const k = m.ref || "etc:" + m.area; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(m); });
    const gname = (k, ms) => k.startsWith("lay:") ? `${(T.airports.find((a) => a.ref === k) || {}).code || ms[0].area} 공항 경유` : k.startsWith("hotel:") ? `${(T.hotels.find((x) => x.ref === k) || {}).name || ms[0].area} 주변` : k === "venue" ? `행사장(${T.venue.name})` : ms[0].area || "기타";
    const placeRow = (m) => h("div", { class: "place" },
      h("button", { class: "btn sm ic star" + (m.fav ? " on" : ""), "aria-pressed": String(m.fav), "aria-label": m.name + (m.fav ? " 즐겨찾기 해제" : " 즐겨찾기"), title: m.fav ? "즐겨찾기 해제" : "즐겨찾기 (폰에서 맨 위에 보여요)", onclick: () => put({ meals: L.meals.map((x) => (x.id === m.id ? { ...x, fav: !x.fav } : x)) }) }, ico("star", { size: 18, fill: m.fav, width: 1.8 })),
      h("div", { class: "grow", style: "display:flex;flex-direction:column;gap:4px;min-width:0" },
        h("div", {}, h("b", { style: "font-size:16px" }, m.name), m.meal ? h("span", { class: "pill", style: "margin-left:8px" }, m.meal) : null, m.cuisine ? h("span", { class: "sub" }, "  " + m.cuisine) : null),
        m.where ? line("pin", m.where) : null, m.hours ? line("clock", m.hours) : null, m.price ? line("money", m.price) : null,
        m.why ? h("div", {}, m.why) : null, m.tip ? h("div", { class: "sub" }, "팁: " + m.tip) : null),
      h("div", { class: "row", style: "gap:6px;flex-wrap:wrap;justify-content:flex-end" },
        link(mapUrl(`${m.name} ${m.where || m.area}`), "지도"), m.sourceUrl ? link(m.sourceUrl, "출처") : null,
        h("button", { class: "btn sm ic danger", "aria-label": m.name + " 삭제", title: "삭제", onclick: () => put({ meals: L.meals.filter((x) => x.id !== m.id) }) }, ico("x", { width: 2.4 }))));
    const mealList = [...groups].map(([k, ms]) => h("div", { class: "grp" },
      h("div", { class: "row", style: "justify-content:space-between" }, h("b", { style: "font-size:15px" }, `${gname(k, ms)} · ${ms.length}곳`),
        h("button", { class: "btn sm danger", onclick: () => confirmBox("목록 비우기", `'${gname(k, ms)}' 식사 장소 ${ms.length}곳을 지울까요?`, "비우기", () => put({ meals: L.meals.filter((x) => (x.ref || "etc:" + x.area) !== k) }), true) }, "비우기")),
      ...ms.map(placeRow)));

    const meals = h("div", { class: "card" }, h("div", { class: "row" }, h("h3", {}, "식사 장소"), L.meals.length ? h("span", { class: "pill gray" }, `${L.meals.length}곳 저장됨`) : null),
      h("div", { class: "msg" }, "경유 공항은 '대기 시간 안에 실제로 먹고 올 수 있는지'를, 숙소는 '걸어갈 수 있고 그 시각에 여는지'를 따져서 찾도록 프롬프트를 만들어요. 고른 곳마다 따로 정리돼요."),
      targets,
      h("div", { class: "row" }, h("button", { class: "btn primary", "data-act": "meals", disabled: !picked.meals.size, onclick: askMeals }, "식사 장소 프롬프트 만들기")),
      ...(mealList.length ? mealList : [h("div", { class: "sub" }, "아직 저장된 식사 장소가 없어요.")]));

    // ---- 교통 ----
    const arr = T.arrival, dep = T.departure;
    const legSub = {
      "arr-hotel": `${arr.airport || "도착 공항 미입력"}${arr.terminal ? " T" + arr.terminal : ""} → ${T.hotels[0] ? T.hotels[0].name : "숙소 미입력"}${arr.time ? " · " + when(arr.time) + " 도착" : ""}`,
      "hotel-venue": `${T.hotels[0] ? T.hotels[0].name : "숙소 미입력"} ↔ ${T.venue.name}`,
      "hotel-dep": `${T.hotels[0] ? T.hotels[0].name : "숙소 미입력"} → ${dep.airport || "출발 공항 미입력"}${dep.time ? " · " + when(dep.time) + " 출발" : ""}`,
    };
    const askRoutes = () => promptModal({
      title: "현지 교통편 찾기 (AI 챗봇용)",
      intro: "노선·정류장·요금·표 사는 법·행사 입장권에 교통이 포함되는지까지 묻는 프롬프트예요. 같은 구간을 다시 받으면 그 구간은 새 답변으로 바뀌어요.",
      getPrompts: async () => [(await api("POST", base + "/prompt", { kind: "transport", targets: [...picked.legs], prefs: prefs.value })).prompt],
      onPaste: async (text) => { const r = await api("POST", base + "/paste", { kind: "transport", text }); draw(r); toast(`교통 ${r.pasted.added}건` + (r.pasted.updated ? `, 표·패스 ${r.pasted.updated}건` : "") + "을 저장했어요."); },
    });
    const routeCard = (r) => h("div", { class: "grp" },
      h("div", { class: "row", style: "align-items:flex-start" },
        h("div", { class: "grow" }, h("b", { style: "font-size:16px" }, r.label || `${r.from} → ${r.to}`), " ", [r.mode, r.line].filter(Boolean).length ? h("span", { class: "pill" }, [r.mode, r.line].filter(Boolean).join(" ")) : null),
        h("button", { class: "btn sm ic star" + (r.fav ? " on" : ""), "aria-pressed": String(r.fav), "aria-label": (r.label || r.line || "교통편") + (r.fav ? " 즐겨찾기 해제" : " 즐겨찾기"), title: "즐겨찾기 (폰에서 맨 위)", onclick: () => put({ routes: L.routes.map((x) => (x.id === r.id ? { ...x, fav: !x.fav } : x)) }) }, ico("star", { size: 18, fill: r.fav, width: 1.8 })),
        h("button", { class: "btn sm ic danger", "aria-label": "삭제", title: "삭제", onclick: () => put({ routes: L.routes.filter((x) => x.id !== r.id) }) }, ico("x", { width: 2.4 }))),
      r.boardStation || r.alightStation ? h("div", { class: "ln" }, ico("train"), h("span", {}, h("b", {}, r.boardStation || "?"), " 승차 → ", h("b", {}, r.alightStation || "?"), " 하차", r.durationMin ? ` · 약 ${r.durationMin}분` : "")) : (r.durationMin ? line("clock", `약 ${r.durationMin}분`) : null),
      [r.frequency, r.firstLast].filter(Boolean).length ? line("clock", [r.frequency, r.firstLast].filter(Boolean).join(" · ")) : null,
      r.fare || r.ticket ? line("money", [r.fare, r.ticket].filter(Boolean).join(" · ")) : null,
      r.whereToBuy ? h("div", { class: "sub" }, "표 구입: " + r.whereToBuy) : null, r.taxi ? h("div", { class: "sub" }, "택시: " + r.taxi) : null,
      r.steps.length ? h("ol", { style: "margin:4px 0 0;padding-left:20px" }, ...r.steps.map((s) => h("li", {}, s))) : null,
      r.tips ? h("div", { class: "sub" }, "팁: " + r.tips) : null,
      h("div", { class: "row", style: "gap:6px" }, link(mapUrl(`${r.from} to ${r.to}`), "지도"), r.sourceUrl ? link(r.sourceUrl, "출처") : null));
    const passRow = (p) => h("div", { class: "row", style: "align-items:flex-start;border-top:1px solid #EEF1F4;padding:8px 0" },
      h("div", { class: "grow" }, h("b", {}, p.name), p.price ? " · " + p.price : "", p.valid ? h("div", { class: "sub" }, "유효: " + p.valid) : null, p.whereToBuy ? h("div", { class: "sub" }, "구입: " + p.whereToBuy) : null, p.note ? h("div", { class: "sub" }, p.note) : null),
      h("button", { class: "btn sm ic danger", "aria-label": p.name + " 삭제", title: "삭제", onclick: () => put({ passes: L.passes.filter((x) => x.id !== p.id) }) }, ico("x", { width: 2.4 })));
    const byLeg = Object.keys(legs).map((k) => [k, L.routes.filter((r) => r.leg === k)]).filter(([, rs]) => rs.length);
    const transport = h("div", { class: "card" }, h("div", { class: "row" }, h("h3", {}, "현지 교통"), L.routes.length ? h("span", { class: "pill gray" }, `${L.routes.length}건` + (L.passes.length ? ` · 표·패스 ${L.passes.length}건` : "")) : null),
      h("div", { class: "msg" }, "숙소와 행사장이 멀 때 공항↔숙소↔행사장 이동을 어떻게 하면 되는지 — 노선·승하차 역·소요 시간·요금·표 구입처·막차까지 찾도록 프롬프트를 만들어요."),
      h("div", {}, h("div", { class: "chips" }, ...["arr-hotel", "hotel-venue", "hotel-dep"].map((k) => check(picked.legs, k, legs[k], legSub[k]))), ...["arr-hotel", "hotel-venue", "hotel-dep"].map((k) => h("div", { class: "sub", style: "margin-top:4px" }, `${legs[k]}: ${legSub[k]}`))),
      h("div", { class: "row" }, h("button", { class: "btn primary", "data-act": "routes", disabled: !picked.legs.size, onclick: askRoutes }, "교통편 프롬프트 만들기")),
      ...(byLeg.length ? byLeg.flatMap(([k, rs]) => [h("h4", {}, legs[k]), ...rs.map(routeCard)]) : [h("div", { class: "sub" }, "아직 저장된 교통 정보가 없어요.")]),
      L.passes.length ? h("div", { class: "grp" }, h("b", { style: "font-size:15px" }, "표·패스"), ...L.passes.map(passRow)) : null,
      L.notes ? h("div", { class: "msg" }, L.notes) : null);

    host.replaceChildren(
      h("div", { class: "card", style: "flex-direction:row;align-items:center;gap:12px;padding:12px 18px;flex-wrap:wrap" }, h("b", { style: "white-space:nowrap" }, "내 취향·제약"), prefs,
        h("span", { class: "sub" }, "두 프롬프트에 함께 들어가요"), h("button", { class: "btn sm", onclick: () => { savePrefs(); toast("저장했어요."); } }, "저장")),
      h("div", { class: "twocol" }, meals, transport));
  }

  load().catch((e) => host.replaceChildren(h("div", { class: "msg err" }, e.message)));
  return host;
}
