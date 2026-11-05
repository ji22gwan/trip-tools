// 홀 위치 지정: 대표 지도 위에서 홀마다 한 번씩 클릭해 위치를 정한다. 폰 지도에는 이 위치에 일자별로 표시된다.
import { h, api, toast, guard } from "./core.js";

let pdfjs = null;
async function loadPdf() {
  if (!pdfjs) {
    pdfjs = await import("./vendor/pdf.min.mjs");
    pdfjs.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;
  }
  return pdfjs;
}

export const hallKey = (s) => String(s || "").trim().toUpperCase().replace(/^(HALLE|HALL|홀)\s*/, "").replace(/\s+/g, "");

// 대표 지도를 페이지별 canvas/img 로 그린다 → [{el, width, height, texts}]
async function loadPages(url, isPdf) {
  if (!isPdf) {
    const img = new Image();
    img.src = url;
    await img.decode();
    return [{ el: img, width: img.naturalWidth, height: img.naturalHeight, texts: [] }];
  }
  const lib = await loadPdf();
  const doc = await lib.getDocument({ url }).promise;
  const out = [];
  for (let p = 1; p <= Math.min(doc.numPages, 12); p++) {
    const page = await doc.getPage(p);
    const base = page.getViewport({ scale: 1 });
    const vp = page.getViewport({ scale: Math.min(2400 / base.width, 3) });
    const cv = document.createElement("canvas");
    cv.width = Math.round(vp.width);
    cv.height = Math.round(vp.height);
    await page.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
    const tc = await page.getTextContent();
    const texts = tc.items.filter((it) => it.str && it.str.trim()).map((it) => {
      const [x, y] = lib.Util.applyTransform([it.transform[4], it.transform[5]], vp.transform);
      return { s: it.str.trim(), x: x / vp.width, y: (y - (it.height || 0) * vp.scale / 2) / vp.height };
    });
    out.push({ el: cv, width: cv.width, height: cv.height, texts });
  }
  return out;
}

// 지도 글자 중 홀 이름처럼 보이는 것만 (예: "3A", "Halle 7", "Hall 10.1")
export function detectHalls(pages, wanted) {
  const found = {};
  const want = new Set(wanted);
  pages.forEach((pg, pi) => pg.texts.forEach((t) => {
    const m = /^(?:HALLE?\s*)?(\d{1,2}(?:\.\d)?[A-C]?)$/i.exec(t.s);
    const key = m && hallKey(m[1]);
    if (key && want.has(key) && !found[key]) found[key] = { x: t.x, y: t.y, page: pi };
  }));
  return found;
}

