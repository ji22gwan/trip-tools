"""매뉴얼용 가상 출장 데이터. 실제 회사·제품과 무관한 예시예요."""
import io
import json
import math
import struct
import wave
import zipfile

TRIP = dict(name="가상 스마트팩토리 엑스포 2026", venue="데모 전시센터", start="2026-11-24", end="2026-11-26",
            purpose="협동로봇·비전 센서·안전 시스템 동향 조사 (매뉴얼용 가상 예시)")

# (id, 이름, 분류, 홀, 부스, 방문일, 출처, 확인, 선별 이유, 질문)
COMPANIES = [
    ("c-alpha", "알파로보틱스", "협동로봇", "1", "1A12", 1, "ai", True, "가반하중 20kg급 협동로봇. 용접·팔레타이징 적용 사례 소개 예정.", ["EtherCAT 지원 범위", "가반하중과 반복정밀도", "납기와 대략 가격"]),
    ("c-belta", "벨타모션", "모션 제어", "1", "1B05", 1, "ai", True, "다축 모션 컨트롤러. EtherCAT 마스터 성능 비교용.", ["최소 사이클 타임", "SDK 언어(C++20 지원?)"]),
    ("c-cobalt", "코발트비전", "비전 센서", "2", "2A30", 1, "csv", True, "용접선 추적용 3D 비전 센서.", ["용접 광 간섭 대응", "현장 설치 사례"]),
    ("c-delta", "델타그리퍼", "그리퍼", "2", "2C11", 1, "manual", True, "전동 그리퍼. 조선 블록 취급 가능성 검토.", ["최대 파지력", "방진·방적 등급"]),
    ("c-eco", "에코웰딩", "용접 로봇", "3A", "3A07", 2, "ai", True, "조선 소조립 용접 자동화 솔루션.", ["수직 필릿 용접 품질", "티칭 방식"]),
    ("c-frost", "프로스트세이프", "안전 시스템", "3A", "3A22", 2, "csv", True, "협동 작업 영역 레이저 스캐너 안전 시스템.", ["인증 규격", "감지 거리"]),
    ("c-gamma", "감마휴머노이드", "휴머노이드", "3B", "3B01", 2, "ai", False, "휴머노이드 양산 일정과 가격 확인. (AI 추정 · 참가 확인 필요)", ["양산 시기", "배터리 지속 시간"]),
    ("c-hydra", "하이드라액추에이터", "액추에이터", "3B", "3B18", 2, "ai", True, "고토크 관절 모듈 공급사.", ["토크 밀도", "최소 주문 수량"]),
    ("c-iris", "아이리스AMR", "AMR", "4", "4A09", 3, "ai", True, "대형 자재 운반 AMR.", ["적재 중량", "엘리베이터 연동"]),
    ("c-juliet", "줄리엣센서랩", "센서", "4", "4C14", 3, "csv", True, "힘/토크 센서.", ["정격 용량", "교정 주기"]),
    ("c-kappa", "카파컨트롤", "모션 제어", "4", "4B02", None, "ai", False, "서보 드라이브 후보. (AI 추정)", []),
    ("c-lambda", "람다파워", "전원 장치", "", "", None, "ai", False, "산업용 전원 모듈. (AI 추정, 홀 미확인)", []),
]
PICKED = {c[0] for c in COMPANIES[:10]}
GLOSSARY = ["EtherCAT", "payload", "협동로봇", "가반하중", "반복정밀도", "AMR", "토크 센서", "SDK"]

HALL_LABELS = {"1": (0.20, 0.72), "2": (0.55, 0.72), "3A": (0.17, 0.27), "3B": (0.45, 0.27), "4": (0.78, 0.27)}

