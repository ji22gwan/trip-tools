// 항공·숙소 탭: 검색 바로가기, AI 챗봇 후보 찾기, 예약 기록
import { h, api, toast, guard, modal, confirmBox, promptModal } from "./core.js";

const DIR = { outbound: "가는 편", return: "오는 편", other: "기타" };
const money = (x) => (x.amount == null ? "" : `${Number(x.amount).toLocaleString()} ${x.currency}`);
const fld = (l, el, w) => h("div", { class: "field", style: w ? `width:${w}px` : "flex:1;min-width:140px" }, h("label", {}, l), el);

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
    const flightRows = c.flights.map((x) => h("div", { class: "row" }, h("div", { class: "grow" }, h("b", {}, `${x.flightNo} ${x.airline}`), h("div", { class: "sub" }, `${x.from}→${x.to} ${x.depart.replace("T", " ")} ${x.stops} ${x.price} ${x.note}`)),
      x.sourceUrl ? h("a", { class: "btn sm", href: x.sourceUrl, target: "_blank", rel: "noopener noreferrer" }, "출처") : null,
      h("button", { class: "btn sm", onclick: () => editFlight({ direction: "outbound", airline: x.airline, flightNo: x.flightNo, from: x.from, to: x.to, depart: x.depart, arrive: x.arrive }) }, "예약 기록으로")));
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
        h("button", { class: "btn", onclick: fromMail }, "예약 메일로 자동 정리 (AI 챗봇)")),
      T.flights.length || T.hotels.length ? null : h("div", { class: "sub" }, "아직 기록이 없어요. 예약을 마치면 직접 입력하거나, 확인 메일을 붙여 넣어 정리하세요."),
      ...T.flights.map((x) => h("div", { class: "row" }, h("span", { class: "pill gray" }, DIR[x.direction]), h("div", { class: "grow" }, h("b", {}, `${x.flightNo} ${x.airline}`.trim() || "항공권"), h("div", { class: "sub" }, `${x.from}→${x.to} · ${x.depart.replace("T", " ")}${x.arrive ? " → " + x.arrive.replace("T", " ") : ""} · 예약번호 ${x.confirmation || "-"} · ${money(x) || "금액 미입력"}`)),
        h("button", { class: "btn sm", onclick: () => editFlight(x) }, "편집"))),
      ...T.hotels.map((x) => h("div", { class: "row" }, h("span", { class: "pill gray" }, "숙소"), h("div", { class: "grow" }, h("b", {}, `${x.name} ${x.stars ? x.stars + "성" : ""}`), h("div", { class: "sub" }, `${x.checkIn} ~ ${x.checkOut} · 예약번호 ${x.confirmation || "-"} · ${money(x) || "금액 미입력"}${x.freeCancelUntil ? " · 무료취소 ~" + x.freeCancelUntil.replace("T", " ") : ""}`), x.address ? h("div", { class: "sub" }, x.address) : null),
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
    const ta = h("textarea", { style: "min-height:140px", placeholder: "항공권·호텔 예약 확인 메일 본문을 그대로 붙여 넣으세요 (여러 건 가능)" });
    promptModal({
      title: "예약 확인 메일 → 기록 (AI 챗봇용)", auto: false,
      intro: "메일 내용을 붙여 넣고 프롬프트를 만든 뒤, AI 챗봇의 답을 다시 붙여 넣으면 항공·숙소 기록이 채워져요. 같은 예약은 중복으로 넣지 않아요. 개인정보가 담긴 메일은 필요한 부분만 붙여 넣으세요.",
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
        airline: h("input", { value: x.airline || "" }), flightNo: h("input", { value: x.flightNo || "", placeholder: "LH713" }),
        from: h("input", { value: x.from || "" }), to: h("input", { value: x.to || "" }),
        depart: h("input", { type: "datetime-local", value: x.depart || "" }), arrive: h("input", { type: "datetime-local", value: x.arrive || "" }),
        confirmation: h("input", { value: x.confirmation || "" }), amount: h("input", { type: "number", min: "0", step: "any", value: x.amount ?? "" }),
        currency: h("select", {}, ...["KRW", "EUR", "USD", "JPY", "GBP", "CNY"].map((c) => h("option", { value: c }, c))),
        baggage: h("input", { value: x.baggage || "" }), note: h("textarea", { value: x.note || "" }),
      };
      e.direction.value = x.direction || "outbound"; e.currency.value = x.currency || "KRW";
      m.append(h("div", { class: "row" }, fld("구분", e.direction, 120), fld("항공사", e.airline), fld("편명", e.flightNo, 120)),
        h("div", { class: "row" }, fld("출발지", e.from), fld("도착지", e.to)),
        h("div", { class: "row" }, fld("출발(현지 시각)", e.depart), fld("도착(현지 시각)", e.arrive)),
        h("div", { class: "row" }, fld("예약번호", e.confirmation), fld("금액", e.amount), fld("통화", e.currency, 100)), fld("수하물", e.baggage), fld("메모", e.note),
        h("div", { class: "row", style: "justify-content:space-between" },
          x.id ? h("button", { class: "btn danger", onclick: () => confirmBox("기록 삭제", "이 항공권 기록을 지울까요?", "삭제", () => { close(); remove("flights", x.id); }, true) }, "삭제") : h("span"),
          h("button", { class: "btn primary", onclick: async () => { const item = { ...x, ...Object.fromEntries(Object.entries(e).map(([k, el]) => [k, el.value])) }; if (await upsert("flights", item)) close(); } }, "저장")));
    });
  }

  function editHotel(x) {
    modal(x.id ? "숙소 편집" : "숙소 기록", (m, close) => {
      const e = {
        name: h("input", { value: x.name || "" }), stars: h("select", {}, h("option", { value: 0 }, "모름"), ...[1, 2, 3, 4, 5].map((n) => h("option", { value: n }, `${n}성`))),
        address: h("input", { value: x.address || "" }), checkIn: h("input", { type: "date", value: x.checkIn || "" }), checkOut: h("input", { type: "date", value: x.checkOut || "" }),
        confirmation: h("input", { value: x.confirmation || "" }), amount: h("input", { type: "number", min: "0", step: "any", value: x.amount ?? "" }),
        currency: h("select", {}, ...["EUR", "KRW", "USD", "JPY", "GBP", "CNY"].map((c) => h("option", { value: c }, c))),
        freeCancelUntil: h("input", { type: "datetime-local", value: x.freeCancelUntil || "" }), site: h("input", { value: x.site || "", placeholder: "Agoda, Hotels.com …" }), note: h("textarea", { value: x.note || "" }),
      };
      e.stars.value = x.stars || 0; e.currency.value = x.currency || "EUR";
      m.append(h("div", { class: "row" }, fld("호텔명", e.name), fld("등급", e.stars, 100)), fld("주소", e.address),
        h("div", { class: "row" }, fld("체크인", e.checkIn), fld("체크아웃", e.checkOut)),
        h("div", { class: "row" }, fld("예약번호", e.confirmation), fld("총 금액", e.amount), fld("통화", e.currency, 100)),
        h("div", { class: "row" }, fld("무료 취소 기한", e.freeCancelUntil), fld("예약 사이트", e.site)), fld("메모", e.note),
        h("div", { class: "row", style: "justify-content:space-between" },
          x.id ? h("button", { class: "btn danger", onclick: () => confirmBox("기록 삭제", "이 숙소 기록을 지울까요?", "삭제", () => { close(); remove("hotels", x.id); }, true) }, "삭제") : h("span"),
          h("button", { class: "btn primary", onclick: async () => { const item = { ...x, ...Object.fromEntries(Object.entries(e).map(([k, el]) => [k, el.value])) }; if (!item.name.trim()) return toast("호텔명을 입력해 주세요.", true); if (await upsert("hotels", item)) close(); } }, "저장")));
    });
  }

  load().catch((e) => host.replaceChildren(h("div", { class: "msg err" }, e.message)));
  return host;
}
