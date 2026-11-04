// 출장·업체·날짜 관련 로직
import * as db from "./db.js";

export const SCHEMA_VERSION = 1;

// ---------- 날짜 ----------
export function todayISO(now = new Date()) {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function isoRange(startISO, endISO) {
  const [sy, sm, sd] = startISO.split("-").map(Number);
  const [ey, em, ed] = (endISO || startISO).split("-").map(Number);
  const out = [];
  let t = Date.UTC(sy, sm - 1, sd);
  const end = Date.UTC(ey, em - 1, ed);
  if (end < t) return [startISO];
  while (t <= end && out.length < 31) {
    const dt = new Date(t);
    out.push(`${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`);
    t += 86400000;
  }
  return out;
}

export function dayLabel(trip, day) {
  const iso = trip.days[day - 1];
  if (!iso) return `Day ${day}`;
  const [, m, d] = iso.split("-").map(Number);
  return `Day ${day} · ${m}월 ${d}일`;
}

export function currentDay(trip) {
  const stored = db.getSelectedDay(trip.id);
  if (stored && stored >= 1 && stored <= trip.days.length) return stored;
  const idx = trip.days.indexOf(todayISO());
  return idx >= 0 ? idx + 1 : 1;
}

export function dayOfTimestamp(trip, ts) {
  const idx = trip.days.indexOf(todayISO(new Date(ts)));
  return idx >= 0 ? idx + 1 : null;
}

// ---------- 표시용 포맷 ----------
export function formatTime(ts) {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function formatDuration(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function formatBytes(n) {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}

export function slugify(s) {
  return (
    String(s || "trip")
      .normalize("NFC") // NFKD 로 풀면 한글이 자모로 쪼개져 지워진다
      .replace(/[^\p{L}\p{N}_-]+/gu, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "trip"
  );
}

// ---------- 출장 ----------
export async function createTrip({ name, venue, startDate, endDate, purpose }) {
  const trip = {
    schema: SCHEMA_VERSION,
    id: db.newId(),
    name: name.trim(),
    venue: (venue || "").trim(),
    purpose: (purpose || "").trim(),
    days: isoRange(startDate, endDate || startDate),
    glossary: [],
    createdAt: Date.now(),
  };
  await db.put("trips", trip);
  db.setActiveTripId(trip.id);
  return trip;
}

export async function loadActiveTrip() {
  const id = db.getActiveTripId();
  if (id) {
    const t = await db.get("trips", id);
    if (t) return t;
  }
  const all = await db.getAll("trips");
  if (all.length) {
    all.sort((a, b) => b.createdAt - a.createdAt);
    db.setActiveTripId(all[0].id);
    return all[0];
  }
  return null;
}

// ---------- 업체 ----------
export async function listCompanies(tripId) {
  const items = await db.getAllByIndex("companies", "tripId", tripId);
  return items.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
}

export async function addCompany(trip, { name, category, hall, booth, day }) {
  const c = {
    id: db.newId(),
    tripId: trip.id,
    name: name.trim(),
    category: (category || "").trim() || "기타",
    hall: (hall || "").trim(),
    booth: (booth || "").trim(),
    day: day || null,
    preNotes: "",
    questions: [],
    addedOnSite: true,
    visits: [],
    createdAt: Date.now(),
  };
  await db.put("companies", c);
  return c;
}

export function isVisited(company, day) {
  return (company.visits || []).some((v) => v.day === day);
}

export async function setVisited(company, day, visited) {
  const rest = (company.visits || []).filter((v) => v.day !== day);
  company.visits = visited ? [...rest, { day, at: Date.now() }] : rest;
  await db.put("companies", company);
  return company;
}

export async function ensureVisited(company, day) {
  if (!isVisited(company, day)) await setVisited(company, day, true);
  return company;
}

// 오늘 리스트에 보일 업체: 오늘 계획된 업체 + 현장 추가 + 오늘 방문 체크된 업체
export function companiesForDay(companies, day) {
  return companies.filter((c) => c.day === day || isVisited(c, day));
}

export function groupByCategory(companies) {
  const groups = new Map();
  for (const c of companies) {
    const key = c.addedOnSite ? "현장 추가" : c.category || "기타";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const keys = [...groups.keys()].sort((a, b) => (a === "현장 추가") - (b === "현장 추가") || a.localeCompare(b, "ko"));
  return keys.map((k) => ({ title: k, items: groups.get(k) }));
}

// ---------- 방문 차수 ----------
export function visitNumber(recordings, rec) {
  const days = [...new Set(recordings.map((r) => r.day))].sort((a, b) => (a ?? 0) - (b ?? 0));
  return days.indexOf(rec.day) + 1;
}

// ---------- 업체 기록 모으기 ----------
export async function loadCompanyRecords(companyId) {
  const [recs, memos, photos] = await Promise.all([
    db.getAllByIndex("recordings", "companyId", companyId),
    db.getAllByIndex("memos", "companyId", companyId),
    db.getAllByIndex("photos", "companyId", companyId),
  ]);
  const byTime = (a, b) => a.createdAt - b.createdAt;
  return {
    recordings: recs.filter((r) => r.status === "done").sort(byTime),
    memos: memos.sort(byTime),
    photos: photos.sort(byTime),
  };
}

/** 홀 이름 비교 키: 'Hall 3A', '3a', '홀 3A' → '3A'. Desk 의 hall_key 와 같은 규칙. */
export function hallKey(s) {
  return String(s || "").trim().toUpperCase().replace(/^(HALLE|HALL|홀)\s*/, "").replace(/\s+/g, "");
}

/** 오늘 방문할 업체를 홀별로 묶어 지도 위 위치와 함께 돌려준다. 위치를 모르는 홀은 missing 으로. */
export function hallMarkers(companies, day, hallPins = {}) {
  const groups = new Map();
  for (const c of companies) {
    if (c.day !== day && !isVisited(c, day)) continue;
    const k = hallKey(c.hall);
    if (!k) continue;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  }
  const markers = [];
  const missing = [];
  for (const [key, list] of groups) {
    const pin = hallPins[key];
    if (pin) markers.push({ key, page: pin.page || 0, x: pin.x, y: pin.y, companies: list, done: list.filter((c) => isVisited(c, day)).length });
    else missing.push(key);
  }
  return { markers, missing };
}
