"""출장 데이터 저장소. 폴더 하나가 출장 하나: trip.json, companies.json, glossary.json, map/"""
import json
import os
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

from . import SCHEMA_VERSION

ID_RE = re.compile(r"^trip-[0-9a-f]{8}$")
MAP_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


class StoreError(Exception):
    pass


def hall_key(s) -> str:
    """홀 이름 비교용 키: 'Hall 3A', '3a', '홀 3A' 모두 '3A'. 폰 앱(model.js hallKey)과 같은 규칙이어야 한다."""
    t = re.sub(r"^(HALLE|HALL|홀)\s*", "", str(s or "").strip().upper())
    return re.sub(r"\s+", "", t)


def clean_hall_pins(pins) -> dict:
    """{홀: {x, y, page}} — x, y 는 지도 이미지의 0~1 비율. 잘못된 값은 버린다."""
    out = {}
    if not isinstance(pins, dict):
        return out
    for k, v in pins.items():
        key = hall_key(k)
        try:
            x, y, page = float(v["x"]), float(v["y"]), int(v.get("page", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if key and 0 <= x <= 1 and 0 <= y <= 1 and 0 <= page < 50:
            out[key] = {"x": round(x, 4), "y": round(y, 4), "page": page}
    return out


def data_dir() -> Path:
    env = os.environ.get("TRIPDESK_HOME")
    return Path(env) if env else Path.home() / "TripDesk"


def iso_range(start: str, end: str | None) -> list[str]:
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end or start)
    except ValueError as exc:
        raise StoreError("날짜는 YYYY-MM-DD 형식으로 입력해 주세요.") from exc
    if e < s:
        raise StoreError("종료일이 시작일보다 빠릅니다.")
    if (e - s).days > 30:
        raise StoreError("출장 기간은 31일 이내로 입력해 주세요.")
    return [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]


def safe_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/"))
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE).strip("._")
    return base or "map"


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else data_dir()
        (self.root / "trips").mkdir(parents=True, exist_ok=True)

    # ---- 경로 ----
    def _dir(self, trip_id: str) -> Path:
        if not ID_RE.match(trip_id or ""):
            raise StoreError("잘못된 출장 ID 입니다.")
        d = self.root / "trips" / trip_id
        if not d.is_dir():
            raise StoreError("출장을 찾을 수 없어요.")
        return d

    @staticmethod
    def _read(path: Path, default):
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, obj) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ---- 출장 ----
    def create_trip(self, name: str, venue: str, start: str, end: str | None, purpose: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            raise StoreError("출장(전시회) 이름을 입력해 주세요.")
        trip = {
            "schema": SCHEMA_VERSION,
            "id": "trip-" + uuid.uuid4().hex[:8],
            "name": name,
            "venue": (venue or "").strip(),
            "purpose": (purpose or "").strip(),
            "days": iso_range(start, end),
            "siteUrl": "",
            "mapSources": [],
            "primaryMap": "",
        }
        d = self.root / "trips" / trip["id"]
        (d / "map").mkdir(parents=True)
        self._write(d / "trip.json", trip)
        self._write(d / "companies.json", [])
        self._write(d / "glossary.json", {"terms": []})
        return trip

    def list_trips(self) -> list[dict]:
        out = []
        for p in sorted((self.root / "trips").glob("trip-*/trip.json")):
            try:
                t = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            t["companyCount"] = len(self._read(p.parent / "companies.json", []))
            t["mapCount"] = len(self.list_maps(t["id"]))
            out.append(t)
        out.sort(key=lambda t: t["days"][0], reverse=True)
        return out

    def get_trip(self, trip_id: str) -> dict:
        return self._read(self._dir(trip_id) / "trip.json", {})

    def update_trip(self, trip_id: str, **fields) -> dict:
        trip = self.get_trip(trip_id)
        allowed = {"name", "venue", "purpose", "siteUrl"}
        for k, v in fields.items():
            if k in allowed and isinstance(v, str):
                trip[k] = v.strip()
        if isinstance(fields.get("keywords"), list):  # 후보 검색 키워드: 저장해 두고 나중에 추가·삭제해 다시 검색
            out = []
            for k in fields["keywords"]:
                k = str(k).strip()[:60]
                if k and k not in out:
                    out.append(k)
            trip["keywords"] = out[:12]
        if isinstance(fields.get("keywordCount"), int) and 5 <= fields["keywordCount"] <= 100:
            trip["keywordCount"] = fields["keywordCount"]
        if "hallPins" in fields:
            trip["hallPins"] = clean_hall_pins(fields["hallPins"])
        if "start" in fields and fields["start"]:
            trip["days"] = iso_range(fields["start"], fields.get("end") or fields["start"])
        self._write(self._dir(trip_id) / "trip.json", trip)
        return trip

    def delete_trip(self, trip_id: str) -> None:
        import shutil

        shutil.rmtree(self._dir(trip_id))

    # ---- 업체 / 용어 ----
    def get_companies(self, trip_id: str) -> list[dict]:
        from . import booths
        return [booths.norm(c) for c in self._read(self._dir(trip_id) / "companies.json", []) if isinstance(c, dict)]

    def set_companies(self, trip_id: str, companies: list[dict]) -> None:
        self._write(self._dir(trip_id) / "companies.json", companies)

    def get_sessions(self, trip_id: str) -> list[dict]:
        return self._read(self._dir(trip_id) / "sessions.json", [])

    def set_sessions(self, trip_id: str, sessions: list[dict]) -> None:
        self._write(self._dir(trip_id) / "sessions.json", sessions)

    def get_glossary(self, trip_id: str) -> list[str]:
        g = self._read(self._dir(trip_id) / "glossary.json", {"terms": []})
        return g.get("terms", []) if isinstance(g, dict) else list(g)

    def set_glossary(self, trip_id: str, terms: list[str]) -> None:
        clean = []
        for t in terms:
            t = str(t).strip()
            if t and t not in clean:
                clean.append(t)
        self._write(self._dir(trip_id) / "glossary.json", {"terms": clean})

    # ---- 설정 ----
    def get_settings(self) -> dict:
        return self._read(self.root / "settings.json", {})

    def save_settings(self, **fields) -> None:
        cur = self.get_settings()
        if isinstance(fields.get("whisperModel"), str) and fields["whisperModel"].strip():
            cur["whisperModel"] = fields["whisperModel"].strip()
        self._write(self.root / "settings.json", cur)

    # ---- 지도 ----
    def list_maps(self, trip_id: str) -> list[Path]:
        d = self._dir(trip_id) / "map"
        return sorted(p for p in d.iterdir() if p.suffix.lower() in MAP_EXTS) if d.exists() else []

    def add_map(self, trip_id: str, filename: str, data: bytes, source: str = "") -> str:
        ext = Path(filename).suffix.lower()
        if ext not in MAP_EXTS:
            raise StoreError("PDF, PNG, JPG 파일만 지도로 쓸 수 있어요.")
        d = self._dir(trip_id) / "map"
        d.mkdir(exist_ok=True)
        name = safe_filename(filename)
        target = d / name
        n = 2
        while target.exists():
            target = d / f"{Path(name).stem}_{n}{ext}"
            n += 1
        target.write_bytes(data)
        trip = self.get_trip(trip_id)
        if source:
            trip.setdefault("mapSources", []).append({"file": target.name, "url": source})
        if not trip.get("primaryMap"):
            trip["primaryMap"] = target.name  # 처음 받은 지도를 대표로. 나중에 바꿀 수 있다
        self._write(self._dir(trip_id) / "trip.json", trip)
        return target.name

    # ---- 폰용 지도 이미지: PDF 지도를 노트북에서 한 번만 이미지로 바꿔 두면 폰이 매번 변환하지 않아도 된다 ----
    def _render_dir(self, trip_id: str) -> Path:
        return self._dir(trip_id) / "map_render"

    def _stamp(self, p: Path) -> dict:
        st = p.stat()
        return {"src": p.name, "size": st.st_size, "mtime": int(st.st_mtime)}

    def render_state(self, trip_id: str) -> dict:
        """대표 지도가 PDF 일 때 폰용 이미지가 최신인지. needed=True 면 노트북 화면에서 변환해 올려야 한다."""
        p = self.primary_map(trip_id)
        if not p or p.suffix.lower() != ".pdf":
            return {"needed": False, "pdf": False, "name": p.name if p else "", "pages": []}
        d = self._render_dir(trip_id)
        meta = self._read(d / "meta.json", {})
        pages = sorted(d.glob("p*.jpg")) if d.exists() else []
        fresh = bool(pages) and meta.get("stamp") == self._stamp(p) and meta.get("pages") == len(pages)
        return {"needed": not fresh, "pdf": True, "name": p.name, "pages": [x.name for x in pages] if fresh else []}

    def render_begin(self, trip_id: str) -> None:
        d = self._render_dir(trip_id)
        if d.exists():
            for x in d.iterdir():
                x.unlink()
        d.mkdir(exist_ok=True)

    def render_put(self, trip_id: str, page: int, data: bytes) -> None:
        if not data[:3] == b"\xff\xd8\xff" or not 1 <= page <= 12:
            raise StoreError("지도 이미지 형식이 올바르지 않아요.")
        d = self._render_dir(trip_id)
        d.mkdir(exist_ok=True)
        (d / f"p{page:02d}.jpg").write_bytes(data)

    def render_done(self, trip_id: str) -> dict:
        p = self.primary_map(trip_id)
        d = self._render_dir(trip_id)
        pages = sorted(d.glob("p*.jpg")) if d.exists() else []
        if not p or not pages:
            raise StoreError("변환된 지도 이미지가 없어요.")
        self._write(d / "meta.json", {"stamp": self._stamp(p), "pages": len(pages)})
        return self.render_state(trip_id)

    def render_files(self, trip_id: str) -> list[Path]:
        st = self.render_state(trip_id)
        return [self._render_dir(trip_id) / n for n in st["pages"]]

    def primary_map(self, trip_id: str) -> Path | None:
        """패키지에 넣을 대표 지도 1장. 지정이 없거나 사라졌으면 남은 지도 중 첫 번째."""
        maps = self.list_maps(trip_id)
        want = self.get_trip(trip_id).get("primaryMap")
        for p in maps:
            if p.name == want:
                return p
        return maps[0] if maps else None

    def set_primary_map(self, trip_id: str, filename: str) -> None:
        if not any(p.name == filename for p in self.list_maps(trip_id)):
            raise StoreError("그 지도 파일을 찾을 수 없어요.")
        trip = self.get_trip(trip_id)
        trip["primaryMap"] = filename
        self._write(self._dir(trip_id) / "trip.json", trip)

    def delete_map(self, trip_id: str, filename: str) -> None:
        p = self._dir(trip_id) / "map" / safe_filename(filename)
        if p.exists():
            p.unlink()
        trip = self.get_trip(trip_id)
        if trip.get("primaryMap") == p.name:
            nxt = self.list_maps(trip_id)
            trip["primaryMap"] = nxt[0].name if nxt else ""
            self._write(self._dir(trip_id) / "trip.json", trip)
