// 업체별 '확인할 질문' 편집기: 선택한 질문 목록 + 직접 입력 + 예상 질문 템플릿(분야별)
import { h } from "./core.js";

export const QUESTION_TEMPLATES = [
  { cat: "가격·납기", items: [
    "대략적인 가격대(단가)는 어느 정도인가요?",
    "최소 주문 수량(MOQ)이 있나요?",
    "주문 후 납기는 얼마나 걸리나요?",
    "한국 내 공급 방식(총판·대리점)과 가격 정책은 어떻게 되나요?",
    "렌탈·리스·PoC(시범 도입) 조건이 있나요?",
    "유지보수 비용과 소프트웨어 라이선스는 별도인가요?",
  ] },
  { cat: "기술 사양", items: [
    "핵심 사양(페이로드, 정밀도, 속도, 가동 범위)을 알려주세요.",
    "경쟁 제품 대비 가장 큰 차별점은 무엇인가요?",
    "지원하는 통신 프로토콜(EtherCAT, PROFINET, OPC UA 등)은 무엇인가요?",
    "최소 제어 주기(사이클 타임)는 얼마인가요?",
    "SDK/API는 어떤 언어(C++, Python, ROS2)를 지원하나요?",
    "동작 환경(온도, 방진·방수 등급, 전원)은 어떻게 되나요?",
    "연속 가동 시간과 MTBF(고장 간 평균 시간)는 얼마인가요?",
    "다음 세대 제품이나 로드맵이 있나요?",
  ] },
  { cat: "도입·적용", items: [
    "실제 도입 사례(레퍼런스)와 적용 산업을 알려주세요.",
    "조선·중공업·대형 구조물 현장에 적용된 사례가 있나요?",
    "열악한 환경(분진, 스패터, 진동)에서 검증한 결과가 있나요?",
    "기존 설비·제어기와의 연동은 어떻게 하나요?",
    "설치·셋업과 교육에 걸리는 시간은 얼마나 되나요?",
    "현장 PoC(시범 적용)를 함께 해볼 수 있나요?",
  ] },
  { cat: "파트너십·지원", items: [
    "한국 내 공식 대리점이나 서비스 거점이 있나요?",
    "A/S 대응 시간과 보증 기간은 어떻게 되나요?",
    "원격·현장 기술 지원과 부품 공급 정책은 어떤가요?",
    "공동 개발이나 커스터마이징이 가능한가요?",
    "담당자 연락처를 받고 후속 미팅을 잡을 수 있을까요?",
    "데모 영상·카탈로그·사양서를 받을 수 있나요?",
  ] },
  { cat: "안전·인증", items: [
    "보유 인증(CE, ISO 10218, ISO/TS 15066, UL 등)은 무엇인가요?",
    "협동 모드 안전 기능(충돌 감지, 속도·힘 제한)은 어떻게 구현되나요?",
    "기능안전 등급(PL, SIL)은 얼마인가요?",
    "한국 안전 인증(KC) 대응 계획이 있나요?",
  ] },
  { cat: "로봇", items: [
    "가반하중과 도달 범위(리치)는 얼마인가요?",
    "반복 정밀도는 어느 정도인가요?",
    "티칭(핸드가이딩, 오프라인 프로그래밍) 방식은 무엇인가요?",
    "(휴머노이드) 배터리 가동 시간과 충전 방식은 어떻게 되나요?",
    "(휴머노이드) 자유도(DoF), 손(그리퍼) 사양, 보행 안정성은 어떤가요?",
    "(AMR) 주행 방식(SLAM 등)과 최대 적재 중량·속도는 얼마인가요?",
  ] },
  { cat: "비전·센서", items: [
    "측정 정밀도·분해능·측정 범위는 얼마인가요?",
    "용접 아크광이나 반사면에서도 동작하나요?",
    "촬영·측정 주기(fps, 스캔 속도)는 얼마인가요?",
    "캘리브레이션(핸드아이) 절차와 소요 시간은 어떻게 되나요?",
    "로봇 제어기 연동용 드라이버·라이브러리를 제공하나요?",
  ] },
  { cat: "제어·통신", items: [
    "EtherCAT 마스터/슬레이브 지원 범위와 지터 성능은 어떤가요?",
    "지원하는 모션 제어 방식(CSP/CSV/CST)은 무엇인가요?",
    "실시간 OS(RT-Linux, Xenomai 등) 요구사항이 있나요?",
    "타사 서보·드라이브와의 호환성은 어떤가요?",
  ] },
  { cat: "용접", items: [
    "용접선 자동 추적(심 트래킹) 방식과 정확도는 어떤가요?",
    "용접 조건(전류·전압·속도) 자동 설정이 되나요?",
    "수직·상향 등 자세별 용접 품질은 어떤가요?",
    "이동식 용접 로봇의 설치·이동 방법과 소요 시간은 얼마인가요?",
  ] },
  { cat: "SW·AI", items: [
    "사용하는 AI 모델과 학습 데이터는 어떻게 확보하나요?",
    "온프레미스(폐쇄망) 운영이 가능한가요?",
    "소프트웨어 업데이트와 라이선스 정책은 어떻게 되나요?",
    "시뮬레이션·디지털 트윈 연동을 지원하나요?",
  ] },
];

