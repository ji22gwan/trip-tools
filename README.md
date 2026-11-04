# Trip Tools

> 📖 **[사용 매뉴얼 보기 (Trip Desk + Trip Field, 화면 캡처 포함)](docs/manual/MANUAL.md)** — 설치부터 사전조사 · 현장 · 보고서까지 모든 화면을 가상 데이터로 설명해요.

출장·전시회에서 정보를 모으고 보고서까지 이어 가기 위한 도구 모음입니다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| `field-pwa/` | 폰 앱 **Trip Field** (PWA). 맵 보기, 방문 체크, 업체별 녹음·메모·사진, 번역, 하루치 내보내기 | 1차 완성 |
| `worker/` | 번역 중계 서버 (Cloudflare Worker + Gemini). 키를 앱 밖에 숨깁니다 | 1차 완성 |
| `sample/` | 시험용 출장 패키지 ZIP | |
| `desk/` | 노트북 앱 **Trip Desk** (대시보드): 사전조사(지도·후보·일정·패키지), 일간 ZIP 가져오기, 전사, 교정·요약, 일간/최종 보고서(Word) | 1·2단계 구현 (실사용 검증 전) |
| `scripts/` | 설치·삭제 스크립트 (Mac/Ubuntu `.sh`, Windows `.bat`/`.ps1`) | |

## 0. 빠른 설치 / 삭제 (스크립트)

| 하는 일 | Mac · Ubuntu | Windows (더블클릭) |
|---|---|---|
| 번역 서버 + 폰 앱을 내 Cloudflare 에 설치 | `scripts/install-worker.sh` | `scripts\install-worker.bat` |
| 번역 서버 + 폰 앱 삭제 | `scripts/uninstall-worker.sh` | `scripts\uninstall-worker.bat` |
| 노트북 앱 Trip Desk 설치 | `scripts/install-desk.sh` | `scripts\install-desk.bat` |
| Trip Desk 삭제 | `scripts/uninstall-desk.sh` | `scripts\uninstall-desk.bat` |

- 번역 서버 설치에는 Node.js 18+, Cloudflare 계정(무료), Gemini API 키가 필요해요. 스크립트가 로그인 → 배포 → 접근 토큰 생성·등록까지 하고, 마지막에 **폰 앱 주소 / 번역 서버 주소 / 토큰**을 알려 줘요.
- **사람마다 따로**: 각자 자기 Cloudflare 계정(무료)으로 설치해요. 설치할 때 **내 ID**(영문 소문자·숫자·하이픈, 예: `ji`)를 정하면 서버 `trip-translate-ji`, 폰 앱 `https://trip-field-ji.pages.dev` 처럼 나만의 주소가 만들어지고, 저장공간·한도·데이터도 내 계정 것만 써요. 설치 순서는 ID 입력 → Cloudflare 로그인 → Gemini 키 → 끝(토큰이 화면에 나와요). 폰 앱에는 내 서버 주소가 미리 들어가서 폰에서는 토큰만 붙여 넣으면 돼요. (한 계정을 여럿이 나눠 쓰면 무료 한도를 같이 쓰게 돼요.)
- 이미 ID 없이 설치했다면 다시 실행해도 예전 이름(`trip-translate`, `trip-field`)을 그대로 써요. ID 주소로 옮기려면 `TRIP_ID=ji ./scripts/install-worker.sh` (새 주소가 생기고 폰 앱·토큰도 새로 설정).
- 다시 실행해도 안전해요(토큰은 그대로, 코드만 갱신). 모델을 바꾸려면 `GEMINI_MODEL=모델ID ./scripts/install-worker.sh`.
- 삭제 스크립트는 Cloudflare 의 Worker(Gemini 키·토큰 포함)와 Pages 프로젝트를 지우고, 지우기 전에 '삭제' 를 입력하게 해요. **Gemini API 키 폐기는 Google AI Studio 에서 직접** 해야 해요.
- Trip Desk 삭제는 프로그램만 지우고, 출장 데이터(`~/TripDesk`)는 물어본 뒤에만 지워요.
- 녹음 → 글 변환(전사)까지 쓰려면 `WHISPER=1 ./scripts/install-desk.sh` (Windows: `install-desk.bat whisper`). 용량이 크고 처음 한 번 모델을 내려받아요. 설치하지 않아도 전사본을 직접 붙여 넣을 수 있어요.
- Mac/Ubuntu 스크립트는 가짜 Cloudflare 명령으로 자동 시험했어요(`bash tests/scripts_test.sh`). **Windows(.ps1) 스크립트는 이 환경에서 실행해 보지 못했어요.** 처음 쓸 때 오류가 나면 알려 주세요.