# 일차별 방문 기록: (업체 id, [(방문 시각 HH:MM, 길이 초, 원문 전사, 교정본)], [메모], 사진 수)
DAYS = {
    1: [
        ("c-alpha", [("10:05", 142, "알파로보틱스 협동로봇은 페이로드 이십 킬로이고 이더캣을 지원한다고 합니다. 가격은 사천만원쯤이라고 하는데 정확하진 않아요.",
                      "알파로보틱스 협동로봇은 payload {{20kg}}이고 {{EtherCAT}}을 지원한다고 합니다. 가격은 [확인필요: 4,000만원 / 4,500만원]쯤이라고 하는데 정확하진 않아요.")],
         [("납기 8주, 견적서 메일로 요청하기", True)], 2),
        ("c-belta", [("11:20", 96, "벨타모션 컨트롤러는 최소 사이클 타임이 125 마이크로초라고 했고 SDK는 C++로 제공됩니다.",
                      "벨타모션 컨트롤러는 최소 사이클 타임이 {{125µs}}라고 했고 {{SDK}}는 {{C++}}로 제공됩니다.")], [], 1),
        ("c-cobalt", [("14:10", 180, "코발트비전은 용접 광 간섭을 필터로 줄였다고 하고 시연 영상을 보내 주기로 했어요.",
                       "코발트비전은 용접 광 간섭을 필터로 줄였다고 하고 시연 영상을 보내 주기로 했어요.")], [("용접선 추적 시연이 인상적", False)], 3),
    ],
    2: [
        ("c-eco", [("10:30", 210, "에코웰딩은 수직 필릿 용접 품질을 보증하는 티칭 방식이 별도로 있다고 합니다. 소조립 라인 사례가 세 곳 있다고 해요.",
                    "에코웰딩은 수직 필릿 용접 품질을 보증하는 티칭 방식이 별도로 있다고 합니다. 소조립 라인 사례가 {{3곳}} 있다고 해요.")],
         [("조선소 납품 사례 자료 요청", True)], 2),
        ("c-frost", [("13:00", 88, "프로스트세이프는 감지 거리가 오 미터이고 안전 인증은 진행 중이라고 합니다.",
                      "프로스트세이프는 감지 거리가 {{5m}}이고 안전 인증은 [확인필요: 진행 중 / 취득 완료]이라고 합니다.")], [], 1),
        ("c-hydra", [("15:40", 120, "하이드라액추에이터는 토크 밀도가 높고 최소 주문 수량은 오십 개라고 했어요.",
                      "하이드라액추에이터는 토크 밀도가 높고 최소 주문 수량은 {{50개}}라고 했어요.")], [("샘플 1개 대여 가능한지 확인", False)], 0),
    ],
    3: [
        ("c-iris", [("10:15", 160, "아이리스 AMR은 적재 중량 팔백 킬로그램이고 엘리베이터 연동은 옵션이라고 합니다.",
                     "아이리스 {{AMR}}은 적재 중량 {{800kg}}이고 엘리베이터 연동은 옵션이라고 합니다.")], [], 2),
        ("c-juliet", [("11:50", 105, "줄리엣센서랩 힘 토크 센서는 정격 용량 오백 뉴턴이고 교정 주기는 일 년입니다.",
                       "줄리엣센서랩 힘·토크 센서는 정격 용량 {{500N}}이고 교정 주기는 {{1년}}입니다.")], [("교정 서비스 비용 확인 필요", True)], 1),
    ],
}
DAY_SUMMARY = {
    1: "협동로봇·모션 제어·비전 센서 3곳을 만났다. 알파로보틱스의 가반하중 {{20kg}}급 협동로봇이 EtherCAT을 지원하는 점이 가장 눈에 띄었고, 코발트비전의 용접선 추적 센서는 후속 시연 영상을 받기로 했다.",
    2: "용접·안전·액추에이터 3곳을 만났다. 에코웰딩의 수직 필릿 용접 티칭 방식이 조선 소조립 적용 후보로 유력하며, 프로스트세이프의 안전 인증 상태는 [확인필요: 진행 중 / 취득 완료].",
    3: "AMR과 힘·토크 센서 2곳을 만났다. 아이리스 AMR의 적재 중량 {{800kg}}은 블록 운반 요구 수준에 못 미칠 수 있어 추가 확인이 필요하다.",
}
FINAL = {
    "overview": "3일간 10곳 중 8곳을 만났다. 협동로봇과 용접 자동화는 즉시 검토할 만한 수준이고, 휴머노이드는 양산 일정이 불확실해 계속 추적이 필요하다.",
    "highlights": ["알파로보틱스: {{20kg}} 가반하중, {{EtherCAT}} 지원 — 시험 도입 후보", "에코웰딩: 수직 필릿 용접 티칭 방식 — 조선 소조립 적용 검토", "아이리스 AMR: 적재 중량 {{800kg}}은 대형 블록 운반에는 부족"],
    "followups": ["알파로보틱스 견적서 수령 (납기 8주)", "에코웰딩 조선소 납품 사례 자료 받기", "코발트비전 시연 영상 확인", "하이드라액추에이터 샘플 대여 문의"],
}

