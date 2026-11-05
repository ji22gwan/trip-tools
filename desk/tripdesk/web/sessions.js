// 세션·행사 탭: 전시회 기간의 세미나·컨퍼런스·토론회. AI 챗봇으로 공식 프로그램을 조사해 붙여 넣고, 갈 것을 골라 패키지(폰)로 보낸다.
import { h, api, toast, guard, modal, confirmBox, promptModal } from "./core.js";

const fmtDay = (d) => `${Number(d.slice(5, 7))}월 ${Number(d.slice(8, 10))}일`;
const time = (s) => (s.start ? s.start + (s.end ? "~" + s.end : "") : "시간 미정");

export function sessionsTab(P, redraw) {
  const list = P.v.sessions || [];
  const save = async (next) => { P.v = await api("PUT", `/trips/${P.tid}/sessions`, next); redraw(); P.app.refreshSide(); };
  const picked = list.filter((s) => s.picked).length;
  const conflicts = (P.v.warnings || []).filter((w) => w.includes("시간이 겹쳐요"));

  const openPrompt = () => promptModal({
    title: "세미나·컨퍼런스 찾기 (AI 챗봇용)",
    intro: "공식 프로그램(일정표) 페이지를 조사하게 하는 프롬프트예요. 웹 검색이 되는 AI 챗봇에 붙여 넣고, 답을 아래 칸에 붙여 넣으세요. 공식 사이트에서 확인한 것만 받도록 되어 있어요. 이미 목록에 있는 세션은 제외돼요.",
    getPrompts: async () => [(await api("POST", `/trips/${P.tid}/prompt/sessions`, {})).prompt],
    onPaste: async (text) => {
      const r = await api("POST", `/trips/${P.tid}/paste/sessions`, { text });
      P.v = r; redraw(); P.app.refreshSide();
      const p = r.pasted;
      toast(`세션 ${p.added}개를 추가했어요` + (p.existing ? ` (이미 있던 ${p.existing}개 제외)` : "") + (p.outside ? ` · 전시 기간 밖 ${p.outside}개 제외` : "") + (p.unverified ? ` · 확인 못 한 ${p.unverified}개` : ""));
      if (p.notes) toast("AI 메모: " + p.notes);
    },
  });

  const editor = (s) => modal(s ? "세션 편집" : "세션 직접 추가", (m, close) => {
    const days = P.v.trip.days;
    const f = {
      title: h("input", { value: s?.title || "" }),
      date: h("select", {}, ...days.map((d) => h("option", { value: d, selected: (s?.date || days[0]) === d }, fmtDay(d)))),
      start: h("input", { type: "time", value: s?.start || "" }), end: h("input", { type: "time", value: s?.end || "" }),
      place: h("input", { value: s?.place || "", placeholder: "예) Forum Stage" }), hall: h("input", { value: s?.hall || "", placeholder: "3A" }),
      speaker: h("input", { value: s?.speaker || "" }), topic: h("textarea", { value: s?.topic || "", style: "min-height:70px" }),
    };
    const fld = (l, el) => h("div", { class: "field" }, h("label", {}, l), el);
    m.append(fld("제목", f.title), h("div", { class: "row" }, h("div", { class: "grow" }, fld("날짜", f.date)), h("div", { class: "grow" }, fld("시작", f.start)), h("div", { class: "grow" }, fld("끝", f.end))),
      h("div", { class: "row" }, h("div", { class: "grow" }, fld("장소(무대·룸)", f.place)), h("div", { style: "width:100px" }, fld("홀", f.hall))), fld("연사", f.speaker), fld("주제·메모", f.topic));
    if (s?.sourceUrl) m.append(h("div", { class: "msg" }, "출처: ", h("a", { href: s.sourceUrl, target: "_blank", rel: "noopener" }, s.sourceUrl)));
    m.append(h("div", { class: "row", style: "justify-content:space-between" },
      s ? h("button", { class: "btn danger", onclick: () => confirmBox("세션 삭제", `'${s.title}' 을(를) 지울까요?`, "삭제", () => guard(() => save(list.filter((x) => x.id !== s.id))), true) }, "삭제") : h("span"),
      h("button", { class: "btn primary", onclick: () => {
        if (!f.title.value.trim()) return toast("제목을 적어 주세요.", true);
        const next = { ...(s || { source: "manual", picked: true }), title: f.title.value, date: f.date.value, start: f.start.value, end: f.end.value, place: f.place.value, hall: f.hall.value, speaker: f.speaker.value, topic: f.topic.value };
        close(); guard(() => save(s ? list.map((x) => (x.id === s.id ? next : x)) : [...list, next]));
      } }, "저장")));
  });

  const row = (s) => h("div", { class: "crow", style: "display:flex;gap:10px;align-items:flex-start;padding:8px 4px;border-top:1px solid var(--line2)" },
    h("button", { class: "cb" + (s.picked ? " on" : ""), role: "checkbox", "aria-checked": String(!!s.picked), "aria-label": s.title + " 선택", onclick: () => guard(() => save(list.map((x) => (x.id === s.id ? { ...x, picked: !s.picked } : x)))) }, s.picked ? "✓" : ""),
    h("div", { style: "width:92px;font-weight:800;font-size:13px;flex:none" }, time(s)),
    h("div", { class: "grow" },
      h("div", { style: "font-weight:700" }, s.title, " ", s.verified ? h("span", { class: "tag green" }, "공식 확인") : (s.source === "ai" ? h("span", { class: "tag" }, "AI 추정") : null)),
      h("div", { class: "sub" }, [s.place, s.hall && "홀 " + s.hall, s.speaker].filter(Boolean).join(" · ") || "장소 미정"),
      s.topic ? h("div", { class: "sub" }, s.topic) : null,
      s.sourceUrl ? h("a", { class: "sub", href: s.sourceUrl, target: "_blank", rel: "noopener" }, "출처") : null),
    h("button", { class: "btn sm ghost", "aria-label": s.title + " 편집", onclick: () => editor(s), style: "padding:0" }, "✎"));

  const dates = [...new Set(list.map((s) => s.date))].sort();
  return h("div", { class: "pad" },
    h("div", { class: "row", style: "justify-content:space-between;margin-bottom:8px" },
      h("div", { class: "sub" }, `세미나·컨퍼런스·토론회 ${list.length}개 · 폰으로 보낼 것 ${picked}개`),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: openPrompt }, "AI 프롬프트 만들기"), h("button", { class: "btn", onclick: () => editor(null) }, "+ 직접 추가"))),
    conflicts.length ? h("div", { class: "msg warn" }, h("b", {}, "시간이 겹치는 세션"), h("ul", { style: "margin:4px 0 0;padding-left:18px" }, ...conflicts.map((w) => h("li", {}, w)))) : null,
    list.length ? h("div", {}, ...dates.map((d) => h("div", { style: "margin-bottom:14px" }, h("h4", { style: "margin:6px 0" }, fmtDay(d), h("span", { class: "sub" }, `  ${list.filter((s) => s.date === d).length}개`)), ...list.filter((s) => s.date === d).map(row))))
      : h("div", { class: "empty" }, h("b", {}, "아직 세션이 없어요"), h("div", {}, "공식 프로그램 페이지는 AI 챗봇으로 조사하고, 빠진 건 직접 추가하세요. 일정표 페이지가 동적이면 놓치는 항목이 있을 수 있어요.")));
}
