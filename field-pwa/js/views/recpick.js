// 녹음 탭: 어느 업체를 녹음할지 고른다 (최근에 다룬 업체가 위로)
import { esc, icons } from "../ui.js";
import { companiesForDay, isVisited } from "../model.js";
import * as db from "../db.js";
import { headerHtml, bindHeader, openAddCompany } from "./shared.js";

export async function renderRecPick(root, ctx) {
  const { trip, day, companies } = ctx;
  const recs = (await db.getAllByIndex("recordings", "tripId", trip.id)).filter((r) => r.status === "done");
  const lastAt = new Map();
  for (const r of recs) lastAt.set(r.companyId, Math.max(lastAt.get(r.companyId) || 0, r.createdAt));
  for (const c of companies) for (const v of c.visits || []) lastAt.set(c.id, Math.max(lastAt.get(c.id) || 0, v.at));

  const today = companiesForDay(companies, day);
  const rest = companies.filter((c) => !today.includes(c));
  const byRecent = (a, b) => (lastAt.get(b.id) || 0) - (lastAt.get(a.id) || 0);
  today.sort(byRecent);
  rest.sort(byRecent);

  const countOf = (id) => recs.filter((r) => r.companyId === id).length;
  const row = (c) => `
    <button class="item" data-open="${c.id}">
      <span class="round" style="border-color:${isVisited(c, day) ? "var(--ink)" : "#c3cbd5"}">${icons.mic(20)}</span>
      <span class="item-main"><span class="item-name">${esc(c.name)}</span><span class="item-sub">${esc([c.hall && `홀 ${c.hall}`, c.booth && `부스 ${c.booth}`, c.category].filter(Boolean).join(" · "))}</span></span>
      ${countOf(c.id) ? `<span class="pill pill-blue">녹음 ${countOf(c.id)}</span>` : ""}
    </button>`;

  root.innerHTML = `
    ${headerHtml(trip, day)}
    <div class="header" style="padding-top:0"><div class="title" style="font-size:20px">어느 업체를 녹음할까요?</div></div>
    <div class="scroll">
      <button class="btn btn-primary btn-block" id="addBtn">${icons.plus(18)}새 업체 추가하고 녹음</button>
      ${today.length ? `<div class="group-title">오늘</div><div class="list-card">${today.map(row).join("")}</div>` : ""}
      ${rest.length ? `<div class="group-title">다른 날 후보</div><div class="list-card">${rest.map(row).join("")}</div>` : ""}
    </div>`;

  bindHeader(root, trip, ctx);
  root.querySelector("#addBtn").onclick = () => openAddCompany(ctx);
  root.querySelectorAll("[data-open]").forEach((b) => {
    b.onclick = () => (location.hash = `#/company/${b.dataset.open}`);
  });
}
