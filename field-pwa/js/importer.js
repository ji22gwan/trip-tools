// 노트북이 만든 출장 패키지(ZIP) 불러오기, 맵 PDF/PNG 불러오기
import * as db from "./db.js";
import { SCHEMA_VERSION } from "./model.js";

function requireJSZip() {
  if (!globalThis.JSZip) throw new Error("ZIP 라이브러리를 불러오지 못했어요. 새로고침해 주세요.");
  return globalThis.JSZip;
}

let pdfjsPromise = null;
async function loadPdfJs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("../vendor/pdf.min.mjs").then((m) => {
      m.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdf.worker.min.mjs", import.meta.url).href;
      return m;
    });
  }
  return pdfjsPromise;
}

function canvasToBlob(canvas, type = "image/png", quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("이미지 변환 실패"))), type, quality);
  });
}

// PDF -> 페이지별 이미지. 아이폰 캔버스 한도를 넘지 않도록 픽셀 수를 제한한다.
export async function pdfToImages(arrayBuffer, { maxPages = 12, targetWidth = 3600, maxPixels = 12_000_000 } = {}) {
  const pdfjs = await loadPdfJs();
  const doc = await pdfjs.getDocument({ data: arrayBuffer }).promise;
  const out = [];
  const pages = Math.min(doc.numPages, maxPages);
  for (let i = 1; i <= pages; i++) {
    const page = await doc.getPage(i);
    const base = page.getViewport({ scale: 1 });
    let scale = Math.min(4, targetWidth / base.width);
    const pixels = base.width * scale * (base.height * scale);
    if (pixels > maxPixels) scale *= Math.sqrt(maxPixels / pixels);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: ctx, viewport }).promise;
    const blob = await canvasToBlob(canvas, "image/png");
    out.push({ blob, width: canvas.width, height: canvas.height, name: doc.numPages > 1 ? `페이지 ${i}` : "전시장 맵" });
    canvas.width = canvas.height = 0;
  }
  return out;
}

async function imageSize(blob) {
  try {
    const bmp = await createImageBitmap(blob);
    const size = { width: bmp.width, height: bmp.height };
    bmp.close?.();
    return size;
  } catch {
    return { width: 0, height: 0 };
  }
}

// 파일 하나(PDF/PNG/JPG)를 맵으로 저장한다. replace=true 면 기존 맵을 지운다.
export async function importMapFile(tripId, file, { replace = true } = {}) {
  const name = file.name || "map";
  const lower = name.toLowerCase();
  let images = [];
  if (lower.endsWith(".pdf") || file.type === "application/pdf") {
    images = await pdfToImages(await file.arrayBuffer());
  } else if (/\.(png|jpe?g|webp)$/.test(lower) || file.type.startsWith("image/")) {
    const size = await imageSize(file);
    images = [{ blob: file, ...size, name: name.replace(/\.[^.]+$/, "") }];
  } else {
    throw new Error("PDF, PNG, JPG 파일만 불러올 수 있어요.");
  }
  if (!images.length) throw new Error("맵 이미지를 만들지 못했어요.");
  if (replace) await db.delAllByIndex("maps", "tripId", tripId);
  const existing = replace ? [] : await db.getAllByIndex("maps", "tripId", tripId);
  let order = existing.length;
  for (const img of images) {
    await db.put("maps", { id: db.newId(), tripId, name: img.name, blob: img.blob, width: img.width, height: img.height, order: order++ });
  }
  return images.length;
}

function normalizeQuestions(list, previous = []) {
  const prevDone = new Map(previous.map((q) => [q.text, q.done]));
  return (list || [])
    .map((q) => (typeof q === "string" ? { text: q } : q))
    .filter((q) => q && q.text)
    .map((q) => ({ text: String(q.text), done: prevDone.get(String(q.text)) ?? !!q.done }));
}

