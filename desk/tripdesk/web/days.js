import { h, api, toast, guard, modal, promptModal, download, marked, fmtDur, fmtDate } from "./core.js";

const kpi = (label, val, note, accent) => h("div", { class: "kpi" + (accent ? " accent" : "") }, h("span", {}, label), h("b", {}, val), h("em", {}, note));
const fmtHours = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}시간 ${Math.round((s % 3600) / 60)}분` : `${Math.round(s / 60)}분`);

// =============== 일간 import ===============
export async function importView(root, tid, app) {
  const [{ days }, eng, tripView] = await Promise.all([api("GET", `/trips/${tid}/days`), api("GET", "/transcribe"), api("GET", `/trips/${tid}`)]);
  const trip = tripView.trip;
  const got = days.filter((d) => d.imported);
  const rec = got.reduce((a, d) => a + d.recordings, 0), tr = got.reduce((a, d) => a + d.transcribed, 0);
  const secs = got.reduce((a, d) => a + d.audioSeconds, 0);

  const prog = h("div", { class: "bar", style: "display:none" }, h("i", { style: "width:0" }));
  const progText = h("div", { class: "sub" });
  const zip = h("input", { type: "file", accept: ".zip", style: "display:none", onchange: () => { if (zip.files[0]) upload(zip.files[0]); zip.value = ""; } });
  const drop = h("div", { class: "drop", ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); }, ondragleave: () => drop.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) upload(f); } },
    h("b", { style: "font-size:17px" }, "폰에서 내보낸 하루치 ZIP을 여기에 놓으세요"),
    h("div", { class: "sub" }, "Trip Field → 내보내기로 만든 파일이에요. 여러 일차가 든 ZIP도, 같은 날 다시 내보낸 ZIP도 괜찮아요(이미 전사한 내용은 유지돼요)."),
    h("div", { class: "row" }, zip, h("button", { class: "btn primary", onclick: () => zip.click() }, "ZIP 파일 선택")), prog, progText);

  function upload(file) {
    prog.style.display = "";
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/trips/${tid}/days/import`);
    xhr.setRequestHeader("X-TripDesk", "1");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) { prog.firstChild.style.width = (e.loaded / e.total) * 100 + "%"; progText.textContent = `올리는 중… ${(e.loaded / 1048576).toFixed(0)}MB / ${(e.total / 1048576).toFixed(0)}MB`; } };
    xhr.onload = () => {
      let j = {};
      try { j = JSON.parse(xhr.responseText); } catch {}
      prog.style.display = "none";
      if (xhr.status !== 200) { progText.textContent = ""; return toast(j.error || "가져오지 못했어요.", true); }
      const r = j.imported.map((d) => `${d.day}일차(업체 ${d.companies}곳, 녹음 ${d.recordings}건)`).join(", ");
      toast("가져왔어요: " + r);
      app.go(`#/import/${tid}`);
      app.refreshSide();
    };
    xhr.onerror = () => { prog.style.display = "none"; toast("올리지 못했어요. Trip Desk 가 켜져 있는지 확인해 주세요.", true); };
    progText.textContent = "올리는 중…";
    xhr.send(file);
  }

  const model = h("select", {}, ...eng.models.map((m) => h("option", { value: m }, m)));
  model.value = eng.model;
  const lang = h("select", {}, ...Object.entries(eng.languages).map(([k, v]) => h("option", { value: k }, v)));
  const redo = h("input", { type: "checkbox", id: "redo" });

  const engine = h("div", { class: "card" }, h("h3", {}, "음성 인식 (이 컴퓨터에서 실행)"),
    eng.available ? h("div", { class: "pill ok", style: "align-self:flex-start" }, "faster-whisper 사용 가능") : h("div", { class: "msg warn" }, eng.reason),
    h("div", { class: "row" },
      h("div", { class: "field", style: "width:130px" }, h("label", {}, "모델"), model),
      h("div", { class: "field", style: "width:130px" }, h("label", {}, "언어"), lang),
      h("label", { class: "check", style: "align-self:flex-end;height:40px" }, redo, "이미 한 것도 다시")),
    h("div", { class: "sub" }, "small 은 빠르고 가벼워요. 한국어 정확도가 아쉬우면 medium·large-v3 를 쓰세요(느리고 무거워요). 처음 한 번은 모델 내려받기에 인터넷이 필요해요. 용어집이 인식 힌트로 쓰여요. 녹음은 이 컴퓨터 밖으로 나가지 않아요."));

  const cards = days.map((d, i) => {
    const n = i + 1;
    if (!d.imported) return h("div", { class: "daycard none" }, h("h3", {}, `Day ${n}`, h("span", { class: "pill gray" }, "아직 안 가져옴")), h("div", { class: "sub" }, fmtDate(trip.days[i])));
    const status = h("div", { class: "sub", id: `st${n}` });
    const btn = h("button", { class: "btn sm primary", disabled: !eng.available || !d.recordings, onclick: () => guard(async () => {
      await api("POST", `/trips/${tid}/days/${n}/transcribe`, { language: lang.value, model: model.value, redo: redo.checked });
      toast("전사를 시작했어요. 다른 화면으로 가도 계속돼요.");
      watch(n, status);
    }) }, d.transcribed === d.recordings && d.recordings ? "다시 전사" : "전사 시작");
    if (!eng.available) btn.title = "음성 인식 엔진이 설치되어 있지 않아요";
    const pct = d.recordings ? (d.transcribed / d.recordings) * 100 : 0;
    setTimeout(() => poll(n, status, false), 0);
    return h("div", { class: "daycard" },
      h("h3", {}, `Day ${n} · ${fmtDate(d.date)}`, h("span", { class: "pill ok" }, "가져옴")),
      h("div", { class: "stat" }, h("span", {}, "업체 ", h("b", {}, d.companies)), d.newCompanies ? h("span", {}, "현장 추가 ", h("b", {}, d.newCompanies)) : null,
        h("span", {}, "녹음 ", h("b", {}, d.recordings), ` (${fmtHours(d.audioSeconds)})`), h("span", {}, "메모 ", h("b", {}, d.memos)), h("span", {}, "사진 ", h("b", {}, d.photos))),
      h("div", {}, h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "sub" }, `전사 ${d.transcribed}/${d.recordings}`), h("span", { class: "sub" }, `교정 ${d.corrected}/${d.recordings}`)),
        h("div", { class: "bar" }, h("i", { style: `width:${pct}%` }))),
      status,
      h("div", { class: "row" }, btn, h("a", { class: "btn sm", href: `#/daily/${tid}/${n}` }, "보고서 보기 →")));
  });

  function poll(n, el, seen) {
    api("GET", `/trips/${tid}/days/${n}/transcribe`).then((r) => {
      const j = r.job;
      if (j.status === "running") { el.textContent = j.message; app.poll(() => poll(n, el, true), 1500); }
      else if (j.status !== "idle") {
        el.textContent = j.message;
        if (seen) { toast(j.message, j.status === "error"); app.go(`#/import/${tid}`); app.refreshSide(); }  // 방금까지 돌던 작업이 끝났으면 숫자를 새로 그린다
      }
    }).catch(() => {});
  }
  const watch = (n, el) => app.poll(() => poll(n, el, true), 1200);

  root.replaceChildren(
    h("div", { class: "top" }, h("h1", {}, "일간 import"), h("span", { class: "pill" }, `${got.length}/${days.length}일 가져옴`)),
    h("div", { class: "kpis" }, kpi("가져온 일차", `${got.length}/${days.length}`, "폰에서 내보낸 날"), kpi("녹음", rec, got.length ? fmtHours(secs) : "—"),
      kpi("전사 완료", `${tr}/${rec}`, rec ? `${Math.round((tr / rec) * 100)}%` : "—", true),
      kpi("메모·사진", `${got.reduce((a, d) => a + d.memos, 0)} · ${got.reduce((a, d) => a + d.photos, 0)}`, "가져온 합계")),
    drop, engine, h("div", { class: "daygrid" }, ...cards));
}

