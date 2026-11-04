"""업체 리스트 가져오기(CSV/Excel)와 합치기."""
import csv
import io
import re
import uuid

HEADERS = {
    "name": {"name", "company", "업체", "업체명", "회사", "회사명", "기업", "기업명", "exhibitor"},
    "category": {"category", "카테고리", "분류", "구분", "분야", "type"},
    "hall": {"hall", "홀", "전시홀"},
    "booth": {"booth", "stand", "부스", "부스번호", "스탠드"},
    "day": {"day", "일차", "날짜", "방문일", "방문일차", "date"},
    "preNotes": {"notes", "note", "memo", "메모", "사전메모", "사전정보", "비고", "설명"},
    "questions": {"questions", "question", "질문", "확인사항", "확인할것", "질문목록"},
}


class ImportError_(Exception):
    pass


def _norm(h) -> str:
    return re.sub(r"[\s_\-()/]+", "", str(h or "")).lower()


def _column_map(header: list) -> dict[str, int]:
    out = {}
    for i, h in enumerate(header):
        n = _norm(h)
        for key, names in HEADERS.items():
            if key not in out and n in {_norm(x) for x in names}:
                out[key] = i
    return out


def read_rows(filename: str, data: bytes) -> list[list]:
    low = filename.lower()
    if low.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError as e:
            raise ImportError_("Excel 파일을 읽으려면 openpyxl 이 필요해요. CSV로 저장해서 올려도 됩니다.") from e
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [["" if c is None else c for c in row] for row in ws.iter_rows(values_only=True)]
    if low.endswith((".csv", ".tsv", ".txt")):
        for enc in ("utf-8-sig", "cp949"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ImportError_("파일 인코딩을 읽지 못했어요. UTF-8 CSV 로 저장해 주세요.")
        sample = text[:2000]
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        return list(csv.reader(io.StringIO(text), delimiter=delim))
    raise ImportError_("CSV 또는 Excel(.xlsx) 파일만 가져올 수 있어요.")


def _day(value, days: list[str]) -> int | None:
    s = str(value).strip() if value is not None else ""
    if not s:
        return None
    s = s.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else s
    if s in days:
        return days.index(s) + 1
    m = re.search(r"\d+", s)
    if m:
        n = int(m.group())
        if 1 <= n <= len(days):
            return n
    return None


def _questions(value) -> list[str]:
    s = str(value or "").strip()
    return [q.strip(" -•\t") for q in re.split(r"[\n;|]+", s) if q.strip(" -•\t")]


def parse_companies(filename: str, data: bytes, days: list[str]) -> tuple[list[dict], list[str]]:
    rows = [r for r in read_rows(filename, data) if any(str(c).strip() for c in r)]
    if not rows:
        raise ImportError_("비어 있는 파일이에요.")
    cols = _column_map(rows[0])
    if "name" not in cols:
        raise ImportError_("첫 줄에 '업체명' 열이 필요해요. (열 이름: 업체명, 카테고리, 홀, 부스, 일차, 메모, 질문)")
    out, warnings = [], []
    for n, row in enumerate(rows[1:], start=2):
        def cell(key):
            i = cols.get(key)
            return row[i] if i is not None and i < len(row) else ""

        name = str(cell("name")).strip()
        if not name:
            continue
        day = _day(cell("day"), days)
        if str(cell("day")).strip() and day is None:
            warnings.append(f"{n}행 '{name}': 일차/날짜 '{cell('day')}' 가 출장 기간에 없어 일정 미정으로 넣었어요.")
        out.append({
            "name": name,
            "category": str(cell("category")).strip() or "기타",
            "hall": str(cell("hall")).strip(),
            "booth": str(cell("booth")).strip(),
            "day": day,
            "preNotes": str(cell("preNotes")).strip(),
            "questions": _questions(cell("questions")),
        })
    return out, warnings


def _key(c: dict) -> tuple:
    return (c["name"].strip().lower(), str(c.get("hall", "")).strip().lower(), str(c.get("booth", "")).strip().lower())


def merge_companies(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """같은 (이름, 홀, 부스) 업체는 id 를 유지하고 내용을 갱신한다. 폰의 방문 기록이 id 로 이어지기 때문이다."""
    by_key = {_key(c): c for c in existing}
    added = updated = 0
    for c in incoming:
        prev = by_key.get(_key(c))
        if prev:
            prev.update({k: v for k, v in c.items()})
            updated += 1
        else:
            c = {"id": "c-" + uuid.uuid4().hex[:8], **c}
            existing.append(c)
            by_key[_key(c)] = c
            added += 1
    return existing, added, updated


def template_csv() -> str:
    return (
        "﻿업체명,카테고리,홀,부스,일차,메모,질문\n"
        "예시 로보틱스,휴머노이드,3A,118,1,제품 라인업 확인,가동 시간; 가격대와 납기\n"
    )
