// 공통 UI 도우미
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

const svg = (body, size = 24, stroke = 2.2) =>
  `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;

export const icons = {
  search: (s) => svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', s, 2),
  map: (s) => svg('<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14"/>', s),
  list: (s) => svg('<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>', s),
  mic: (s) => svg('<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>', s),
  micFill: (s) => svg('<rect x="9" y="3" width="6" height="12" rx="3" fill="currentColor"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>', s, 2.4),
  upload: (s) => svg('<path d="M12 15V4M8 8l4-4 4 4M5 14v5h14v-5"/>', s),
  plus: (s) => svg('<path d="M12 5v14M5 12h14"/>', s, 3),
  check: (s = 18) => svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>', s, 3.2),
  back: (s) => svg('<path d="M15 5l-7 7 7 7"/>', s, 2.6),
  close: (s) => svg('<path d="M6 6l12 12M18 6L6 18"/>', s, 2.6),
  play: (s = 18) => `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12-7.5z"/></svg>`,
  pause: (s = 18) => `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4h4v16H7zM13 4h4v16h-4z"/></svg>`,
  camera: (s) => svg('<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>', s),
  translate: (s) => svg('<path d="M4 5h9M8.5 3v2M6 5c.5 3.5 3 6.5 6.5 8M12 5c-.5 3.5-3 6.5-7 8.5M13 20l4-9 4 9M14.5 17h5"/>', s),
  swap: (s) => svg('<path d="M7 8h12l-3-3M17 16H5l3 3"/>', s, 2.4),
  gear: (s) => svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>', s, 1.8),
  star: (s = 14) => `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3l2.7 5.8 6.3.7-4.7 4.3 1.3 6.2L12 17l-5.6 3 1.3-6.2L3 9.5l6.3-.7z"/></svg>`,
  warn: (s) => svg('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>', s, 2.4),
  utensils: (s) => svg('<path d="M7 3v8M4 3v5a3 3 0 006 0V3M7 11v10M17 21V3c-2.5 1.5-3.5 4-3.5 7 0 2 1 3 3.5 3"/>', s, 2),
  plane: (s) => svg('<path d="M10.5 13.5L3 11l1.5-1.5 9 .5L18 5.5a2 2 0 013 3l-4.5 4.5.5 9-1.5 1.5-2.5-7.5-4.5 4.5-1-1 4.5-4.5z"/>', s, 2),
  chevR: (s) => svg('<path d="M9 6l6 6-6 6"/>', s, 2.4),
  chevD: (s) => svg('<path d="M6 9l6 6 6-6"/>', s, 2.6),
  compass: (s) => svg('<path d="M12 3l7 18-7-4-7 4z"/>', s, 2.2),
  pin: (s) => svg('<path d="M12 21s7-6.2 7-11.5A7 7 0 005 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>', s, 2),
  trash: (s) => svg('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', s),
};

let toastTimer = null;
export function toast(msg, ms = 2600) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), ms);
}

// 팝업 / 시트. 닫기 함수를 돌려준다.
export function openSheet(html, { bottom = false, onClose } = {}) {
  const scrim = document.createElement("div");
  scrim.className = "scrim" + (bottom ? " bottom" : "");
  scrim.innerHTML = `<div class="sheet" role="dialog" aria-modal="true">${html}</div>`;
  document.body.appendChild(scrim);
  const close = () => {
    scrim.remove();
    onClose?.();
  };
  scrim.addEventListener("click", (e) => {
    if (e.target === scrim) close();
  });
  scrim.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
  return { el: scrim.querySelector(".sheet"), close };
}

export function confirmDialog(message, okLabel = "확인") {
  return new Promise((resolve) => {
    const { el, close } = openSheet(
      `<p style="margin:0;font-size:16px;line-height:1.5">${esc(message)}</p>
       <div class="row"><button class="btn btn-block" data-no>취소</button><button class="btn btn-dark btn-block" data-yes>${esc(okLabel)}</button></div>`,
    );
    el.querySelector("[data-no]").onclick = () => {
      close();
      resolve(false);
    };
    el.querySelector("[data-yes]").onclick = () => {
      close();
      resolve(true);
    };
  });
}

export function pickFile(accept, { capture } = {}) {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    if (capture) input.capture = capture;
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener("change", () => {
      const f = input.files?.[0] || null;
      input.remove();
      resolve(f);
    });
    input.addEventListener("cancel", () => {
      input.remove();
      resolve(null);
    });
    input.click();
  });
}