// =============== 일간 보고서 ===============
const D = { cid: null, ri: 0 };

export async function dailyView(root, tid, n, app) {
  const [{ days }, tripView] = await Promise.all([api("GET", `/trips/${tid}/days`), api("GET", `/trips/${tid}`)]);
  if (D.key !== tid + ":" + n) Object.assign(D, { key: tid + ":" + n, cid: null, ri: 0 });
  const tabs = h("div", { class: "row" }, ...days.map((d, i) => h("a", { class: "btn sm" + (i + 1 === n ? " primary" : ""), style: d.imported || i + 1 === n ? "" : "opacity:.5", href: `#/daily/${tid}/${i + 1}` }, `Day ${i + 1}`)));
  let rep;
  try {
    rep = (await api("GET", `/trips/${tid}/days/${n}`)).report;
  } catch (e) {
    return root.replaceChildren(h("div", { class: "top" }, h("h1", {}, `Day ${n} 일간 보고서`), tabs),
      h("div", { class: "panel" }, h("div", { class: "empty" }, h("b", {}, `${n}일차 데이터를 아직 가져오지 않았어요`), h("div", {}, "폰에서 내보낸 ZIP을 먼저 가져오세요."), h("a", { class: "btn primary", href: `#/import/${tid}` }, "일간 import 로 이동"))));
  }
  const st = rep.stats;
  const cur = rep.companies.find((c) => c.id === D.cid) || rep.companies[0];
  D.cid = cur?.id;
  const reload = () => { const y = window.scrollY; dailyView(root, tid, n, app).then(() => window.scrollTo(0, y)); app.refreshSide(); };
  D.reload = reload;
  const base = `/api/trips/${tid}/days/${n}/file/`;

  const list = h("div", { class: "list" }, h("h4", {}, `방문 업체 ${rep.companies.length}곳`),
    ...rep.companies.map((c) => h("button", { class: "li" + (c.id === D.cid ? " on" : ""), onclick: () => { D.cid = c.id; D.ri = 0; reload(); } },
      h("div", { class: "row", style: "gap:6px" }, h("b", {}, c.name), c.addedOnSite ? h("span", { class: "tag" }, "현장 추가") : null),
      h("span", {}, [c.recordings.length ? `녹음 ${c.recordings.length}` : "", c.memos.length ? `메모 ${c.memos.length}` : "", c.photos.length ? `사진 ${c.photos.length}` : ""].filter(Boolean).join(" · ") || "기록 없음"))),
    h("div", { class: "grow" }), h("div", { class: "sub", style: "padding:8px;line-height:1.5" }, rep.tomorrow ? "아래 '내일 계획'에 이어져요" : ""));

  const mid = h("div", { class: "mid" });
  if (!cur) mid.append(h("div", { class: "empty" }, "방문 기록이 없어요."));
  else if (!cur.recordings.length) {
    mid.append(h("h3", { style: "margin:0" }, cur.name), h("div", { class: "sub" }, "이 업체에는 녹음이 없어요. 메모와 사진은 오른쪽 보고서에 들어가요."));
  } else {
    const r = cur.recordings[Math.min(D.ri, cur.recordings.length - 1)];
    const rawTa = () => editBox("전사 원문 수정", r.text, (v) => api("PUT", `/trips/${tid}/days/${n}/recording`, { file: r.file, text: v }));
    mid.append(
      h("div", { class: "row", style: "justify-content:space-between" }, h("div", {}, h("h3", { style: "margin:0;font-size:15px" }, `${cur.name} · ${D.ri + 1}번째 녹음`),
        h("div", { class: "sub" }, `${r.time} · ${fmtDur(r.durationSec)}${r.engine ? " · " + r.engine : ""}`))),
      h("audio", { controls: true, preload: "none", src: base + r.file.split("/").map(encodeURIComponent).join("/") }),
      h("div", { class: "field" }, h("div", { class: "row", style: "justify-content:space-between" }, h("label", {}, "전사 (원문)"), h("button", { class: "btn sm ghost", onclick: rawTa }, r.text ? "수정" : "직접 입력")),
        r.text ? h("div", { class: "box raw" }, r.text) : h("div", { class: "msg warn" }, "아직 전사가 없어요. '일간 import' 화면에서 전사를 시작하거나, 직접 입력할 수 있어요.")),
      h("div", { class: "divider" }, h("span", { class: "pill", style: "font-size:12px" }, "AI 교정 · 용어집 + 사전조사 메모")),
      h("div", { class: "field" }, h("div", { class: "row", style: "justify-content:space-between" }, h("label", {}, "교정본"), h("button", { class: "btn sm ghost", onclick: () => editBox("교정본 수정", r.corrected || r.text, (v) => api("PUT", `/trips/${tid}/days/${n}/recording`, { file: r.file, corrected: v })) }, "직접 수정")),
        r.corrected ? h("div", { class: "box fix" }, marked(r.corrected)) : h("div", { class: "sub" }, r.text ? "아직 교정 전이에요. 아래 'AI 교정·요약' 으로 프롬프트를 만들어 Claude Chat 에 물어보세요." : "전사가 있어야 교정할 수 있어요.")),
      h("div", { class: "legend" }, h("div", {}, h("i", { style: "background:var(--blue-bg);border:1px solid var(--blue)" }), "용어집·문맥으로 교정한 부분"), h("div", {}, h("i", { style: "background:var(--orange-bg);border:1px solid var(--orange)" }), "사람이 확인해야 하는 부분")),
      h("div", { class: "grow" }),
      cur.recordings.length > 1 ? h("div", { class: "row" }, ...cur.recordings.map((x, i) => h("button", { class: "btn sm" + (i === D.ri ? " primary" : ""), onclick: () => { D.ri = i; reload(); } }, `${i + 1}번째 ${x.time}`))) : null);
  }

  const pointsFor = (c) => c.points.length ? h("ul", {}, ...c.points.map((p) => h("li", {}, marked(p))))
    : c.recordings.some((r) => r.text) ? h("div", {}, h("div", { class: "sub" }, "AI 정리 전 — 교정본(없으면 전사 원문)을 그대로 보여요"),
      ...c.recordings.filter((r) => r.corrected || r.text).map((r) => h("div", { class: "box raw", style: "margin-top:4px;font-size:13px" }, `${r.time} · `, marked(r.corrected || r.text)))) : null;

  const prev = h("div", { class: "prev" },
    h("div", { class: "row", style: "justify-content:space-between" }, h("span", { class: "sub", style: "font-weight:800" }, "일간 보고서 미리보기"), h("span", { class: "pill" + (rep.summaryIsAi ? "" : " gray"), style: "font-size:12px;padding:3px 10px" }, rep.summaryIsAi ? "AI 요약 반영" : "자동 집계")),
    h("h2", {}, `${fmtDate(rep.date)} · 출장 ${n}일차`),
    h("div", {}, h("div", { class: "row", style: "justify-content:space-between" }, h("h4", {}, "오늘 요약"), h("button", { class: "btn sm ghost", onclick: () => editBox("오늘 요약 수정", rep.summary, (v) => api("PUT", `/trips/${tid}/days/${n}/report`, { summary: v })) }, "수정")), h("div", { style: "line-height:1.6" }, marked(rep.summary))),
    ...rep.companies.map((c) => h("div", {}, h("div", { class: "row", style: "justify-content:space-between" }, h("h4", {}, `${c.name} · ${c.category || "기타"}`, c.addedOnSite ? h("span", { class: "tag" }, "현장 추가") : null),
      h("button", { class: "btn sm ghost", onclick: () => editBox(`${c.name} 핵심 내용 수정 (한 줄에 하나)`, c.points.join("\n"), (v) => api("PUT", `/trips/${tid}/days/${n}/report`, { points: { [c.id]: v.split("\n") } })) }, "수정")),
      pointsFor(c),
      c.memos.length ? h("div", { style: "margin-top:6px" }, h("div", { class: "sub", style: "font-weight:800" }, "내 메모 · 원문 그대로"), ...c.memos.map((m) => h("div", { class: "box memo", style: "margin-top:4px" }, (m.important ? "★ " : "") + m.text))) : null,
      c.photos.length ? h("div", { class: "photos", style: "margin-top:6px" }, ...c.photos.slice(0, 8).map((p) => h("img", { loading: "lazy", alt: "", src: base + p.file.split("/").map(encodeURIComponent).join("/") })), c.photos.length > 8 ? h("span", { class: "sub" }, `+${c.photos.length - 8}`) : null) : null)),
    h("div", {}, h("div", { class: "row", style: "justify-content:space-between" }, h("h4", {}, "내일 계획"), h("button", { class: "btn sm ghost", onclick: () => editBox("내일 계획 수정", rep.tomorrow, (v) => api("PUT", `/trips/${tid}/days/${n}/report`, { tomorrow: v })) }, "수정")), h("div", { style: "line-height:1.6" }, rep.tomorrow || h("span", { class: "sub" }, "배정된 다음 일정이 없어요."))),
    rep.checks.length ? h("div", { class: "msg warn" }, h("b", {}, `확인 필요 ${rep.checks.length}건`), h("ul", { style: "margin:4px 0 0;padding-left:18px" }, ...rep.checks.map((c) => h("li", {}, `${c.company}: ${c.text}`)))) : null,
    h("div", { class: "grow" }),
    h("div", { class: "row" },
      h("button", { class: "btn", style: "flex:1 1 auto", onclick: openAi }, "AI 교정·요약"),
      h("button", { class: "btn primary", style: "flex:1 1 auto", onclick: () => saveMenu() }, "Word 저장"),
      h("button", { class: "btn", onclick: () => download(`/trips/${tid}/days/${n}/report.md`) }, "Markdown")));

  function saveMenu() { download(`/trips/${tid}/days/${n}/report.docx`); }
  function openAi() {
    promptModal({
      title: `Day ${n} 교정·요약 (Claude Chat 용)`,
      intro: "전사본에 용어집·사전조사 메모를 붙여 만든 프롬프트예요. Claude 가 고친 부분은 파랑, 불확실한 부분은 [확인필요: …] 주황으로 표시돼요. AI가 한 일은 눈으로 확인하세요 — 내 메모는 건드리지 않아요.",
      getPrompts: async () => (await api("POST", `/trips/${tid}/days/${n}/prompt`, {})).prompts,
      onPaste: async (text, mode) => {
        const r = await api("POST", `/trips/${tid}/days/${n}/paste`, { text, mode });
        const a = r.applied;
        toast(`교정 ${a.recordings}건, 업체 요약 ${a.companies}곳` + (a.summary ? ", 하루 요약" : "") + (a.ignored ? ` · 맞지 않아 건너뜀 ${a.ignored}` : "") + " 반영");
        reload();
      },
    });
  }

  root.replaceChildren(
    h("div", { class: "top" }, h("div", { class: "row", style: "gap:14px" }, h("h1", {}, `Day ${n} 일간 보고서`),
      h("span", { class: "pill" }, `업체 ${st.companies}곳 · 녹음 ${st.recordings}건 · 전사 ${st.transcribed}/${st.recordings} · 교정 ${st.corrected}/${st.recordings}`)), tabs),
    h("div", { class: "dayrow" }, list, mid, prev));
}

