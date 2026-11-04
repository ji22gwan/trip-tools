// 저녁 내보내기: 하루치를 ZIP 하나로 만들어 공유(AirDrop/메일)한다
import { esc, icons, toast } from "../ui.js";
import { dayLabel, formatBytes, formatDuration, formatTime } from "../model.js";
import { buildDayZip, collectDay, countsOf, downloadBlob, listExports, logExport, shareOrDownload } from "../exporter.js";
import { headerHtml, bindHeader } from "./shared.js";

let built = null; // 직전에 만든 ZIP { day, blob, filename, counts }

export async function renderExport(root, ctx) {
  const { trip, day } = ctx;
  const data = await collectDay(trip, day);
  const counts = countsOf(data);
  const exports = await listExports(trip.id);
  const lastForDay = exports.find((e) => e.day === day);
  // 만든 뒤에 기록이 더 쌓였으면 ZIP이 낡은 것이므로 다시 만들게 한다
  const readyBuild =
    built && built.tripId === trip.id && built.day === day && JSON.stringify(built.counts) === JSON.stringify(counts) ? built : null;

  const logRows = trip.days
    .map((_, i) => {
      const d = i + 1;
      const e = exports.find((x) => x.day === d);
      const ringColor = d === day ? "var(--orange)" : "var(--line)";
      const dotStyle = e
        ? "width:24px;height:24px;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#fff;flex:none;background:var(--ink)"
        : `width:24px;height:24px;border-radius:12px;border:2px solid ${ringColor};flex:none`;
      return `<div class="row" style="min-height:40px">
        <span style="${dotStyle}">${e ? icons.check(14) : ""}</span>
        <span style="flex:1">${esc(dayLabel(trip, d))}${e ? ` · ${formatTime(e.at)}` : ""}</span>
        <span class="tiny" style="font-weight:700;color:${e ? "var(--blue)" : d === day ? "var(--orange)" : "var(--sub)"}">${e ? "내보냄" : d === day ? "아직 안 내보냄" : "—"}</span>
      </div>`;
    })
    .join("");

  root.innerHTML = `
    ${headerHtml(trip, day)}
    <div class="header" style="padding-top:0"><div class="title" style="font-size:20px">오늘 데이터 내보내기</div></div>
    <div class="scroll"><div class="stack">
      <div class="card">
        <div class="card-title">${esc(dayLabel(trip, day))} 수집한 내용</div>
        <div class="stat-grid">
          <div class="stat"><span class="k">방문 업체</span><span class="v">${counts.companies}곳</span></div>
          <div class="stat"><span class="k">녹음</span><span class="v">${counts.recordings}건 · ${counts.audioSeconds < 60 ? `${Math.round(counts.audioSeconds)}초` : `${Math.round(counts.audioSeconds / 60)}분`}</span></div>
          <div class="stat"><span class="k">직접 메모</span><span class="v">${counts.memos}건</span></div>
          <div class="stat"><span class="k">사진</span><span class="v">${counts.photos}장</span></div>
        </div>
        <div class="small muted" style="margin-top:10px">현장 추가 업체 ${counts.newCompanies}곳 포함${lastForDay ? ` · 마지막 내보내기 ${formatTime(lastForDay.at)} (그 뒤 추가분은 다시 내보내 주세요)` : ""}</div>
      </div>
      <div class="notice"><span style="color:var(--orange);flex:none">${icons.warn(22)}</span><div>내보내기를 마치기 전에는 브라우저 데이터나 사이트 데이터를 지우지 마세요. 노트북에서 불러오기가 끝나면 지워도 됩니다.</div></div>
      ${
        readyBuild
          ? `<div class="card stack" style="border-color:var(--blue)">
               <div style="font-weight:800">ZIP 준비 완료 · ${formatBytes(readyBuild.blob.size)}</div>
               <div class="tiny muted">${esc(readyBuild.filename)}</div>
               <button class="btn btn-primary btn-block" id="shareBtn" style="height:56px;font-size:17px">${icons.upload(22)}공유하기 (AirDrop · 메일)</button>
               <button class="btn btn-block" id="dlBtn">이 기기에 파일로 저장</button>
             </div>`
          : `<button class="btn btn-primary btn-block" id="buildBtn" style="height:56px;font-size:17px" ${counts.companies || counts.recordings ? "" : "disabled"}>${icons.upload(22)}ZIP 만들기</button>
             <div class="small muted" style="text-align:center;margin-top:-4px">${counts.companies || counts.recordings ? "만든 뒤 공유 시트에서 AirDrop · 메일 · 드라이브를 고르세요" : "오늘 수집한 내용이 아직 없어요"}</div>`
      }
      <div class="card"><div class="card-title">내보내기 기록</div>${logRows}</div>
    </div></div>`;

  bindHeader(root, trip, ctx);

  root.querySelector("#buildBtn")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "만드는 중…";
    try {
      const out = await buildDayZip(trip, day);
      built = { ...out, tripId: trip.id, day };
      ctx.rerender();
    } catch (err) {
      toast("ZIP을 만들지 못했어요: " + err.message, 5000);
      ctx.rerender();
    }
  });

  const done = async (how) => {
    if (how === "cancelled") return;
    await logExport(trip, day, readyBuild.counts, readyBuild.blob.size);
    toast(how === "shared" ? "공유했어요." : "파일로 저장했어요.");
    ctx.rerender();
  };
  root.querySelector("#shareBtn")?.addEventListener("click", async () => {
    done(await shareOrDownload(readyBuild.blob, readyBuild.filename));
  });
  root.querySelector("#dlBtn")?.addEventListener("click", () => {
    downloadBlob(readyBuild.blob, readyBuild.filename);
    done("downloaded");
  });
}

export function clearBuilt() {
  built = null;
}
