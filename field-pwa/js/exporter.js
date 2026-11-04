// 하루치 데이터를 ZIP 하나로 만든다. (노트북 Trip Desk가 읽는 형식)
//
//   trip_<이름>/days/day<N>/
//       visits.json
//       audio/<업체>_<HHMM>_<번호>.m4a|webm
//       photos/<업체>_<HHMM>_<번호>.jpg
import * as db from "./db.js";
import { SCHEMA_VERSION, slugify, listCompanies, isVisited } from "./model.js";
import { extensionFor } from "./recorder.js";

function hhmm(ts) {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}`;
}

function photoExt(blob) {
  const t = blob?.type || "";
  if (t.includes("png")) return "png";
  if (t.includes("webp")) return "webp";
  if (t.includes("heic")) return "heic";
  return "jpg";
}

export async function collectDay(trip, day) {
  const [companies, recordings, memos, photos] = await Promise.all([
    listCompanies(trip.id),
    db.getAllByIndex("recordings", "tripId", trip.id),
    db.getAllByIndex("memos", "tripId", trip.id),
    db.getAllByIndex("photos", "tripId", trip.id),
  ]);
  const dayRecs = recordings.filter((r) => r.status === "done" && r.day === day);
  const dayMemos = memos.filter((m) => m.day === day);
  const dayPhotos = photos.filter((p) => p.day === day);

  const active = companies.filter(
    (c) => isVisited(c, day) || dayRecs.some((r) => r.companyId === c.id) || dayMemos.some((m) => m.companyId === c.id) || dayPhotos.some((p) => p.companyId === c.id),
  );
  return { companies: active, recordings: dayRecs, memos: dayMemos, photos: dayPhotos };
}

export function countsOf(data) {
  const audioSeconds = data.recordings.reduce((s, r) => s + (r.duration || 0), 0);
  return {
    companies: data.companies.length,
    recordings: data.recordings.length,
    audioSeconds,
    memos: data.memos.length,
    photos: data.photos.length,
    newCompanies: data.companies.filter((c) => c.addedOnSite).length,
  };
}

export async function buildDayZip(trip, day, JSZip = globalThis.JSZip) {
  if (!JSZip) throw new Error("ZIP 라이브러리를 불러오지 못했어요.");
  const data = await collectDay(trip, day);
  const root = `trip_${slugify(trip.name)}`;
  const dayDir = `${root}/days/day${day}`;
  const zip = new JSZip();
  const used = new Set();

  function uniqueName(dir, base, ext) {
    let n = 1;
    let name;
    do {
      name = `${dir}/${base}_${String(n).padStart(2, "0")}.${ext}`;
      n++;
    } while (used.has(name));
    used.add(name);
    return name;
  }

  const companiesOut = [];
  for (const c of data.companies) {
    const slug = slugify(c.name);
    const recs = data.recordings.filter((r) => r.companyId === c.id).sort((a, b) => a.createdAt - b.createdAt);
    const mems = data.memos.filter((m) => m.companyId === c.id).sort((a, b) => a.createdAt - b.createdAt);
    const phs = data.photos.filter((p) => p.companyId === c.id).sort((a, b) => a.createdAt - b.createdAt);

    const recOut = [];
    for (const r of recs) {
      const path = uniqueName(`${dayDir}/audio`, `${slug}_${hhmm(r.createdAt)}`, extensionFor(r.mime));
      zip.file(path, r.blob);
      recOut.push({
        file: path.slice(dayDir.length + 1),
        at: new Date(r.createdAt).toISOString(),
        durationSec: Math.round(r.duration || 0),
        mime: r.mime,
        recovered: !!r.recovered,
      });
    }
    const phOut = [];
    for (const p of phs) {
      const path = uniqueName(`${dayDir}/photos`, `${slug}_${hhmm(p.createdAt)}`, photoExt(p.blob));
      zip.file(path, p.blob);
      phOut.push({ file: path.slice(dayDir.length + 1), at: new Date(p.createdAt).toISOString() });
    }

    companiesOut.push({
      id: c.id,
      name: c.name,
      category: c.category,
      hall: c.hall,
      booth: c.booth,
      addedOnSite: !!c.addedOnSite,
      visited: isVisited(c, day),
      visitedAt: (c.visits || []).find((v) => v.day === day)?.at ? new Date(c.visits.find((v) => v.day === day).at).toISOString() : null,
      recordings: recOut,
      memos: mems.map((m) => ({ text: m.text, important: !!m.important, at: new Date(m.createdAt).toISOString() })),
      photos: phOut,
    });
  }

  const visits = {
    schema: SCHEMA_VERSION,
    tripId: trip.id,
    tripName: trip.name,
    venue: trip.venue,
    day,
    date: trip.days[day - 1] || null,
    exportedAt: new Date().toISOString(),
    tzOffsetMin: -new Date().getTimezoneOffset(), // 폰이 있던 곳의 UTC 대비 분(독일 겨울 +60). 노트북이 다른 시간대여도 현장 시각으로 보여 주기 위해
    companies: companiesOut,
  };
  zip.file(`${dayDir}/visits.json`, JSON.stringify(visits, null, 2));

  const blob = await zip.generateAsync({ type: "blob", compression: "STORE" }); // 음성/사진은 이미 압축된 형식
  const filename = `${slugify(trip.name)}_day${day}_${trip.days[day - 1] || "date"}.zip`;
  return { blob, filename, counts: countsOf(data), visits };
}

export async function shareOrDownload(blob, filename) {
  const file = new File([blob], filename, { type: "application/zip" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename });
      return "shared";
    } catch (e) {
      if (e?.name === "AbortError") return "cancelled";
      // 공유 시트를 못 열면 다운로드로 대체
    }
  }
  downloadBlob(blob, filename);
  return "downloaded";
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export async function logExport(trip, day, counts, size) {
  const entry = { id: db.newId(), tripId: trip.id, day, at: Date.now(), counts, size };
  await db.put("exports", entry);
  return entry;
}

export async function listExports(tripId) {
  const items = await db.getAllByIndex("exports", "tripId", tripId);
  return items.sort((a, b) => b.at - a.at);
}