## 1. 번역 서버(Worker) 수동 배포

Node.js가 있는 PC에서:

```bash
cd worker
npm install
npx wrangler login

# 비밀 값 등록 (파일에 적지 않습니다)
npx wrangler secret put GEMINI_API_KEY      # Gemini API 키
npx wrangler secret put TOKENS              # 팀원 토큰, 쉼표로 구분 (예: tokenA,tokenB)

# wrangler.toml 의 GEMINI_MODEL 을 테스트해 보신 모델 ID로 맞춘 뒤
npx wrangler deploy
```

배포되면 `https://trip-translate.<계정>.workers.dev` 주소가 나옵니다. 이 주소가 앱 설정의 "서버 주소"입니다.

- 토큰 만들기: `openssl rand -hex 16` (팀원마다 하나씩 나눠 주면, 문제가 생긴 토큰만 빼면 됩니다)
- 토큰을 뺄 때: `TOKENS` 값을 다시 등록하면 즉시 반영됩니다.
- 토큰은 직접 만든 긴 임의 문자열입니다. 예: `openssl rand -hex 24`. 서버(`wrangler secret put TOKENS`)와 폰 설정에 같은 값을 넣습니다.
- 번역이 느릴 때: 번역 팝업 아래에 `전체 시간 (Gemini 시간) · 모델` 이 표시됩니다. 설정의 '연결 시험'에도 같은 정보가 나옵니다.
  `https://<내 Worker 주소>/health` 를 열면 실제로 배포된 모델 ID 를 볼 수 있어요(`gemini-3.5-flash-lite` 인지 확인).
  Gemini 시간이 길면 모델 문제, 전체만 길고 Gemini 시간이 짧으면 네트워크 문제입니다.
  모델이 지원하면 `GEMINI_THINKING_LEVEL = "minimal"` 을 wrangler.toml [vars] 에 넣어 추론 시간을 줄일 수 있어요(지원하지 않는 모델에서는 오류가 납니다).
- `ALLOWED_ORIGIN` 을 폰 앱 주소(예: `https://trip-field.pages.dev`)로 바꾸면 다른 사이트에서의 호출을 막을 수 있습니다.
- 시험: `cd worker && npm test` (8개 테스트)

## 2. 폰 앱(Trip Field) 배포

빌드 과정이 없는 정적 파일이라 폴더 그대로 올리면 됩니다. Cloudflare Pages(무료)를 권장합니다.

```bash
npx wrangler pages deploy field-pwa --project-name trip-field
```

주소 예: `https://trip-field.pages.dev` (HTTPS라서 마이크 사용 가능)

- **설치**: 폰에서 주소를 열고 "홈 화면에 추가"
  - iPhone: Safari → 공유 버튼 → 홈 화면에 추가
  - Android: Chrome → 메뉴 → 홈 화면에 추가 / 앱 설치
- 처음 한 번 인터넷으로 열어 두면 이후 오프라인에서도 켜집니다(맵 변환, 녹음, 메모 모두 오프라인 동작. 번역만 온라인).
- 코드를 고쳐 다시 배포할 때는 `field-pwa/sw.js` 의 `VERSION` 숫자를 올려야 폰에 반영됩니다.
- 팀 공유: 주소 + 번역 토큰만 전달하면 됩니다.

