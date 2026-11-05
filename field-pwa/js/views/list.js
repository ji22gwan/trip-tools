// 오늘의 방문 리스트
import { esc, icons } from "../ui.js";
import { companiesForDay, groupByCategory, isVisited, setVisited } from "../model.js";
import * as db from "../db.js";
import { headerHtml, bindHeader, openAddCompany, openSession, dupBadge } from "./shared.js";

let filter = "today";

export async function renderList(root, ctx) {
  const { trip, day, companies } = ctx;
  const shown = filter === "today" ? companiesForDay(companies, day) : companies;
  const planned = shown.filter((c) => !c.addedOnSite);
  const done = planned.filter((c) => isVisited(c, day)).length;
  const onsite = shown.filter((c) => c.addedOnSite).length;
  const pct = planned.length ? Math.round((done / planned.length) * 100) : 0;

  const groups = groupByCategory(shown);
  const rowHtml = (c) => {
    const visited = isVisited(c, day);
    const place = [c.hall && `홀 ${c.hall}`, c.booth && `부스 ${c.booth}`].filter(Boolean).join(" · ");
    const note = c.addedOnSite ? "현장 추가" : c.preNotes ? c.preNotes.split("\n")[0] : "";
    const dupHtml = dupBadge(c, companies);
    return `
      <div class="item ${visited ? "done" : ""}" data-open="${c.id}" role="button" tabindex="0">
        <button class="check ${visited ? "on" : ""}" data-toggle="${c.id}" aria-label="${esc(c.name)} 방문 ${visited ? "취소" : "체크"}" aria-pressed="${visited}">${visited ? `<span style="color:#fff">${icons.check(18)}</span>` : ""}</button>
        <div class="item-main"><div class="item-name">${esc(c.name)}${dupHtml.pill}</div><div class="item-sub">${esc([place, note].filter(Boolean).join(" · ") || "정보 없음")}</div>${dupHtml.line}</div>
        <span class="muted" aria-hidden="true">›</span>
      </div>`;
  };

  const date = trip.days[day - 1];
  const todaySessions = (trip.sessions || []).filter((x) => x.date === date);
  const sessHtml = todaySessions.length
    ? `<div class="group-title">오늘 세션 · ${todaySessions.length}개</div><div class="list-card">${todaySessions
        .map((x) => `<div class="item" data-sess="${esc(x.id)}" role="button" tabindex="0"><div class="item-main"><div class="item-name"><span style="color:var(--orange);font-weight:800">${esc(x.start || "시간 미정")}${x.end ? "~" + esc(x.end) : ""}</span> ${esc(x.title)}${x.going ? ` <span class="pill pill-blue">참석</span>` : ""}</div><div class="item-sub">${esc([x.place, x.hall && `홀 ${x.hall}`, x.speaker].filter(Boolean).join(" · ") || "장소 미정")}</div></div><span class="muted" aria-hidden="true">›</span></div>`)
        .join("")}</div>`
    : "";

  root.innerHTML = `
    ${headerHtml(trip, day)}
    <div class="header" style="padding-top:0;gap:8px">
      <div class="row" style="justify-content:space-between"><div class="title" style="font-size:20px">방문 리스트</div>
        <div class="seg"><button class="${filter === "today" ? "on" : ""}" data-f="today">오늘</button><button class="${filter === "all" ? "on" : ""}" data-f="all">전체</button></div></div>
      <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:700"><span>${planned.length}곳 중 ${done}곳 완료</span><span style="color:var(--orange)">현장 추가 ${onsite}곳</span></div>
      <div class="progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
    </div>
    <div class="scroll">
      ${sessHtml}
      ${
        groups.length
          ? groups.map((g) => `<div class="group-title">${esc(g.title)} · ${g.items.length}곳</div><div class="list-card ${g.title === "현장 추가" ? "dashed" : ""}">${g.items.map(rowHtml).join("")}</div>`).join("")
          : `<div class="card" style="margin-top:12px;text-align:center;color:var(--sub)">${filter === "today" ? "오늘 방문할 업체가 없어요. 전체 보기에서 확인하거나 업체를 추가해 보세요." : "아직 업체가 없어요."}</div>`
      }
      <button class="btn btn-block" id="addBtn" style="margin-top:16px">${icons.plus(18)}업체 추가</button>
    </div>`;

  bindHeader(root, trip, ctx);
  root.querySelectorAll("[data-f]").forEach((b) => {
    b.onclick = () => {
      filter = b.dataset.f;
      ctx.rerender();
    };
  });
  root.querySelector("#addBtn").onclick = () => openAddCompany(ctx);
  root.querySelectorAll("[data-sess]").forEach((row) => {
    row.onclick = () => openSession(todaySessions.find((x) => x.id === row.dataset.sess), trip, () => ctx.rerender());
  });

  root.querySelectorAll("[data-open]").forEach((row) => {
    const open = () => (location.hash = `#/company/${row.dataset.open}`);
    row.addEventListener("click", (e) => {
      if (e.target.closest("[data-toggle]")) return;
      open();
    });
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter") open();
    });
  });
  root.querySelectorAll("[data-toggle]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const c = await db.get("companies", btn.dataset.toggle);
      await setVisited(c, day, !isVisited(c, day));
      ctx.rerender();
    };
  });
}
