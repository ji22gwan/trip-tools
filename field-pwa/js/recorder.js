// 녹음: MediaRecorder + 1초마다 조각 저장(앱이 꺼져도 복구 가능) + 화면 켜짐 유지
import * as db from "./db.js";

function pickMime() {
  const candidates = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported?.(m)) return m;
  }
  return "";
}

export function extensionFor(mime) {
  if (!mime) return "bin";
  if (mime.includes("mp4") || mime.includes("aac")) return "m4a";
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("wav")) return "wav";
  return "bin";
}

export function isRecordingSupported() {
  return !!(navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
}

async function assemble(recId, mime) {
  const chunks = await db.getAllByIndex("chunks", "recId", recId);
  chunks.sort((a, b) => a.seq - b.seq);
  return new Blob(
    chunks.map((c) => c.blob),
    { type: mime || "audio/webm" },
  );
}

export class Recorder {
  constructor() {
    this.recorder = null;
    this.stream = null;
    this.rec = null;
    this.seq = 0;
    this.startedAt = 0;
    this.timer = null;
    this.wakeLock = null;
    this.onTick = null;
    this._visibility = () => this._reacquireWakeLock();
  }

  get active() {
    return !!this.recorder && this.recorder.state !== "inactive";
  }

  async start({ tripId, companyId, day }, onTick) {
    if (this.active) return this.rec;
    this.onTick = onTick;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const mime = pickMime();
    this.recorder = mime ? new MediaRecorder(this.stream, { mimeType: mime }) : new MediaRecorder(this.stream);
    const usedMime = this.recorder.mimeType || mime || "audio/webm";

    this.rec = {
      id: db.newId(),
      tripId,
      companyId,
      day,
      mime: usedMime,
      createdAt: Date.now(),
      duration: 0,
      status: "recording",
    };
    this.seq = 0;
    await db.put("recordings", this.rec);

    const recId = this.rec.id;
    this.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        const seq = this.seq++;
        db.put("chunks", { recId, seq, blob: e.data }).catch(() => {});
      }
    };
    this.startedAt = Date.now();
    this.recorder.start(1000);
    this.timer = setInterval(() => this.onTick?.((Date.now() - this.startedAt) / 1000), 250);

    await this._acquireWakeLock();
    document.addEventListener("visibilitychange", this._visibility);
    return this.rec;
  }

  async stop() {
    if (!this.active) return null;
    const recorder = this.recorder;
    const rec = this.rec;
    const stopped = new Promise((resolve) => {
      recorder.onstop = resolve;
    });
    try {
      recorder.requestData?.();
    } catch {
      /* 무시 */
    }
    recorder.stop();
    await stopped;
    // 마지막 조각 저장이 끝날 시간을 잠깐 준다
    await new Promise((r) => setTimeout(r, 120));

    clearInterval(this.timer);
    this.stream?.getTracks().forEach((t) => t.stop());
    document.removeEventListener("visibilitychange", this._visibility);
    await this._releaseWakeLock();

    const duration = (Date.now() - this.startedAt) / 1000;
    const blob = await assemble(rec.id, rec.mime);
    const done = { ...rec, blob, duration, status: "done" };
    await db.put("recordings", done);
    await db.delAllByIndex("chunks", "recId", rec.id);
    this.recorder = null;
    this.stream = null;
    this.rec = null;
    return done;
  }

  async _acquireWakeLock() {
    try {
      if ("wakeLock" in navigator) this.wakeLock = await navigator.wakeLock.request("screen");
    } catch {
      this.wakeLock = null;
    }
  }

  async _reacquireWakeLock() {
    if (document.visibilityState === "visible" && this.active) await this._acquireWakeLock();
  }

  async _releaseWakeLock() {
    try {
      await this.wakeLock?.release();
    } catch {
      /* 무시 */
    }
    this.wakeLock = null;
  }
}

// 앱이 갑자기 꺼졌을 때 남은 녹음 조각을 복구한다
export async function recoverRecordings() {
  const all = await db.getAll("recordings");
  let recovered = 0;
  for (const r of all) {
    if (r.status !== "recording") continue;
    const blob = await assemble(r.id, r.mime);
    if (blob.size > 0) {
      await db.put("recordings", { ...r, blob, status: "done", recovered: true });
      recovered++;
    } else {
      await db.del("recordings", r.id);
    }
    await db.delAllByIndex("chunks", "recId", r.id);
  }
  return recovered;
}
