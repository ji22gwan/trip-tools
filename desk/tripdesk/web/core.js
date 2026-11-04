// 공통 도구: DOM 만들기, API 호출, 알림, 모달. 사용자·AI 가 쓴 글은 textContent 로만 넣어 스크립트가 실행되지 않게 한다.
// append/replaceChildren 에 null·false 가 들어와도 글자 'null' 이 찍히지 않게 한다
for (const m of ["append", "prepend", "replaceChildren"]) {
  const orig = Element.prototype[m];
  Element.prototype[m] = function (...a) { return orig.apply(this, a.filter((x) => x != null && x !== false)); };
}

export const h = (tag, props, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (k === "checked") e.checked = !!v;
    else if (k === "disabled") e.disabled = !!v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(9)) {
    if (kid == null || kid === false) continue;
    e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return e;
};

export async function api(method, path, body, opts = {}) {
  const init = { method, headers: { "X-TripDesk": "1" } };
  if (body !== undefined) init.body = opts.raw ? body : JSON.stringify(body);
  const r = await fetch("/api" + path, init);
  if (opts.blob && r.ok) return r.blob();
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "오류 " + r.status);
  return j;
}

export function toast(msg, err = false) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}

export async function guard(fn) {
  try {
    return await fn();
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

export function modal(title, build) {
  const bg = h("div", { class: "modalbg", onclick: (e) => e.target === bg && close() });
  const body = h("div", { class: "modal", role: "dialog", "aria-label": title });
  const close = () => bg.remove();
  body.append(h("div", { class: "row" }, h("h2", { class: "grow" }, title), h("button", { class: "btn sm ghost", onclick: close, "aria-label": "닫기" }, "✕")));
  build(body, close);
  bg.append(body);
  document.body.append(bg);
  return close;
}

export function confirmBox(title, text, okLabel, onOk, danger = false) {
  modal(title, (m, close) => {
    m.append(h("p", { style: "margin:0;line-height:1.6" }, text));
    m.append(h("div", { class: "row", style: "justify-content:flex-end" },
      h("button", { class: "btn", onclick: close }, "취소"),
      h("button", { class: "btn primary" + (danger ? " danger" : ""), style: danger ? "background:#B42318;border-color:#B42318;color:#fff" : "", onclick: async () => { close(); await onOk(); } }, okLabel)));
  });
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("복사했어요.");
  } catch {
    const ta = h("textarea", { style: "position:fixed;opacity:0" }, text);
    document.body.append(ta);
    ta.select();
    const ok = document.execCommand?.("copy");
    ta.remove();
    toast(ok ? "복사했어요." : "복사하지 못했어요. 글을 직접 선택해서 복사해 주세요.", !ok);
  }
}

// 교정 표시: {{고친 부분}} 은 파랗게, [확인필요: …] 는 주황으로.
export function marked(text) {
  const out = [];
  let last = 0;
  const re = /\{\{(.*?)\}\}|\[확인필요[^\]]*\]/gs;
  for (const m of String(text || "").matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[1] !== undefined ? h("span", { class: "hl" }, m[1]) : h("span", { class: "ck" }, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(String(text).slice(last));
  return out;
}

export function download(path) {
  const a = h("a", { href: "/api" + path });
  document.body.append(a);
  a.click();
  a.remove();
}

export const fmtDur = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
export const fmtDate = (d) => (d ? `${Number(d.slice(5, 7))}월 ${Number(d.slice(8, 10))}일` : "");
export const hm = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

// 프롬프트를 보여 주고 복사하게 한 뒤, AI 의 답을 붙여 넣게 하는 공통 창
export function promptModal({ title, intro, getPrompts, onPaste, extraTop, pasteHint, auto = true }) {
  modal(title, (m, close) => {
    if (intro) m.append(h("div", { class: "msg" }, intro));
    m.append(h("div", { class: "sub" }, "Claude, ChatGPT, Gemini 등 어떤 AI 챗봇이든 쓸 수 있어요. 웹 검색을 켜면 결과가 더 정확해요."));
    const slot = h("div", { style: "display:flex;flex-direction:column;gap:14px" });
    m.append(slot);
    let parts = [];
    const paste = h("textarea", { placeholder: pasteHint || "AI 의 답변 전체를 여기에 붙여 넣으세요.", style: "min-height:130px" });
    const mode = { n: 0 };
    const render = (prompts) => {
      parts = prompts;
      slot.replaceChildren(
        h("div", { class: "stepn" }, h("i", {}, "1"), h("div", { class: "grow", style: "display:flex;flex-direction:column;gap:8px" },
          h("b", {}, prompts.length > 1 ? `아래 ${prompts.length}개 프롬프트를 AI 챗봇에 차례로 붙여 넣으세요 (각각 답을 받아 2번에 붙여 넣기)` : "아래 프롬프트를 복사해 AI 챗봇에 붙여 넣으세요 (웹 검색을 켠 채로)"),
          ...prompts.map((p, i) => h("div", { style: "display:flex;flex-direction:column;gap:6px" },
            h("pre", {}, p),
            h("div", { class: "row" }, h("button", { class: "btn sm primary", onclick: () => copyText(p) }, prompts.length > 1 ? `프롬프트 ${i + 1} 복사` : "프롬프트 복사"),
              h("span", { class: "sub" }, `${p.length.toLocaleString()}자`)))))),
        h("div", { class: "stepn" }, h("i", {}, "2"), h("div", { class: "grow", style: "display:flex;flex-direction:column;gap:8px" },
          h("b", {}, "AI 가 준 답변 전체를 붙여 넣고 '가져오기'"), paste,
          h("div", { class: "row" }, h("button", { class: "btn primary", onclick: async () => {
            const ok = await guard(async () => { await onPaste(paste.value, parts.length > 1 && mode.n > 0 ? "append" : "replace"); return true; });
            if (ok) { mode.n++; paste.value = ""; if (parts.length <= 1 || mode.n >= parts.length) close(); }
          } }, "가져오기"), h("span", { class: "sub" }, "답변 속 ```json 블록을 자동으로 찾아요.")))));
    };
    const load = async () => guard(async () => render(await getPrompts()));
    if (extraTop) m.insertBefore(extraTop({ load, render }), slot);
    if (auto) load();
  });
}