TRAVEL = dict(origin="ICN", destination="FRA", minStars=3, maxStars=4)
FLIGHTS = [
    dict(direction="outbound", airline="데모에어", flightNo="DA101", **{"from": "ICN", "to": "FRA"}, depart="2026-11-23T13:10", arrive="2026-11-23T17:40",
         confirmation="X7K2QD", amount=1450000, currency="KRW", baggage="수하물 23kg x1"),
    dict(direction="return", airline="데모에어", flightNo="DA102", **{"from": "FRA", "to": "ICN"}, depart="2026-11-26T19:30", arrive="2026-11-27T13:50",
         confirmation="X7K2QD", amount=0, currency="KRW", baggage=""),
]
HOTELS = [dict(name="그랜드 데모 호텔", stars=4, address="Musterstraße 12, 데모시티", checkIn="2026-11-23", checkOut="2026-11-26", confirmation="HD-558210",
               amount=612, currency="EUR", freeCancelUntil="2026-11-20T12:00", site="Agoda", note="전시센터까지 지하철 12분")]
CAND_FLIGHTS = [dict(airline="데모에어", flightNo="DA101", **{"from": "ICN", "to": "FRA"}, depart="2026-11-23T13:10", arrive="2026-11-23T17:40", stops="직항", price="약 145만원", sourceUrl="https://example.com/flights", note="도착 후 저녁 여유"),
                dict(airline="샘플항공", flightNo="SA77", **{"from": "ICN", "to": "FRA"}, depart="2026-11-23T09:00", arrive="2026-11-23T16:20", stops="1회 경유(DOH)", price="약 118만원", sourceUrl="https://example.com/flights", note="경유 대기 2시간")]
CAND_HOTELS = [dict(name="그랜드 데모 호텔", stars=4, address="Musterstraße 12", distance="전시센터까지 지하철 12분", price="1박 약 204유로", cancellation="무료 취소 ~11/20", sourceUrl="https://example.com/hotel1", note="가용 확인됨"),
               dict(name="시티 샘플 인", stars=3, address="Beispielweg 3", distance="도보 8분", price="1박 약 139유로", cancellation="취소 불가", sourceUrl="https://example.com/hotel2", note="가용 미확인")]


def tone_wav(freq: float, sec: float = 3.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        n = int(8000 * sec)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / 8000) * (1 - i / n))) for i in range(n)))
    return buf.getvalue()


def photo_jpeg(label: str, color) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (480, 320), color)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 460, 300], outline=(255, 255, 255), width=4)
    d.text((40, 140), label, fill=(255, 255, 255))
    out = io.BytesIO(); im.save(out, "JPEG", quality=80)
    return out.getvalue()


