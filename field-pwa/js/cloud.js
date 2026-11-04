// 서버(Worker) 패키지 보관함: Desk 가 올린 출장 패키지를 목록으로 보고 내려받는다.
import { loadSettings } from "./db.js";

const ERR = {
  unauthorized: "토큰이 맞지 않아요. 설정에서 확인해 주세요.",
  storage_not_configured: "서버에 패키지 보관함이 아직 없어요. 노트북에서 install-worker 를 다시 실행해 주세요.",
  rate_limited: "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.",
  not_found: "서버에서 찾지 못했어요. Desk 에서 다시 보내 주세요.",
};

function conf() {
  const s = loadSettings();
  if (!s.workerUrl || !s.token) throw new Error("설정에서 번역 서버 주소와 토큰을 먼저 입력해 주세요.");
  return { base: s.workerUrl.replace(/\/+$/, ""), headers: { Authorization: `Bearer ${s.token}` } };
}

async function check(res) {
  if (res.ok) return res;
  let code = "";
  try { code = (await res.json()).error || ""; } catch { /* 본문 없음 */ }
  throw new Error(ERR[code] || `서버 응답 오류(${res.status})`);
}

export async function listServerPackages() {
  const { base, headers } = conf();
  const res = await check(await fetch(`${base}/packages`, { headers }).catch(() => { throw new Error("서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."); }));
  return (await res.json()).packages || [];
}

export async function downloadServerPackage(id) {
  const { base, headers } = conf();
  const res = await check(await fetch(`${base}/packages/${encodeURIComponent(id)}`, { headers }).catch(() => { throw new Error("서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."); }));
  return res.arrayBuffer();
}
