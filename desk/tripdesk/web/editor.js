// 최종 보고서 편집기: PPT 슬라이드 구성(핵심/비교 업체, 사진, 시사점, 후속 과제)을 템플릿처럼 채우고 저장한다.
import { h, api, toast, guard, download } from "./core.js";

const lines = (t) => t.value.split("\n").map((x) => x.trim()).filter(Boolean);
const TIER = [["", "자동"], ["core", "핵심 고정"], ["brief", "비교(2개씩)"], ["hide", "보고서에서 제외"]];
const AUTO = { core: "핵심", brief: "비교", thin: "자료 부족" };

export function openReportEditor(root, tid, r, close) {
  const pp = r.ppt;
  const fld = (l, e) => h("div", { class: "field" }, h("label", {}, l), e);
  const ta = (v, min = 60) => h("textarea", { value: v, style: `min-height:${min}px` });
  const att = h("input", { value: pp.attendees, placeholder: "예: 홍길동 책임, 김철수 선임" });
  const rem = h("input", { value: pp.remark });
  const fair = {};
  for (const [k, l] of [["name", "명칭"], ["summary", "개요"], ["scale", "규모"], ["halls", "전시관 구성"], ["slogan", "슬로건"]]) fair[k] = [l, k === "name" ? h("input", { value: pp.fair.name }) : ta(pp.fair[k].join("\n"), 48)];

  // ---- 업체 카드 ----
  const cards = r.companies.map((c) => {
    const cur = pp.companies[c.id] || {};
    const photos = c.visits.flatMap((v) => v.photoFiles || []);
    let sel = (cur.photos || []).map((x) => ({ ...x }));
    const key = (p) => p.day + "/" + p.file;
    const strip = h("div", { class: "edstrip" });
    const paint = () => strip.replaceChildren(...photos.map((p) => {
      const i = sel.findIndex((x) => key(x) === key(p));
      return h("div", { class: "edph" + (i >= 0 ? " on" : ""), onclick: () => { if (i >= 0) sel.splice(i, 1); else if (sel.length < 8) sel.push({ day: p.day, file: p.file }); paint(); } },
        h("img", { loading: "lazy", alt: "", src: `/api/trips/${tid}/days/${p.day}/file/` + p.file.split("/").map(encodeURIComponent).join("/") }), i >= 0 ? h("b", {}, i === 0 ? "대표" : String(i + 1)) : null);
    }));
    paint();
    const f = {
      short: h("input", { value: cur.short || "", placeholder: c.name }), group: h("input", { value: cur.group || c.category || "" }),
      tier: h("select", {}, ...TIER.map(([v, t]) => h("option", { value: v, selected: (cur.tier || "") === v }, v === "" ? `자동 (${AUTO[r.tiers[c.id]] || "-"})` : t))),
      level: h("select", {}, ...[["", "수준 미정"], ["1", "1 단기 적용"], ["2", "2 추가 검증"], ["3", "3 중·장기"]].map(([v, t]) => h("option", { value: v, selected: String(cur.level || "") === v }, t))),
      check: h("input", { value: cur.check || "", placeholder: "표에 들어갈 확인 사항 1~2문장" }),
      summary: ta((cur.summary && cur.summary.length ? cur.summary : c.visits.flatMap((v) => v.points)).join("\n"), 80), apply: ta((cur.apply || []).join("\n"), 60),
      diff: h("input", { value: cur.diff || "", placeholder: "기존 기술 대비 달라 보이는 점" }),
    };
    const el = h("div", { class: "edco" },
      h("div", { class: "row", style: "gap:8px;flex-wrap:wrap" }, h("b", {}, c.name), f.short, f.group, f.tier, f.level),
      f.check, fld("기술 요약 (한 줄에 하나, 비우면 현장 개조식 사용)", f.summary), fld("당사 적용 및 시사점", f.apply), f.diff,
      photos.length ? h("div", {}, h("div", { class: "sub" }, `사진 ${photos.length}장 — 클릭한 순서대로 배치돼요(첫 번째가 대표·크게)`), strip) : null);
    return { c, f, el, sel: () => sel };
  });

  // ---- 시사점 / 결론 / 후속 ----
  const blocks = (title, arr, max) => {
    const wrap = h("div", {});
    const rows = [];
    const add = (b = { title: "", points: [] }) => {
      const t = h("input", { value: b.title, placeholder: "제목" }), p = ta(b.points.join("\n"), 56);
      const row = { t, p, el: h("div", { class: "edco" }, t, p, h("button", { class: "btn sm ghost", onclick: () => { rows.splice(rows.indexOf(row), 1); row.el.remove(); } }, "삭제")) };
      rows.push(row); wrap.append(row.el);
    };
    arr.forEach(add);
    return { el: h("div", {}, h("h4", {}, title), wrap, h("button", { class: "btn sm", onclick: () => rows.length < max && add() }, "+ 추가")), get: () => rows.map((x) => ({ title: x.t.value, points: lines(x.p) })).filter((b) => b.title || b.points.length) };
  };
  const ins = blocks("시사점 (4개 권장)", pp.insights, 4), con = blocks("결론 (3개 권장)", pp.conclusions, 3);
  const fuWrap = h("div", {}), fus = [];
  const addFu = (x = { term: "단기", title: "", detail: "" }) => {
    const term = h("select", {}, ...["단기", "중기", "장기"].map((v) => h("option", { value: v, selected: x.term === v }, v))), title = h("input", { value: x.title, placeholder: "과제" }), detail = h("input", { value: x.detail, placeholder: "비교·측정할 내용, 대상 업체" });
    const row = { term, title, detail, el: h("div", { class: "row", style: "gap:6px;margin-bottom:4px" }, term, title, detail, h("button", { class: "btn sm ghost", onclick: () => { fus.splice(fus.indexOf(row), 1); row.el.remove(); } }, "삭제")) };
    fus.push(row); fuWrap.append(row.el);
  };
  (pp.followups || []).forEach(addFu);

  const payload = () => {
    const companies = {};
    for (const x of cards) companies[x.c.id] = { short: x.f.short.value, group: x.f.group.value, tier: x.f.tier.value, level: x.f.level.value || null, check: x.f.check.value, summary: lines(x.f.summary), apply: lines(x.f.apply), diff: x.f.diff.value, photos: x.sel() };
    return { attendees: att.value, remark: rem.value, companies, insights: ins.get(), conclusions: con.get(),
      followups: fus.map((x) => ({ term: x.term.value, title: x.title.value, detail: x.detail.value })),
      fair: Object.fromEntries(Object.entries(fair).map(([k, [, e]]) => [k, e.value])) };
  };
  const save = () => guard(async () => { await api("PUT", `/trips/${tid}/final/ppt`, payload()); toast("저장했어요."); });

  const byCat = {};
  for (const x of cards) (byCat[x.f.group.value || "기타"] ||= []).push(x);
  root.replaceChildren(
    h("div", { class: "top" }, h("div", { class: "row", style: "gap:14px" }, h("h1", {}, "보고서 편집기"), h("span", { class: "pill" }, "저장 후 Markdown 을 AI 에 주면 PPT 로 바뀌어요")),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: close }, "← 최종 보고서"), h("button", { class: "btn", onclick: save }, "저장"),
        h("button", { class: "btn primary", onclick: () => guard(async () => { await api("PUT", `/trips/${tid}/final/ppt`, payload()); download(`/trips/${tid}/final-ppt.zip`); }) }, "저장하고 Markdown + 사진 받기"))),
    h("div", { class: "card" }, h("h3", {}, "기본 정보 · 박람회 개요"), fld("출장자", att), fld("비고", rem), ...Object.values(fair).map(([l, e]) => fld(l, e))),
    h("div", { class: "card" }, h("h3", {}, "업체 (카테고리별)"), h("div", { class: "sub" }, "핵심 업체는 1페이지에 크게, 비교 업체는 2개씩 묶여요. '자동'은 현장 정보량으로 판정한 값이에요."),
      ...Object.entries(byCat).map(([g, xs]) => h("div", {}, h("h4", {}, `${g} (${xs.length})`), ...xs.map((x) => x.el)))),
    h("div", { class: "card" }, h("h3", {}, "종합 시사점 · 결론"), ins.el, con.el),
    h("div", { class: "card" }, h("h3", {}, "후속 추진 방향 (단기·중기·장기)"), fuWrap, h("button", { class: "btn sm", onclick: () => fus.length < 6 && addFu() }, "+ 과제 추가")),
  );
  window.scrollTo(0, 0);
}
