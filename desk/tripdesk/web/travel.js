// 항공·숙소 탭: 검색 바로가기, AI 챗봇 후보 찾기, 예약 기록
import { h, api, toast, guard, modal, confirmBox, promptModal } from "./core.js";

const DIR = { outbound: "가는 편", return: "오는 편", other: "기타" };
const money = (x) => (x.amount == null ? "" : `${Number(x.amount).toLocaleString()} ${x.currency}`);
const fld = (l, el, w) => h("div", { class: "field", style: w ? `width:${w}px` : "flex:1;min-width:140px" }, h("label", {}, l), el);

// 날짜·시각 표기는 모두 24시간제(AM/PM 없음)
const WD = ["일", "월", "화", "수", "목", "금", "토"];
const when = (dt) => {
  if (!dt) return "";
  const [d, t] = dt.split("T");
  return `${+d.slice(5, 7)}/${+d.slice(8, 10)}(${WD[new Date(d + "T00:00").getDay()]})${t ? " " + t : ""}`;
};
const span = (m) => (m == null ? "" : m < 0 ? "시각 확인 필요" : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`);
const normTime = (v) => {
  const d = String(v || "").replace(/\D/g, "");
  if (d.length < 3 || d.length > 4) return "";
  const hh = +d.slice(0, d.length - 2), mm = +d.slice(-2);
  return hh < 24 && mm < 60 ? `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}` : "";
};
// 날짜 + 24시간제 시각 입력 (브라우저 기본 시각 입력은 AM/PM 으로 보일 수 있어 직접 만든다)
function dtField(value) {
  const [d0, t0] = String(value || "").split("T");
  const date = h("input", { type: "date", value: d0 || "", style: "flex:1;min-width:130px" });
  const time = h("input", { value: t0 || "", placeholder: "HH:MM", inputmode: "numeric", maxlength: "5", style: "width:76px", "aria-label": "시각(24시간제)" });
  time.addEventListener("input", () => { time.value = time.value.replace(/[^\d:]/g, ""); });
  time.addEventListener("blur", () => { time.value = normTime(time.value) || (time.value ? time.value : ""); time.classList.toggle("bad", !!time.value && !normTime(time.value)); });
  const el = h("div", { class: "row", style: "gap:6px" }, date, time);
  return { el, get: () => (date.value ? date.value + (normTime(time.value) ? "T" + normTime(time.value) : "") : ""), bad: () => !!time.value && !normTime(time.value) };
}
const segText = (g) => `${g.flightNo || (g.mode === "ground" ? "지상 이동" : "")} ${g.from}${g.fromTerm ? " T" + g.fromTerm : ""} → ${g.to}${g.toTerm ? " T" + g.toTerm : ""} · ${when(g.depart)} → ${g.arrive ? (g.arrive.slice(0, 10) === g.depart.slice(0, 10) ? g.arrive.slice(11) : when(g.arrive)) : "?"}`.trim();

let candTab = "flights";

export function travelTab(P) {
  const host = h("div", { class: "pad" }, h("div", { class: "sub" }, "불러오는 중…"));
  const base = `/trips/${P.tid}/travel`;
  let V = null;
  const load = async (v) => { V = v || (await api("GET", base)); draw(); };
  const put = (patch) => guard(async () => { await load(await api("PUT", base, patch)); return true; });

  // 다시 그려도 보던 위치를 유지한다 (탭 전환·저장 때 화면이 맨 위로 튀지 않게)
  function scroller() {
    for (let el = host.parentElement; el; el = el.parentElement) if (el.scrollHeight > el.clientHeight && /(auto|scroll)/.test(getComputedStyle(el).overflowY)) return el;
    return document.scrollingElement;
  }

  function draw() {
    const sc = scroller(), top = sc ? sc.scrollTop : 0;
    paint();
    if (sc) { sc.scrollTop = top; requestAnimationFrame(() => { sc.scrollTop = top; }); }
  }

  function paint() {
    const { travel: T, links, summary } = V;
    const days = P.v.trip.days;
    const f = {
      origin: h("input", { value: T.origin, placeholder: "예) ICN 또는 인천" }), destination: h("input", { value: T.destination, placeholder: "예) NUE 또는 뉘른베르크" }),
      outDate: h("input", { type: "date", value: T.outDate || links.dates.out }), retDate: h("input", { type: "date", value: T.retDate || links.dates.ret }),
      checkIn: h("input", { type: "date", value: T.checkIn || links.dates.checkIn }), checkOut: h("input", { type: "date", value: T.checkOut || links.dates.checkOut }),
      minStars: h("select", {}, ...[1, 2, 3, 4, 5].map((n) => h("option", { value: n }, `${n}성`))), maxStars: h("select", {}, ...[1, 2, 3, 4, 5].map((n) => h("option", { value: n }, `${n}성`))),
    };
    f.minStars.value = T.minStars; f.maxStars.value = T.maxStars;
    const dflt = { outDate: links.dates.out, retDate: links.dates.ret, checkIn: links.dates.checkIn, checkOut: links.dates.checkOut };
    // 출장 기간 기본값과 같은 날짜는 '직접 지정'으로 저장하지 않는다 (출장 날짜를 바꾸면 같이 따라가도록)
    const saveSettings = () => put(Object.fromEntries(Object.entries(f).map(([k, el]) => [k, dflt[k] === el.value ? "" : el.value])));

    const settings = h("div", { class: "card" }, h("h3", {}, "이동 조건"),
      h("div", { class: "row", style: "align-items:flex-end;flex-wrap:wrap" }, fld("출발지", f.origin), fld("목적지(도시/공항)", f.destination)),
      h("div", { class: "row", style: "align-items:flex-end;flex-wrap:wrap" }, fld("가는 날", f.outDate, 150), fld("오는 날", f.retDate, 150), fld("체크인", f.checkIn, 150), fld("체크아웃", f.checkOut, 150)),
      h("div", { class: "row", style: "align-items:flex-end;flex-wrap:wrap" }, fld("호텔 등급 최소", f.minStars, 110), fld("호텔 등급 최대", f.maxStars, 110),
        h("span", { class: "sub", style: "flex:1;min-width:200px" }, "호텔 자체의 성급입니다(투숙객 리뷰 평점 아님). 날짜는 출장 기간으로 미리 채워져 있어요."),
        h("button", { class: "btn primary", onclick: () => saveSettings().then((ok) => ok && toast("저장했어요.")) }, "저장")));

    const linkBtns = (arr) => arr.length ? h("div", { class: "row", style: "flex-wrap:wrap" }, ...arr.map((l) => h("a", { class: "btn", href: l.url, target: "_blank", rel: "noopener noreferrer" }, l.name + " ↗"))) : h("div", { class: "sub" }, "위에서 출발지·목적지를 저장하면 검색 버튼이 생겨요.");
    const search = h("div", { class: "card" }, h("h3", {}, "검색 바로가기"),
      h("div", { class: "msg" }, "각 사이트의 검색 화면을 조건이 채워진 채로 열어요. 사이트가 주소 형식을 바꾸면 일부(특히 호텔 등급 필터)가 안 채워질 수 있으니, 열린 화면에서 한 번 확인하세요. 가격·잔여 객실은 그 화면이 기준입니다."),
      h("h4", {}, "항공편"), linkBtns(links.flights), h("h4", {}, "호텔"), linkBtns(links.hotels),
      h("div", { class: "row", style: "flex-wrap:wrap" },
        h("button", { class: "btn", onclick: () => askAi("flights") }, "항공편 후보 프롬프트 (AI 챗봇)"),
        h("button", { class: "btn", onclick: () => askAi("hotels") }, "호텔 후보 프롬프트 (AI 챗봇)")));

    const c = T.candidates;
    if (candTab === "flights" && !c.flights.length && c.hotels.length) candTab = "hotels";
    if (candTab === "hotels" && !c.hotels.length && c.flights.length) candTab = "flights";
    const clear = (kind) => confirmBox("후보 비우기", `${kind === "flights" ? "항공편" : "호텔"} 후보 ${c[kind].length}건을 목록에서 지울까요? (예약 기록은 지워지지 않아요)`, "비우기",
      () => put({ candidates: { ...c, [kind]: [] } }));
    const flightRows = c.flights.map((x) => h("div", { class: "row" }, h("div", { class: "grow" }, h("b", {}, `${x.flightNo} ${x.airline}`), h("div", { class: "sub" }, `${x.from}→${x.to} ${when(x.depart)}${x.arrive ? " → " + when(x.arrive) : ""} ${x.stops} ${x.price} ${x.note}`),
        ...(x.segments || []).map((g) => h("div", { class: "sub", style: "padding-left:12px" }, segText(g)))),
      x.sourceUrl ? h("a", { class: "btn sm", href: x.sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "출처") : null,
      h("button", { class: "btn sm", onclick: () => editFlight({ direction: "outbound", segments: x.segments?.length ? x.segments : [{ airline: x.airline, flightNo: x.flightNo, from: x.from, to: x.to, depart: x.depart, arrive: x.arrive }] }) }, "예약 기록으로")));
    const hotelRows = c.hotels.map((x) => h("div", { class: "row" }, h("div", { class: "grow" }, h("b", {}, `${x.name} ${x.stars ? x.stars + "성" : "등급 미확인"}`), h("div", { class: "sub" }, `${x.distance} · ${x.price} · ${x.cancellation} ${x.note}`)),
      x.sourceUrl ? h("a", { class: "btn sm", href: x.sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "출처") : null,
      h("button", { class: "btn sm", onclick: () => editHotel({ name: x.name, stars: x.stars, address: x.address, checkIn: links.dates.checkIn, checkOut: links.dates.checkOut }) }, "예약 기록으로")));
    const cand = c.flights.length || c.hotels.length ? h("div", { class: "card" }, h("h3", {}, "AI 후보 (가격·가용 여부는 사이트에서 확인)"),
      h("div", { class: "row", style: "flex-wrap:wrap" },
        ...[["flights", "항공편"], ["hotels", "호텔"]].map(([k, label]) => h("button", { class: "chip" + (candTab === k ? " on" : ""), onclick: () => { candTab = k; draw(); } }, `${label} ${c[k].length}`)),
        h("button", { class: "btn sm danger", style: "margin-left:auto;font-size:16px", disabled: !c[candTab].length, title: candTab === "flights" ? "항공편 후보 비우기" : "호텔 후보 비우기", "aria-label": candTab === "flights" ? "항공편 후보 비우기" : "호텔 후보 비우기", onclick: () => clear(candTab) }, "🗑")),
      ...(c[candTab].length ? (candTab === "flights" ? flightRows : hotelRows) : [h("div", { class: "sub" }, "이 목록은 비어 있어요. 위의 프롬프트 버튼으로 후보를 받아 보세요.")])) : null;

    const rec = h("div", { class: "card" }, h("h3", {}, "예약 기록"),
      h("div", { class: "row", style: "flex-wrap:wrap" }, h("button", { class: "btn primary", onclick: () => editFlight({ direction: "outbound" }) }, "+ 항공권"), h("button", { class: "btn primary", onclick: () => editHotel({ checkIn: links.dates.checkIn, checkOut: links.dates.checkOut }) }, "+ 숙소"),
        h("button", { class: "btn", onclick: fromMail }, "예약 확인서(스크린샷·메일)로 자동 정리")),
      T.flights.length || T.hotels.length ? null : h("div", { class: "sub" }, "아직 기록이 없어요. 예약을 마치면 직접 입력하거나, 확인 메일을 붙여 넣어 정리하세요."),
      ...T.flights.map((x) => h("div", { class: "row", style: "align-items:flex-start" }, h("span", { class: "pill gray" }, DIR[x.direction]),
        h("div", { class: "grow" },
          h("b", {}, x.route.join(" → ")), h("span", { class: "sub" }, x.segments.length > 1 ? `  경유 ${x.segments.length - 1}회` : "  직항"),
          h("div", { class: "sub" }, `예약번호 ${x.confirmation || "-"} · ${money(x) || "금액 미입력"}${x.note ? " · " + x.note : ""}`),
          ...x.segments.flatMap((g, i) => [
            h("div", { class: "sub", style: "color:var(--text,inherit)" }, segText(g)),
            x.layovers[i] ? h("div", { class: "sub", style: "padding-left:14px" }, `↳ ${x.layovers[i].at} 경유 ${span(x.layovers[i].minutes)}${x.layovers[i].airportChange ? ` (공항 변경 → ${x.layovers[i].to})` : ""}`) : null,
          ])),
        h("button", { class: "btn sm", onclick: () => editFlight(x) }, "편집"))),
      ...T.hotels.map((x) => h("div", { class: "row" }, h("span", { class: "pill gray" }, "숙소"), h("div", { class: "grow" }, h("b", {}, `${x.name} ${x.stars ? x.stars + "성" : ""}`), h("div", { class: "sub" }, `${x.checkIn} ~ ${x.checkOut} · 예약번호 ${x.confirmation || "-"} · ${money(x) || "금액 미입력"}${x.freeCancelUntil ? " · 무료취소 ~" + when(x.freeCancelUntil) : ""}`), x.address ? h("div", { class: "sub" }, x.address) : null),
        h("button", { class: "btn sm", onclick: () => editHotel(x) }, "편집"))),
      Object.keys(summary.totals).length ? h("div", { class: "msg" }, "합계: " + Object.entries(summary.totals).map(([k, v]) => `${v.toLocaleString()} ${k}`).join(" + ") + " (통화는 합치지 않았어요)") : null,
      summary.issues.length ? h("div", { class: "msg warn" }, h("ul", { style: "margin:0;padding-left:18px" }, ...summary.issues.map((i) => h("li", {}, i)))) : null);

    host.replaceChildren(settings, search, cand, rec);
  }

  function askAi(kind) {
    promptModal({
      title: kind === "flights" ? "항공편 후보 찾기 (AI 챗봇용)" : "호텔 후보 찾기 (AI 챗봇용)",
      intro: "Desk 가 AI를 직접 부르지는 않아요. 프롬프트를 AI 챗봇에 붙여 넣고(웹 검색 켜기), 답변을 아래에 붙여 넣으면 후보가 쌓여요.",
      getPrompts: async () => [(await api("POST", base + "/prompt", { kind })).prompt],
      onPaste: async (text) => { const r = await api("POST", base + "/paste", { kind, text }); await load(r); toast(`후보 ${r.pasted.added}건을 가져왔어요.`); },
    });
  }

  function fromMail() {
    const ta = h("textarea", { style: "min-height:110px", placeholder: "예약 확인 메일·문자 내용을 붙여 넣으세요 (여러 건 가능).\n스크린샷만 있으면 비워 두세요 — 이미지를 AI 챗봇에 직접 첨부하면 돼요." });
    promptModal({
      title: "예약 확인서 → 기록 (AI 챗봇용)", auto: false,
      intro: "① 아래에서 '프롬프트 만들기' → ② AI 챗봇에 프롬프트를 붙여 넣고, 예약 확인 화면 스크린샷을 함께 첨부(또는 메일 내용을 위 칸에 붙여 넣기) → ③ 챗봇의 답을 다시 붙여 넣으면 경유 구간까지 채워져요. 같은 예약은 중복으로 넣지 않아요. 승객 이름은 프롬프트가 적지 않도록 하지만, 걱정되면 스크린샷에서 가려서 올리세요.",
      extraTop: (ctl) => h("div", { style: "display:flex;flex-direction:column;gap:8px" }, ta, h("button", { class: "btn primary", onclick: ctl.load }, "프롬프트 만들기")),
      getPrompts: async () => [(await api("POST", base + "/prompt", { kind: "booking", text: ta.value })).prompt],
      onPaste: async (text) => { const r = await api("POST", base + "/paste", { kind: "booking", text }); await load(r); toast(`${r.pasted.added}건을 기록했어요` + (r.pasted.existing ? ` (이미 있던 ${r.pasted.existing}건 제외)` : "")); },
    });
  }

  const upsert = (key, item) => {
    const list = V.travel[key];
    const next = item.id && list.some((x) => x.id === item.id) ? list.map((x) => (x.id === item.id ? item : x)) : [...list, item];
    return put({ [key]: next });
  };
  const remove = (key, id) => put({ [key]: V.travel[key].filter((x) => x.id !== id) });

  function editFlight(x) {
    modal(x.id ? "항공권 편집" : "항공권 기록", (m, close) => {
      const e = {
        direction: h("select", {}, ...Object.entries(DIR).map(([k, v]) => h("option", { value: k }, v))),
        confirmation: h("input", { value: x.confirmation || "", placeholder: "예약번호(6자리)" }), amount: h("input", { type: "number", min: "0", step: "any", value: x.amount ?? "" }),
        currency: h("select", {}, ...["KRW", "EUR", "USD", "JPY", "GBP", "CNY"].map((c) => h("option", { value: c }, c))), note: h("input", { value: x.note || "" }),
      };
      e.direction.value = x.direction || "outbound"; e.currency.value = x.currency || "KRW";
      const segs = [];
      const box = h("div", { style: "display:flex;flex-direction:column;gap:8px" });
      const addSeg = (g) => {
        const c = {
          flightNo: h("input", { value: g.flightNo || "", placeholder: "LH713" }), airline: h("input", { value: g.airline || "" }),
          from: h("input", { value: g.from || "", placeholder: "ICN" }), fromTerm: h("input", { value: g.fromTerm || "", placeholder: "1" }),
          to: h("input", { value: g.to || "", placeholder: "FRA" }), toTerm: h("input", { value: g.toTerm || "", placeholder: "1" }),
          cabin: h("input", { value: g.cabin || "", placeholder: "예) W, 이코노미" }), baggage: h("input", { value: g.baggage || "", placeholder: "예) 1PC" }),
          ground: h("input", { type: "checkbox", checked: g.mode === "ground" }),
        };
        const dep = dtField(g.depart), arr = dtField(g.arrive);
        const rec = { g, c, dep, arr };
        const card = h("div", { class: "card", style: "padding:10px;margin:0" });
        rec.card = card;
        const paint = () => {
          const n = segs.indexOf(rec) + 1;
          card.replaceChildren(
            h("div", { class: "row", style: "justify-content:space-between;align-items:center" }, h("b", {}, segs.length > 1 ? `구간 ${n}` : "구간"),
              segs.length > 1 ? h("button", { class: "btn sm danger", onclick: () => { segs.splice(segs.indexOf(rec), 1); segs.forEach((r) => r.paint()); box.replaceChildren(...segs.map((r) => r.card)); } }, "구간 삭제") : h("span")),
            h("div", { class: "row" }, fld("편명", c.flightNo, 110), fld("항공사", c.airline), h("label", { class: "sub", style: "display:flex;gap:4px;align-items:center;align-self:flex-end;padding-bottom:8px" }, c.ground, "버스·기차")),
            h("div", { class: "row", style: "align-items:flex-end;flex-wrap:wrap" }, fld("출발지", c.from, 90), fld("터미널", c.fromTerm, 70), fld("출발 (현지, 24시간제)", dep.el)),
            h("div", { class: "row", style: "align-items:flex-end;flex-wrap:wrap" }, fld("도착지", c.to, 90), fld("터미널", c.toTerm, 70), fld("도착 (현지, 24시간제)", arr.el)),
            h("div", { class: "row" }, fld("좌석등급", c.cabin), fld("수하물", c.baggage)));
        };
        rec.paint = paint; segs.push(rec); segs.forEach((r) => r.paint()); box.replaceChildren(...segs.map((r) => r.card));
      };
      (x.segments?.length ? x.segments : [{}]).forEach(addSeg);
      const collect = () => segs.map(({ g, c, dep, arr }) => ({ ...g, flightNo: c.flightNo.value, airline: c.airline.value, from: c.from.value, to: c.to.value, fromTerm: c.fromTerm.value, toTerm: c.toTerm.value,
        cabin: c.cabin.value, baggage: c.baggage.value, mode: c.ground.checked ? "ground" : "air", depart: dep.get(), arrive: arr.get() }));
      m.append(h("div", { class: "row" }, fld("구분", e.direction, 120), fld("예약번호", e.confirmation), fld("금액", e.amount, 120), fld("통화", e.currency, 90)),
        h("div", { class: "sub" }, "경유는 구간을 하나씩 추가하세요. 몇 번 경유해도 같아요. 시각은 그 공항의 현지 시각이에요."),
        box, h("div", { class: "row" }, h("button", { class: "btn", onclick: () => { const last = segs[segs.length - 1]; const ld = last.arr.get(); addSeg({ from: last.c.to.value, depart: ld ? ld.slice(0, 10) : "", airline: last.c.airline.value }); } }, "+ 경유 구간 추가")),
        fld("메모", e.note),
        h("div", { class: "row", style: "justify-content:space-between" },
          x.id ? h("button", { class: "btn danger", onclick: () => confirmBox("기록 삭제", "이 항공권 기록을 지울까요?", "삭제", () => { close(); remove("flights", x.id); }, true) }, "삭제") : h("span"),
          h("button", { class: "btn primary", onclick: async () => {
            if (segs.some((r) => r.dep.bad() || r.arr.bad())) return toast("시각은 24시간제 HH:MM 으로 적어 주세요. (예: 18:40)", true);
            const list = collect();
            if (list.some((g) => !g.from.trim() || !g.to.trim())) return toast("모든 구간에 출발지와 도착지를 적어 주세요.", true);
            const item = { ...x, direction: e.direction.value, confirmation: e.confirmation.value, amount: e.amount.value, currency: e.currency.value, note: e.note.value, segments: list };
            delete item.route; delete item.layovers;
            if (await upsert("flights", item)) close();
          } }, "저장")));
    });
  }

  function editHotel(x) {
    modal(x.id ? "숙소 편집" : "숙소 기록", (m, close) => {
      const e = {
        name: h("input", { value: x.name || "" }), stars: h("select", {}, h("option", { value: 0 }, "모름"), ...[1, 2, 3, 4, 5].map((n) => h("option", { value: n }, `${n}성`))),
        address: h("input", { value: x.address || "" }), checkIn: h("input", { type: "date", value: x.checkIn || "" }), checkOut: h("input", { type: "date", value: x.checkOut || "" }),
        confirmation: h("input", { value: x.confirmation || "" }), amount: h("input", { type: "number", min: "0", step: "any", value: x.amount ?? "" }),
        currency: h("select", {}, ...["EUR", "KRW", "USD", "JPY", "GBP", "CNY"].map((c) => h("option", { value: c }, c))),
        freeCancelUntil: dtField(x.freeCancelUntil), site: h("input", { value: x.site || "", placeholder: "Agoda, Hotels.com …" }), note: h("textarea", { value: x.note || "" }),
      };
      e.stars.value = x.stars || 0; e.currency.value = x.currency || "EUR";
      m.append(h("div", { class: "row" }, fld("호텔명", e.name), fld("등급", e.stars, 100)), fld("주소", e.address),
        h("div", { class: "row" }, fld("체크인", e.checkIn), fld("체크아웃", e.checkOut)),
        h("div", { class: "row" }, fld("예약번호", e.confirmation), fld("총 금액", e.amount), fld("통화", e.currency, 100)),
        h("div", { class: "row" }, fld("무료 취소 기한 (24시간제)", e.freeCancelUntil.el), fld("예약 사이트", e.site)), fld("메모", e.note),
        h("div", { class: "row", style: "justify-content:space-between" },
          x.id ? h("button", { class: "btn danger", onclick: () => confirmBox("기록 삭제", "이 숙소 기록을 지울까요?", "삭제", () => { close(); remove("hotels", x.id); }, true) }, "삭제") : h("span"),
          h("button", { class: "btn primary", onclick: async () => { const item = { ...x, ...Object.fromEntries(Object.entries(e).map(([k, el]) => [k, k === "freeCancelUntil" ? el.get() : el.value])) }; if (e.freeCancelUntil.bad()) return toast("시각은 24시간제 HH:MM 으로 적어 주세요.", true); if (!item.name.trim()) return toast("호텔명을 입력해 주세요.", true); if (await upsert("hotels", item)) close(); } }, "저장")));
    });
  }

  load().catch((e) => host.replaceChildren(h("div", { class: "msg err" }, e.message)));
  return host;
}