### 처음 사용하기
1. 설정(톱니바퀴)에서 번역 서버 주소와 토큰 입력 → "연결 시험"
2. 출장 시작: `sample/sample_trip_package.zip` 으로 먼저 연습해 보세요 (폰으로 파일을 보낸 뒤 "ZIP 파일 선택"). 또는 "직접 만들기"
3. 맵 화면에서 공식 평면도 PDF/PNG를 불러오기 (패키지에 맵이 있으면 자동)
4. 업체를 열어 녹음 → 저녁에 "내보내기"에서 ZIP 만들고 AirDrop/메일로 노트북에 전달

### 주의할 점 (현장에서 중요한 것)
- **iPhone**: 녹음 중에는 화면을 켜 둔 채 앱을 앞에 두세요. 앱을 닫거나 화면이 꺼지면 녹음이 멈출 수 있습니다. 앱은 1초마다 조각을 저장해 두었다가 다시 열면 복구를 시도합니다.
- **저장 데이터**: 브라우저가 오래 쓰지 않은 데이터를 지울 수 있습니다. 매일 저녁 내보내기를 하고, 노트북에서 확인되기 전에는 사이트 데이터를 지우지 마세요.
- **맵 PDF**: 폰에서 직접 이미지로 변환합니다. 아주 큰 PDF는 시간이 걸리고, 최대 12페이지까지 처리합니다.
- **번역**: 입력한 문장이 Cloudflare Worker를 거쳐 Gemini로 전달됩니다. 회사 보안 정책을 확인하세요.

## 3. 데이터 형식

### 출장 패키지 보내기 (노트북 → 폰): 서버 또는 ZIP
- **서버(기본)**: Desk '패키지 확정'에서 '폰으로 보내기'를 누르면 내 Worker 의 보관함(Cloudflare KV)에 올라가요. 폰에서 새 출장 → '서버에서 불러오기'. 토큰마다 보관함이 따로 나뉘고 90일 뒤 자동으로 지워져요. 크기 한도 24MB, 반영까지 1분쯤 걸릴 수 있어요(KV 특성). `install-worker` 를 다시 실행해야 보관함이 만들어져요(Worker 코드가 바뀌었으므로 폰·서버 둘 다 갱신).
- **ZIP(대체)**: 인터넷이 안 될 때 예전처럼 파일로 옮겨요. 아래 형식은 둘 다 같아요.
- 하루치 기록(폰 → 노트북)은 지금처럼 ZIP(이메일 등)로 옮겨요. 녹음·사진이 커서 서버에는 올리지 않아요.

### 출장 패키지 형식 (ZIP)
```
trip.json        { schema, id, name, venue, purpose, days: ["2026-11-24", ...] }
companies.json   [ { id, name, category, hall, booth, day, preNotes, questions: [..] } ]
glossary.json    { terms: ["EtherCAT", ...] }          (선택)
map/*.pdf|png    전시장 평면도                          (선택)
```
같은 `trip.id` 로 다시 불러오면 업체 정보는 갱신되고, 방문 기록과 질문 체크는 유지됩니다.

### 하루치 내보내기 (폰 → 노트북, ZIP)
```
trip_<이름>/days/day<N>/
    visits.json      방문 업체, 녹음/메모/사진 목록(시각 포함), 현장 추가 여부
    audio/<업체>_<HHMM>_<번호>.m4a|webm
    photos/<업체>_<HHMM>_<번호>.jpg
```
녹음은 업체별로 누적되며, 같은 업체를 다른 날 다시 방문하면 `N차 방문`으로 구분됩니다.

## 4. 개발 메모
- 폰 앱: 의존성 없는 순수 JS(ES 모듈). 외부 라이브러리는 `field-pwa/vendor/` 에 포함(JSZip, pdf.js 4.10 legacy 빌드).
- 저장: IndexedDB (`js/db.js`). 녹음은 1초 조각으로 저장 후 정지 시 합칩니다.
- 시험: `npm install && npm test` (루트) — 내보내기/불러오기 파이프라인 시험. 실제 폰 브라우저에서의 동작(녹음, 터치 확대 등)은 직접 확인이 필요합니다.
