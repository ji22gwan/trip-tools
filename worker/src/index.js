// Trip Translate Worker
// 폰 앱(Trip Field) -> 이 Worker -> Gemini. API 키는 Worker 비밀 값으로만 존재합니다.
//
// 필요한 설정
//   비밀 값:  GEMINI_API_KEY (Gemini 키), TOKENS (허용할 팀원 토큰, 쉼표로 구분)
//   일반 값:  GEMINI_MODEL (모델 ID), ALLOWED_ORIGIN (앱 주소, 비우면 모두 허용)
//   선택 값:  GEMINI_THINKING_LEVEL (minimal/low/medium/high. 비우면 모델 기본값. 지원하지 않는 모델에 쓰면 오류가 나요)

const MAX_TEXT_LENGTH = 2000;
const RATE_LIMIT_PER_MINUTE = 30; // 토큰별, Worker 인스턴스 단위의 간이 제한

const LANG_NAMES = {
  ko: "Korean",
  de: "German",
  en: "English",
  ja: "Japanese",
  zh: "Chinese",
  fr: "French",
  it: "Italian",
  es: "Spanish",
};

const rateBuckets = new Map();

function corsHeaders(env, request) {
  const allowed = (env.ALLOWED_ORIGIN || "*").trim();
  const origin = request.headers.get("Origin") || "";
  let allowOrigin = "*";
  if (allowed !== "*") {
    const list = allowed.split(",").map((s) => s.trim()).filter(Boolean);
    allowOrigin = list.includes(origin) ? origin : list[0] || "";
  }
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function getToken(request) {
  const auth = request.headers.get("Authorization") || "";
  const m = auth.match(/^Bearer\s+(.+)$/i);
  return m ? m[1].trim() : "";
}

function isAllowedToken(env, token) {
  const list = String(env.TOKENS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return token !== "" && list.includes(token);
}

function rateLimited(token, now = Date.now()) {
  const windowStart = now - 60_000;
  const hits = (rateBuckets.get(token) || []).filter((t) => t > windowStart);
  if (hits.length >= RATE_LIMIT_PER_MINUTE) {
    rateBuckets.set(token, hits);
    return true;
  }
  hits.push(now);
  rateBuckets.set(token, hits);
  return false;
}

function buildPrompt(from, to) {
  const fromName = from === "auto" ? "the source language (detect it)" : LANG_NAMES[from] || from;
  const toName = LANG_NAMES[to] || to;
  return [
    "You are a live interpreter helping an engineer at an industrial trade fair.",
    `Translate the user's text from ${fromName} into ${toName}.`,
    "Keep product names, company names, units and technical terms (for example EtherCAT, payload, TCP) in their original form when that is how engineers say them.",
    "Output only the translation. No explanations, no quotation marks, no notes.",
  ].join(" ");
}

function generationConfig(env) {
  // 번역은 짧은 출력이면 충분하다. 길이를 제한해 엉뚱하게 길어지는 응답을 막는다.
  const cfg = { temperature: 0, maxOutputTokens: 1024 };
  const level = String(env.GEMINI_THINKING_LEVEL || "").trim();
  if (level) cfg.thinkingConfig = { thinkingLevel: level };
  return cfg;
}

async function translate(env, text, from, to) {
  const model = env.GEMINI_MODEL;
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": env.GEMINI_API_KEY,
    },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: buildPrompt(from, to) }] },
      contents: [{ role: "user", parts: [{ text }] }],
      generationConfig: generationConfig(env),
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    const err = new Error(`Gemini ${res.status}`);
    err.status = res.status;
    err.detail = detail.slice(0, 300);
    throw err;
  }
  const data = await res.json();
  const parts = data?.candidates?.[0]?.content?.parts || [];
  const out = parts.map((p) => p.text || "").join("").trim();
  if (!out) throw new Error("Gemini returned an empty result");
  return out;
}

export default {
  async fetch(request, env) {
    const cors = corsHeaders(env, request);
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, model: env.GEMINI_MODEL || null }, 200, cors);
    }

    if (request.method !== "POST" || url.pathname !== "/translate") {
      return json({ error: "not_found" }, 404, cors);
    }

    if (!env.GEMINI_API_KEY || !env.GEMINI_MODEL || !env.TOKENS) {
      return json({ error: "server_not_configured" }, 500, cors);
    }

    const token = getToken(request);
    if (!isAllowedToken(env, token)) {
      return json({ error: "unauthorized" }, 401, cors);
    }
    if (rateLimited(token)) {
      return json({ error: "rate_limited" }, 429, cors);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid_json" }, 400, cors);
    }

    const text = typeof body?.text === "string" ? body.text.trim() : "";
    const from = typeof body?.from === "string" ? body.from : "auto";
    const to = typeof body?.to === "string" ? body.to : "";
    if (!text) return json({ error: "empty_text" }, 400, cors);
    if (text.length > MAX_TEXT_LENGTH) return json({ error: "text_too_long", max: MAX_TEXT_LENGTH }, 413, cors);
    if (!to) return json({ error: "missing_target_language" }, 400, cors);

    try {
      const started = Date.now();
      const translation = await translate(env, text, from, to);
      // ms: Worker 가 Gemini 를 기다린 시간. 앱에서 보이는 전체 시간과 비교하면 어디서 느린지 알 수 있다.
      return json({ translation, model: env.GEMINI_MODEL, ms: Date.now() - started }, 200, cors);
    } catch (e) {
      return json({ error: "upstream_error", status: e.status || 0, detail: e.detail || "" }, 502, cors);
    }
  },
};

export { buildPrompt, generationConfig, isAllowedToken, rateLimited };
