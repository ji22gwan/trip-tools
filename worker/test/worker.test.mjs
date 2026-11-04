import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

const env = {
  GEMINI_API_KEY: "secret-key",
  GEMINI_MODEL: "test-model",
  TOKENS: "tokA, tokB",
  ALLOWED_ORIGIN: "*",
};

function req(path, { method = "POST", token, body, origin } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (origin) headers.Origin = origin;
  return new Request(`https://w.example${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function mockGemini(replyText, status = 200) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    if (status !== 200) return new Response("boom", { status });
    return new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: replyText }] } }] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return calls;
}

test("health works without a token", async () => {
  const res = await worker.fetch(req("/health", { method: "GET" }), env);
  assert.equal(res.status, 200);
  assert.equal((await res.json()).ok, true);
});

test("OPTIONS returns CORS preflight", async () => {
  const res = await worker.fetch(req("/translate", { method: "OPTIONS" }), env);
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "*");
});

test("rejects missing or wrong token", async () => {
  mockGemini("x");
  let res = await worker.fetch(req("/translate", { body: { text: "a", to: "ko" } }), env);
  assert.equal(res.status, 401);
  res = await worker.fetch(req("/translate", { token: "nope", body: { text: "a", to: "ko" } }), env);
  assert.equal(res.status, 401);
});

test("server not configured returns 500", async () => {
  const res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "a", to: "ko" } }), { ...env, TOKENS: "" });
  assert.equal(res.status, 500);
});

test("validates input", async () => {
  mockGemini("x");
  let res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "  ", to: "ko" } }), env);
  assert.equal(res.status, 400);
  res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "hi" } }), env);
  assert.equal(res.status, 400);
  res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "a".repeat(2001), to: "ko" } }), env);
  assert.equal(res.status, 413);
});

test("translates and sends the key only in the header", async () => {
  const calls = mockGemini("적재 하중은 20킬로그램입니다.");
  const res = await worker.fetch(
    req("/translate", { token: "tokB", body: { text: "Die Nutzlast beträgt zwanzig Kilogramm.", from: "de", to: "ko" } }),
    env,
  );
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.translation, "적재 하중은 20킬로그램입니다.");
  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.includes("models/test-model:generateContent"));
  assert.ok(!calls[0].url.includes("secret-key"));
  assert.equal(calls[0].init.headers["x-goog-api-key"], "secret-key");
  const sent = JSON.parse(calls[0].init.body);
  assert.match(sent.systemInstruction.parts[0].text, /German/);
  assert.match(sent.systemInstruction.parts[0].text, /Korean/);
});

test("upstream failure becomes 502 without leaking the key", async () => {
  mockGemini("", 500);
  const res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "hi", to: "ko" } }), env);
  assert.equal(res.status, 502);
  const text = await res.text();
  assert.ok(!text.includes("secret-key"));
});

test("rate limit kicks in per token", async () => {
  mockGemini("ok");
  let last;
  for (let i = 0; i < 31; i++) {
    last = await worker.fetch(req("/translate", { token: "tokB", body: { text: "hi", to: "ko" } }), env);
  }
  assert.equal(last.status, 429);
});

test("response reports upstream time and model; generation is bounded", async () => {
  const calls = mockGemini("안녕하세요");
  const res = await worker.fetch(req("/translate", { token: "tokA", body: { text: "Hello", from: "en", to: "ko" } }), env);
  const data = await res.json();
  assert.equal(data.translation, "안녕하세요");
  assert.equal(data.model, "test-model");
  assert.equal(typeof data.ms, "number");
  const sent = JSON.parse(calls[0].init.body);
  assert.equal(sent.generationConfig.maxOutputTokens, 1024);
  assert.equal(sent.generationConfig.thinkingConfig, undefined);
});

test("thinking level is sent only when configured", async () => {
  const calls = mockGemini("x");
  await worker.fetch(req("/translate", { token: "tokA", body: { text: "Hi", from: "en", to: "ko" } }), { ...env, GEMINI_THINKING_LEVEL: "minimal" });
  assert.deepEqual(JSON.parse(calls[0].init.body).generationConfig.thinkingConfig, { thinkingLevel: "minimal" });
});