function findEntry(zip, basename) {
  const names = Object.keys(zip.files).filter((n) => !zip.files[n].dir);
  return names.find((n) => n.split("/").pop() === basename) || null;
}

export async function importTripPackage(file) {
  const JSZip = requireJSZip();
  const zip = await JSZip.loadAsync(file);

  const tripPath = findEntry(zip, "trip.json");
  const companiesPath = findEntry(zip, "companies.json");
  if (!tripPath || !companiesPath) throw new Error("출장 패키지가 아니에요. trip.json 과 companies.json 이 필요합니다.");

  const tripIn = JSON.parse(await zip.files[tripPath].async("string"));
  const companiesIn = JSON.parse(await zip.files[companiesPath].async("string"));
  if (!tripIn.id || !tripIn.name || !Array.isArray(tripIn.days) || !tripIn.days.length) {
    throw new Error("trip.json 에 id, name, days 가 필요해요.");
  }
  if ((tripIn.schema || 1) > SCHEMA_VERSION) throw new Error("더 새로운 버전의 패키지예요. 앱을 업데이트해 주세요.");

  let glossary = [];
  const glossaryPath = findEntry(zip, "glossary.json");
  if (glossaryPath) {
    try {
      const g = JSON.parse(await zip.files[glossaryPath].async("string"));
      glossary = Array.isArray(g) ? g : g.terms || [];
    } catch {
      glossary = [];
    }
  }

  const existingTrip = await db.get("trips", tripIn.id);
  const trip = {
    schema: SCHEMA_VERSION,
    id: tripIn.id,
    name: tripIn.name,
    venue: tripIn.venue || "",
    purpose: tripIn.purpose || "",
    days: tripIn.days,
    glossary,
    hallPins: cleanPins(tripIn.hallPins),
    bookings: { flights: Array.isArray(tripIn.bookings?.flights) ? tripIn.bookings.flights : [], hotels: Array.isArray(tripIn.bookings?.hotels) ? tripIn.bookings.hotels : [] },
    createdAt: existingTrip?.createdAt || Date.now(),
  };
  await db.put("trips", trip);

  const existing = new Map((await db.getAllByIndex("companies", "tripId", trip.id)).map((c) => [c.id, c]));
  let added = 0;
  let updated = 0;
  for (const c of companiesIn) {
    if (!c.id || !c.name) continue;
    const prev = existing.get(c.id);
    const merged = {
      id: c.id,
      tripId: trip.id,
      name: c.name,
      category: c.category || "기타",
      hall: c.hall || "",
      booth: c.booth || "",
      day: c.day ?? null,
      preNotes: c.preNotes || "",
      questions: normalizeQuestions(c.questions, prev?.questions),
      addedOnSite: prev?.addedOnSite ?? !!c.addedOnSite,
      visits: prev?.visits || [],
      createdAt: prev?.createdAt || Date.now() + added,
    };
    await db.put("companies", merged);
    prev ? updated++ : added++;
  }

  // 맵
  const mapPaths = Object.keys(zip.files).filter(
    (n) => !zip.files[n].dir && /(^|\/)map\//i.test(n) && /\.(pdf|png|jpe?g|webp)$/i.test(n),
  );
  let maps = 0;
  if (mapPaths.length) {
    await db.delAllByIndex("maps", "tripId", trip.id);
    for (const p of mapPaths.sort()) {
      const blob = await zip.files[p].async("blob");
      const f = new File([blob], p.split("/").pop(), { type: blob.type });
      maps += await importMapFile(trip.id, f, { replace: false });
    }
  }

  db.setActiveTripId(trip.id);
  return { trip, added, updated, maps };
}

function cleanPins(p) {
  const out = {};
  if (!p || typeof p !== "object") return out;
  for (const [k, v] of Object.entries(p)) {
    const x = Number(v?.x), y = Number(v?.y);
    if (k && x >= 0 && x <= 1 && y >= 0 && y <= 1) out[k] = { x, y, page: Number(v.page) || 0 };
  }
  return out;
}
