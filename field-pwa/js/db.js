// IndexedDB 래퍼. 모든 현장 데이터는 폰 안에만 저장됩니다.
const DB_NAME = "tripfield";
const DB_VERSION = 2; // 2: exhibitors 저장소 추가(지금은 쓰지 않지만 버전을 낮추면 오류가 나므로 유지)

const STORES = {
  trips: { keyPath: "id" },
  companies: { keyPath: "id", indexes: ["tripId"] },
  recordings: { keyPath: "id", indexes: ["companyId", "tripId"] },
  chunks: { keyPath: ["recId", "seq"], indexes: ["recId"] },
  memos: { keyPath: "id", indexes: ["companyId", "tripId"] },
  photos: { keyPath: "id", indexes: ["companyId", "tripId"] },
  maps: { keyPath: "id", indexes: ["tripId"] },
  exports: { keyPath: "id", indexes: ["tripId"] },
  exhibitors: { keyPath: "id", indexes: ["tripId"] }, // 출장당 1건: { id: tripId, items: [{name, hall, booth, category, country}] }
};

let dbPromise = null;

export function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const [name, def] of Object.entries(STORES)) {
        if (db.objectStoreNames.contains(name)) continue;
        const store = db.createObjectStore(name, { keyPath: def.keyPath });
        for (const idx of def.indexes || []) store.createIndex(idx, idx, { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function wrap(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function store(name, mode = "readonly") {
  const db = await openDb();
  return db.transaction(name, mode).objectStore(name);
}

export async function get(name, key) {
  return wrap((await store(name)).get(key));
}

export async function getAll(name) {
  return wrap((await store(name)).getAll());
}

export async function getAllByIndex(name, index, value) {
  return wrap((await store(name)).index(index).getAll(value));
}

export async function put(name, value) {
  await wrap((await store(name, "readwrite")).put(value));
  return value;
}

export async function del(name, key) {
  return wrap((await store(name, "readwrite")).delete(key));
}

export async function delAllByIndex(name, index, value) {
  const items = await getAllByIndex(name, index, value);
  const s = await store(name, "readwrite");
  const keyPath = STORES[name].keyPath;
  await Promise.all(
    items.map((it) => wrap(s.delete(Array.isArray(keyPath) ? keyPath.map((k) => it[k]) : it[keyPath]))),
  );
}

export function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "id-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

// ---- 작은 설정 값(localStorage) ----
const SETTINGS_KEY = "tf.settings";

export function loadSettings() {
  try {
    return { workerUrl: "", token: "", fromLang: "de", toLang: "ko", ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch {
    return { workerUrl: "", token: "", fromLang: "de", toLang: "ko" };
  }
}

export function saveSettings(patch) {
  const next = { ...loadSettings(), ...patch };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  return next;
}

export function getActiveTripId() {
  return localStorage.getItem("tf.activeTripId");
}

export function setActiveTripId(id) {
  localStorage.setItem("tf.activeTripId", id);
}

export function getSelectedDay(tripId) {
  const v = localStorage.getItem("tf.day." + tripId);
  return v ? Number(v) : null;
}

export function setSelectedDay(tripId, day) {
  localStorage.setItem("tf.day." + tripId, String(day));
}