function editBox(title, value, save) {
  modal(title, (m, close) => {
    const ta = h("textarea", { style: "min-height:220px", value: value || "" });
    m.append(ta, h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: close }, "취소"),
      h("button", { class: "btn primary", onclick: async () => { const ok = await guard(async () => { await save(ta.value); return true; }); if (ok) { close(); D.reload?.(); } } }, "저장")));
    ta.focus();
  });
}

// =============== 최종 보고서 ===============
export async function finalView(root, tid, app) {
  const { report: r } = await api("GET", `/trips/${tid}/final`);
  const t = r.totals;
  const reload = () => finalView(root, tid, app);
  const f = r.final;
  const sec = (title, ...kids) => h("div", { class: "card" }, h("h3", {}, title), ...kids);
  const list = (items) => items.length ? h("ul", { style: "margin:0;padding-left:18px;line-height:1.7" }, ...items.map((x) => h("li", {}, marked(x)))) : null;
  if (!r.days.length) {
    return root.replaceChildren(h("div", { class: "top" }, h("h1", {}, "최종 보고서")),
      h("div", { class: "panel" }, h("div", { class: "empty" }, h("b", {}, "가져온 일간 데이터가 없어요"), h("div", {}, "폰에서 내보낸 하루치 ZIP을 먼저 가져오세요."), h("a", { class: "btn primary", href: `#/import/${tid}` }, "일간 import 로 이동"))));
  }
  const editFinal = () => modal("총평 직접 쓰기", (m, close) => {
    const ov = h("textarea", { value: f.overview, style: "min-height:130px" });
    const hi = h("textarea", { value: f.highlights.join("\n"), style: "min-height:110px" });
    const fo = h("textarea", { value: f.followups.join("\n"), style: "min-height:110px" });
    const fld = (l, e) => h("div", { class: "field" }, h("label", {}, l), e);
    m.append(fld("총평", ov), fld("주요 발견 (한 줄에 하나)", hi), fld("후속 조치 (한 줄에 하나)", fo),
      h("div", { class: "row", style: "justify-content:flex-end" }, h("button", { class: "btn", onclick: close }, "취소"), h("button", { class: "btn primary", onclick: () => guard(async () => {
        await api("PUT", `/trips/${tid}/final`, { overview: ov.value, highlights: hi.value.split("\n"), followups: fo.value.split("\n") });
        close(); reload();
      }) }, "저장")));
  });
  const openPrompt = () => promptModal({
    title: "최종 총평 (Claude Chat 용)",
    intro: "일자별 요약과 업체별 핵심 내용, 내 메모를 모아 총평·주요 발견·후속 조치를 쓰게 하는 프롬프트예요. 일간 보고서에서 교정·요약을 먼저 끝내 두면 결과가 좋아요.",
    getPrompts: async () => [(await api("POST", `/trips/${tid}/final/prompt`, {})).prompt],
    onPaste: async (text) => { await api("POST", `/trips/${tid}/final/paste`, { text }); toast("총평을 반영했어요."); reload(); },
  });
  root.replaceChildren(
    h("div", { class: "top" }, h("div", { class: "row", style: "gap:14px" }, h("h1", {}, "최종 보고서"), h("span", { class: "pill" }, `${r.dates[0]} ~ ${r.dates[r.dates.length - 1]}`)),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => download(`/trips/${tid}/final.docx`) }, "Word 로 저장"), h("button", { class: "btn", onclick: () => download(`/trips/${tid}/final.md`) }, "Markdown"))),
    h("div", { class: "kpis" }, kpi("가져온 일차", `${t.days}/${r.dates.length}`, "일간 데이터"), kpi("방문 업체", t.companies, t.newCompanies ? `현장 추가 ${t.newCompanies}곳` : "계획대로", true),
      kpi("녹음", t.recordings, fmtHours(t.audioSeconds)), kpi("메모", t.memos, "원문 그대로 수록"), kpi("사진", t.photos, "일간 Word 에 포함")),
    sec("총평", f.overview ? h("div", { style: "line-height:1.7;white-space:pre-wrap" }, marked(f.overview)) : h("div", { class: "msg" }, "아직 총평이 없어요. 'AI 총평 프롬프트'로 만들거나 직접 쓸 수 있어요."),
      f.highlights.length ? h("div", {}, h("h4", {}, "주요 발견"), list(f.highlights)) : null, f.followups.length ? h("div", {}, h("h4", {}, "후속 조치"), list(f.followups)) : null,
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: openPrompt }, "AI 총평 프롬프트"), h("button", { class: "btn", onclick: editFinal }, "직접 쓰기/수정"))),
    sec("일자별 요약", ...r.days.map((d) => h("div", {}, h("div", { class: "row", style: "justify-content:space-between" }, h("h4", { style: "color:var(--ink)" }, `${d.day}일차 · ${fmtDate(d.date)}`), h("a", { class: "btn sm ghost", href: `#/daily/${tid}/${d.day}` }, "일간 보고서 →")), h("div", { style: "line-height:1.6" }, marked(d.summary))))),
    sec(`업체별 정리 (${r.companies.length}곳)`, ...r.companies.map((c) => h("div", { style: "border-top:1px solid var(--line2);padding-top:10px" },
      h("h4", { style: "color:var(--ink);font-size:14px" }, c.name, h("span", { class: "sub" }, ` · ${c.category || "기타"}`), c.addedOnSite ? h("span", { class: "tag" }, "현장 추가") : null),
      ...c.visits.map((v) => h("div", {}, h("div", { class: "sub", style: "font-weight:800" }, `${v.day}일차`), list(v.points), ...v.memos.map((m) => h("div", { class: "box memo", style: "margin-top:4px" }, "메모: " + m.text))))))),
    r.notVisited.length ? sec("방문하지 못한 계획 업체", h("div", {}, r.notVisited.join(", "))) : null,
    r.checks.length ? h("div", { class: "msg warn" }, h("b", {}, `확인 필요 ${r.checks.length}건`), h("ul", { style: "margin:4px 0 0;padding-left:18px" }, ...r.checks.map((c) => h("li", {}, `${c.day}일차 ${c.company}: ${c.text}`)))) : null);
}