def day_zip(trip: dict, day: int, tz_min: int = 60) -> bytes:
    """폰 '내보내기'가 만드는 것과 같은 구조의 하루치 ZIP."""
    from datetime import datetime, timedelta, timezone
    date = trip["days"][day - 1]
    root = "trip_demo"; dd = f"{root}/days/day{day}"
    names = {c[0]: c for c in COMPANIES}
    zbuf = io.BytesIO()
    companies = []
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_STORED) as z:
        for ci, (cid, recs, memos, photos) in enumerate(DAYS[day]):
            c = names[cid]
            recs_out, ph_out = [], []
            for ri, (hm, dur, _t, _c) in enumerate(recs):
                local = datetime.fromisoformat(f"{date}T{hm}:00")
                utc = local - timedelta(minutes=tz_min)
                fn = f"audio/{cid}_{hm.replace(':', '')}_{ri + 1:02d}.wav"
                z.writestr(f"{dd}/{fn}", tone_wav(300 + 60 * (ci + day)))
                recs_out.append(dict(file=fn, at=utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"), durationSec=dur, mime="audio/wav", recovered=False))
            for pi in range(photos):
                fn = f"photos/{cid}_{recs[0][0].replace(':', '')}_{pi + 1:02d}.jpg"
                z.writestr(f"{dd}/{fn}", photo_jpeg(f"{c[1]} 부스 사진 {pi + 1}", (40 + 30 * pi, 90 + 20 * ci, 140)))
                ph_out.append(dict(file=fn, at=recs_out[0]["at"]))
            companies.append(dict(id=cid, name=c[1], category=c[2], hall=c[3], booth=c[4], addedOnSite=False, visited=True, visitedAt=recs_out[0]["at"],
                                  recordings=recs_out, memos=[dict(text=t, important=imp, at=recs_out[0]["at"]) for t, imp in memos], photos=ph_out))
        visits = dict(schema=1, tripId=trip["id"], tripName=trip["name"], venue=trip["venue"], day=day, date=date, exportedAt=f"{date}T20:00:00Z", tzOffsetMin=tz_min, companies=companies)
        z.writestr(f"{dd}/visits.json", json.dumps(visits, ensure_ascii=False, indent=2))
    return zbuf.getvalue()


def map_pdf() -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig = plt.figure(figsize=(11, 7)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    zones = {"1": (0.05, 0.55, 0.30, 0.38, "#cfe3f7"), "2": (0.40, 0.55, 0.30, 0.38, "#d9f0d9"), "3A": (0.05, 0.08, 0.26, 0.38, "#f7e3cf"), "3B": (0.34, 0.08, 0.26, 0.38, "#f3d9ee"), "4": (0.63, 0.08, 0.32, 0.38, "#fdf1c4")}
    for k, (x, y, w, h, col) in zones.items():
        ax.add_patch(Rectangle((x, y), w, h, facecolor=col, edgecolor="#555", lw=2))
        ax.text(*HALL_LABELS[k], k, fontsize=34, ha="center", va="center", color="#223")
    ax.add_patch(Rectangle((0.74, 0.55), 0.21, 0.38, facecolor="#eeeeee", edgecolor="#999", lw=1.5)); ax.text(0.845, 0.74, "ENTRANCE", fontsize=16, ha="center", color="#555")
    ax.text(0.5, 0.5, "DEMO EXPO CENTER - sample floor plan", fontsize=12, ha="center", color="#777")
    out = io.BytesIO(); fig.savefig(out, format="pdf"); plt.close(fig)
    return out.getvalue()


POINTS = {
    "c-alpha": ["가반하중 20kg, EtherCAT 지원", "가격 4,000~4,500만원 추정 (확인 필요)", "견적서 메일 요청, 납기 8주"],
    "c-belta": ["최소 사이클 타임 125µs", "SDK는 C++ 제공"],
    "c-cobalt": ["용접 광 간섭을 필터로 저감", "시연 영상 송부 예정"],
    "c-frost": ["감지 거리 5m", "안전 인증 상태 확인 필요"],
    "c-hydra": ["토크 밀도 높음", "최소 주문 수량 50개", "샘플 대여 문의"],
    "c-iris": ["적재 중량 800kg", "엘리베이터 연동은 옵션"],
    "c-juliet": ["정격 500N, 교정 주기 1년"],
    "c-eco": ["수직 필릿 용접 품질 보증 티칭 방식", "소조립 라인 사례 3곳"],
}


FAIR = dict(name="가상 스마트팩토리 엑스포 2026", summary=["가상의 스마트 제조 자동화 전시회"], scale=["참가 업체·방문객 수: 추가 확인 필요"], halls=["1홀: 로봇", "3A·3B홀: 용접·안전", "4홀: 이동로봇·센서"], slogan=["Make it smarter"])
PPT_REPLY = {
    "companies": [dict(id="c-alpha", usage=[dict(title="소부재 이송·조립 보조", points=["가반하중 20kg급, 대형 블록에는 부족", "시험 도입 전 견적·납기 확인"])]),
                  dict(id="c-eco", usage=[dict(title="소조립 용접 자동화", points=["수직 필릿 티칭 방식 별도 보유", "조선소 납품 실적은 추가 확인 필요"])])],
    "insights": [dict(title="전시회 기술 트렌드", points=["협동로봇의 중량물 대응 확대", "센서 기반 용접선 인식 보급"]),
                 dict(title="AI·데이터", points=["현장 데이터 연계 구조가 핵심 과제"]),
                 dict(title="업체 동향", points=["모션 제어와 비전의 통합 제안 증가"]),
                 dict(title="조선소 과제", points=["비정형 블록 대응과 내환경성 검증 필요"])],
    "conclusions": [dict(title="용접 자동화 단기 실증", points=["에코웰딩 소조립 라인 PoC 검토"]),
                    dict(title="협동로봇 추가 검증", points=["알파로보틱스 견적·납기 확인"]),
                    dict(title="이동로봇은 장기 검토", points=["적재 중량 요건 확인 후 재검토"])],
}