export async function pinsPanel(P, redraw) {
  const { trip, maps, companies } = P.v;
  const primary = maps.find((m) => m.primary) || maps[0];
  const card = h("div", { class: "card" }, h("h3", {}, "홀 위치 지정"));
  if (!primary) return null;
  const picked = companies.filter((c) => c.picked !== false).flatMap((c) => (c.booths?.length ? c.booths : [c])).filter((b) => hallKey(b.hall)); // 부스 단위
  const halls = [...new Set(picked.map((c) => hallKey(c.hall)))].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  if (!halls.length) {
    card.append(h("div", { class: "msg" }, "업체에 홀 정보가 아직 없어요. 홀이 정해지면 여기서 지도 위 위치를 찍을 수 있어요."));
    return card;
  }
  const pins = { ...(trip.hallPins || {}) };
  let sel = halls.find((k) => !pins[k]) || halls[0];
  let dayFilter = 0;
  const isPdf = primary.name.toLowerCase().endsWith(".pdf");
  const url = `/api/trips/${P.tid}/maps/${encodeURIComponent(primary.name)}`;
  const status = h("div", { class: "sub" }, "지도를 불러오는 중…");
  const box = h("div", { style: "position:relative;overflow:auto;max-height:560px;border:1px solid var(--line);border-radius:10px;background:#eef1f4" });
  const list = h("div", { class: "chips" });
  const dayRow = h("div", { class: "chips" });
  const delBtn = h("button", { class: "btn", onclick: () => { delete pins[sel]; paint(); } }, "");
  card.append(h("div", { class: "msg" }, `'${primary.name}' 위에서 홀마다 한 번씩 클릭하세요. 폰 지도에는 이 위치에 그날 방문할 업체 수가 표시돼요. 홀 이름: 선택된 업체 기준 ${halls.length}곳.`), dayRow, list, status, box);
  let pages = [];
  let page = 0;
  const wrap = h("div", { style: "position:relative;display:block;cursor:crosshair" });

  const dayCount = (key) => picked.filter((c) => hallKey(c.hall) === key && (!dayFilter || c.day === dayFilter)).length;
  const paint = () => {
    delBtn.textContent = `${sel} 위치 지우기`; // 선택한 홀이 바뀔 때마다 이름을 갱신한다
    delBtn.disabled = !pins[sel];
    status.textContent = `${Object.keys(pins).filter((k) => halls.includes(k)).length}/${halls.length}곳 지정됨 · 지금 찍을 홀: ${sel}`;
    list.replaceChildren(...halls.map((k) => h("button", { class: "chip" + (k === sel ? " on" : ""), onclick: () => { sel = k; paint(); } },
      `${pins[k] ? "📍" : "·"} ${k} (${dayCount(k) || picked.filter((c) => hallKey(c.hall) === k).length})`)));
    dayRow.replaceChildren(h("span", { class: "sub" }, "보기:"), ...[0, ...trip.days.map((_, i) => i + 1)].map((d) =>
      h("button", { class: "chip" + (d === dayFilter ? " on" : ""), onclick: () => { dayFilter = d; paint(); } }, d ? `Day ${d}` : "전체")));
    wrap.querySelectorAll(".hp").forEach((n) => n.remove());
    Object.entries(pins).filter(([, p]) => p.page === page).forEach(([k, p]) => {
      const n = dayCount(k);
      if (dayFilter && !n) return;
      wrap.append(h("div", { class: "hp" + (k === sel ? " sel" : ""), style: `left:${p.x * 100}%;top:${p.y * 100}%`, title: k }, h("b", {}, k), n ? h("i", {}, String(n)) : null));
    });
  };
  const save = () => guard(async () => { P.v = await api("PUT", `/trips/${P.tid}/hall-pins`, pins); toast("홀 위치를 저장했어요."); P.app.refreshSide?.(); });

  try {
    pages = await loadPages(url, isPdf);
    const show = () => {
      const pg = pages[page];
      pg.el.style.cssText = "display:block;width:100%;height:auto";
      wrap.replaceChildren(pg.el);
      paint();
    };
    wrap.addEventListener("click", (e) => {
      if (e.target.closest(".hp")) { sel = e.target.closest(".hp").title; return paint(); }
      const r = pages[page].el.getBoundingClientRect();
      pins[sel] = { x: +((e.clientX - r.left) / r.width).toFixed(4), y: +((e.clientY - r.top) / r.height).toFixed(4), page };
      sel = halls.find((k) => !pins[k]) || sel;
      paint();
    });
    box.append(wrap);
    show();
    const pager = pages.length > 1 ? h("div", { class: "row" }, ...pages.map((_, i) => h("button", { class: "btn sm" + (i === page ? " primary" : ""), onclick: () => { page = i; show(); } }, `${i + 1}쪽`))) : null;
    const auto = h("button", { class: "btn", onclick: () => {
      const todo = halls.filter((k) => !pins[k]);
      if (!todo.length) return toast("모든 홀의 위치가 이미 지정돼 있어요. 바꾸려면 지도를 다시 클릭하세요.");
      const f = detectHalls(pages, todo);
      const n = Object.keys(f).length;
      Object.assign(pins, f);
      paint();
      toast(n ? `지도 글자에서 ${n}곳을 찾았어요. 위치가 맞는지 확인하고 저장하세요.` : "지도에서 홀 이름 글자를 찾지 못했어요. 직접 클릭해 주세요.", !n);
    } }, "지도 글자에서 자동 찾기");
    card.append(h("div", { class: "row" }, auto,
      delBtn,
      h("button", { class: "btn primary", onclick: save }, "저장")), pager);
  } catch (e) {
    status.textContent = "지도를 화면에 그리지 못했어요: " + (e.message || e);
  }
  return card;
}