// initial: 이미 있는 질문 문자열 배열. get() 은 비어 있지 않은 질문을 순서대로 돌려준다.
export function questionPicker(initial = []) {
  let list = initial.map((x) => String(x).trim()).filter(Boolean);
  let cat = QUESTION_TEMPLATES[0].cat;
  const box = h("div", { class: "qpick" });
  const norm = (t) => t.replace(/\s+/g, " ").trim().toLowerCase();
  const has = (t) => list.some((x) => norm(x) === norm(t));
  const add = (t) => { t = String(t).trim(); if (t && !has(t)) { list.push(t); paint(); } };
  const remove = (i) => { list.splice(i, 1); paint(); };
  const move = (i, d) => { const j = i + d; if (j < 0 || j >= list.length) return; [list[i], list[j]] = [list[j], list[i]]; paint(); };

  function paint() {
    const rows = list.length
      ? list.map((t, i) => h("div", { class: "qrow" },
          h("span", { class: "qn" }, String(i + 1)),
          h("input", { value: t, "aria-label": `질문 ${i + 1}`, oninput: (e) => { list[i] = e.target.value; } }),
          h("button", { class: "btn sm ghost", type: "button", "aria-label": `질문 ${i + 1} 위로`, disabled: i === 0, onclick: () => move(i, -1) }, "▲"),
          h("button", { class: "btn sm ghost", type: "button", "aria-label": `질문 ${i + 1} 아래로`, disabled: i === list.length - 1, onclick: () => move(i, 1) }, "▼"),
          h("button", { class: "btn sm ghost", type: "button", "aria-label": `질문 ${i + 1} 삭제`, onclick: () => remove(i) }, "×")))
      : [h("div", { class: "sub" }, "아직 질문이 없어요. 아래 예상 질문에서 고르거나 직접 입력하세요.")];
    const custom = h("input", { placeholder: "직접 입력 후 Enter 또는 추가", "aria-label": "질문 직접 입력", onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); add(custom.value); } } });
    const tabs = h("div", { class: "qcats", role: "tablist" }, ...QUESTION_TEMPLATES.map((g) =>
      h("button", { class: "chip" + (g.cat === cat ? " on" : ""), type: "button", role: "tab", "aria-selected": String(g.cat === cat), onclick: () => { cat = g.cat; paint(); } }, g.cat)));
    const cur = QUESTION_TEMPLATES.find((g) => g.cat === cat);
    const tpl = h("div", { class: "qtpl" }, ...cur.items.map((t) => {
      const on = has(t);
      return h("button", { class: "qt" + (on ? " on" : ""), type: "button", "aria-pressed": String(on), onclick: () => (on ? remove(list.findIndex((x) => norm(x) === norm(t))) : add(t)) },
        h("span", { class: "qk", "aria-hidden": "true" }, on ? "✓" : "+"), t);
    }));
    const keep = document.activeElement && box.contains(document.activeElement) && document.activeElement.tagName === "INPUT" && document.activeElement.getAttribute("aria-label") === "질문 직접 입력";
    box.replaceChildren(
      h("div", { class: "qlist" }, ...rows),
      h("div", { class: "row", style: "gap:6px" }, h("div", { class: "grow" }, custom), h("button", { class: "btn sm", type: "button", onclick: () => add(custom.value) }, "추가")),
      h("div", { class: "qhead" }, h("b", {}, "예상 질문 (눌러서 추가 · 다시 누르면 빼요)"), h("span", { class: "sub" }, `${list.length}개 선택됨`)),
      tabs, tpl);
    if (keep) custom.focus();
  }
  paint();
  return { el: box, get: () => list.map((x) => x.trim()).filter(Boolean) };
}
