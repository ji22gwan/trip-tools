// 번역: 폰 -> Cloudflare Worker -> Gemini. 키는 앱에 없고 팀원 토큰만 가진다.
import { loadSettings } from "./db.js";

export const LANGUAGES = [
  { code: "de", label: "독일어", speech: "de-DE" },
  { code: "ko", label: "한국어", speech: "ko-KR" },
  { code: "en", label: "영어", speech: "en-US" },
  { code: "fr", label: "프랑스어", speech: "fr-FR" },
  { code: "it", label: "이탈리아어", speech: "it-IT" },
  { code: "es", label: "스페인어", speech: "es-ES" },
  { code: "ja", label: "일본어", speech: "ja-JP" },
  { code: "zh", label: "중국어", speech: "zh-CN" },
];

const ERROR_TEXT = {
  unauthorized: "토큰이 맞지 않아요. 설정에서 확인해 주세요.",
  rate_limited: "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.",
  text_too_long: "문장이 너무 길어요. 나눠서 번역해 주세요.",
  empty_text: "번역할 문장을 입력해 주세요.",
  server_not_configured: "번역 서버 설정이 아직 끝나지 않았어요.",
  upstream_error: "번역 서비스가 응답하지 않아요. 잠시 후 다시 시도해 주세요.",
};

// 직전 번역의 시간 정보: total(앱에서 본 전체), upstream(Worker 가 Gemini 를 기다린 시간), model
let lastTiming = null;
export function getLastTiming() {
  return lastTiming;
}

export function translationConfigured() {
  const s = loadSettings();
  return !!(s.workerUrl && s.token);
}

export async function translateText(text, from, to, { signal } = {}) {
  const s = loadSettings();
  if (!s.workerUrl || !s.token) throw new Error("설정에서 번역 서버 주소와 토큰을 먼저 입력해 주세요.");
  if (navigator.onLine === false) throw new Error("오프라인이에요. 번역은 인터넷이 있을 때만 쓸 수 있어요.");

  const base = s.workerUrl.replace(/\/+$/, "");
  let res;
  const t0 = performance.now();
  try {
    res = await fetch(`${base}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${s.token}` },
      body: JSON.stringify({ text, from, to }),
      signal,
    });
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    throw new Error("번역 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.");
  }
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* 무시 */
  }
  if (!res.ok) throw new Error(ERROR_TEXT[data.error] || `번역에 실패했어요. (${res.status})`);
  lastTiming = { total: Math.round(performance.now() - t0), upstream: data.ms ?? null, model: data.model || "" };
  return data.translation;
}

export async function testConnection() {
  const s = loadSettings();
  if (!s.workerUrl) throw new Error("서버 주소를 입력해 주세요.");
  const base = s.workerUrl.replace(/\/+$/, "");
  const res = await fetch(`${base}/health`).catch(() => null);
  if (!res || !res.ok) throw new Error("서버에 연결하지 못했어요. 주소를 확인해 주세요.");
  if (s.token) {
    const out = await translateText("Hello", "en", "ko");
    const t = lastTiming;
    const detail = t ? ` · 전체 ${t.total}ms${t.upstream != null ? ` (Gemini ${t.upstream}ms)` : ""} · ${t.model}` : "";
    return `연결 성공 · 테스트 번역: ${out}${detail}`;
  }
  return "서버는 켜져 있어요. 토큰을 입력하면 번역을 시험할 수 있어요.";
}

export function speechRecognitionClass() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}
