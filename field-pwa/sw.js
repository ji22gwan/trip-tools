// 서비스 워커: 한 번 열어 두면 오프라인에서도 앱이 켜진다.
// 파일을 바꿔 배포할 때는 VERSION 숫자를 올려 주세요.
const VERSION = "tf-v5";

const SHELL = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "css/app.css",
  "js/app.js",
  "js/db.js",
  "js/model.js",
  "js/recorder.js",
  "js/importer.js",
  "js/exporter.js",
  "js/translate.js",
  "js/panzoom.js",
  "js/ui.js",
  "js/views/shared.js",
  "js/views/map.js",
  "js/views/list.js",
  "js/views/recpick.js",
  "js/views/detail.js",
  "js/views/export.js",
  "js/views/setup.js",
  "js/views/settings.js",
  "vendor/jszip.min.js",
  "vendor/pdf.min.mjs",
  "vendor/pdf.worker.min.mjs",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// 저장된 파일을 바로 보여 주고, 뒤에서 새 버전을 받아 둔다(다음 실행부터 반영).
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 번역 서버 등 외부 요청은 건드리지 않음

  event.respondWith(
    caches.open(VERSION).then(async (cache) => {
      const cached = await cache.match(req, { ignoreSearch: true });
      const network = fetch(req)
        .then((res) => {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        })
        .catch(() => null);
      if (cached) {
        event.waitUntil(network);
        return cached;
      }
      const res = await network;
      if (res) return res;
      if (req.mode === "navigate") return (await cache.match("index.html")) || Response.error();
      return Response.error();
    }),
  );
});
