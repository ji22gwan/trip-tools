"""공식 사이트에서 전시장 지도(PDF/이미지)를 찾고 받는다.

원칙
- 받은 파일은 앞부분(시그니처)으로 진짜 PDF/이미지인지 확인한다. 에러 페이지를 PDF로 저장하지 않는다.
- 사이트가 자동 다운로드를 막으면(403 등) 억지로 우회하지 않고, 수동 업로드로 안내한다.
"""
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX_BYTES = 80 * 1024 * 1024
FILE_EXTS = (".pdf", ".jpg", ".jpeg", ".png")

# 이름에 이 키워드가 들어간 링크일수록 지도일 가능성이 높다 (점수)
KEYWORDS = [
    ("gelaendeplan", 6), ("geländeplan", 6), ("map_of_the_grounds", 6), ("map of the grounds", 6),
    ("hallenplan", 6), ("hall plan", 5), ("hallplan", 5), ("floor plan", 5), ("floorplan", 5),
    ("floor-plan", 5), ("site plan", 4), ("site-plan", 4), ("lageplan", 5), ("venue map", 4),
    ("exhibition map", 4), ("fairground", 3), ("hallen", 2), ("gelände", 2), ("gelaende", 2),
    ("map", 2), ("plan", 1), ("parkplan", 1), ("hall-plan", 5),
]
NEGATIVE = ("programm", "agenda", "press", "pressemitteilung", "datenschutz", "privacy", "terms", "agb",
            "imprint", "impressum", "ticket", "voucher", "invitation", "einladung", "catalog", "katalog",
            "anreise-flyer")

# 이미 확인된 공식 주소 (사용자가 직접 받아 본 것). 이름·연도로 맞춘다.
KNOWN_SOURCES = [
    {
        "match": re.compile(r"\bSPS\b", re.I),
        "years": {
            2026: {
                "siteUrl": "https://sps.mesago.com/nuernberg/de.html",
                "mapUrls": [
                    "https://sps.mesago.com/content/dam/messefrankfurt-mesago/sps/2026/documents/pdf/"
                    "SPS2026_Gelaendeplan_map_of_the_grounds_2026.pdf"
                ],
            }
        },
    }
]


class MapError(Exception):
    """사용자에게 그대로 보여줄 수 있는 메시지를 담는다."""


def sniff(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _check_url(url: str) -> str:
    url = (url or "").strip()
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise MapError("http:// 또는 https:// 로 시작하는 주소를 입력해 주세요.")
    return url


def fetch(url: str, timeout: int = 30, limit: int = MAX_BYTES) -> tuple[bytes, str, str]:
    """(본문, content-type, 최종 URL)"""
    url = _check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en,de;q=0.8,ko;q=0.6"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            chunks, total = [], 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                total += len(b)
                if total > limit:
                    raise MapError("파일이 너무 커요(80MB 초과).")
                chunks.append(b)
            return b"".join(chunks), r.headers.get("Content-Type", ""), r.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise MapError(
                f"사이트가 자동 다운로드를 거절했어요(HTTP {e.code}). 브라우저로 직접 받은 파일을 '파일 올리기'로 넣어 주세요."
            ) from e
        raise MapError(f"다운로드 실패(HTTP {e.code}).") from e
    except urllib.error.URLError as e:
        raise MapError(f"주소에 접속하지 못했어요: {e.reason}") from e
    except TimeoutError as e:
        raise MapError("응답 시간이 초과됐어요.") from e


def download_map(url: str) -> tuple[bytes, str]:
    """지도 파일을 받아 (데이터, 확장자)를 돌려준다. 시그니처가 맞지 않으면 거절한다."""
    data, ctype, final = fetch(url)
    ext = sniff(data)
    if not ext:
        kind = "웹 페이지" if "html" in ctype.lower() or data[:200].lstrip().lower().startswith((b"<!doc", b"<html")) else "알 수 없는 파일"
        raise MapError(f"받은 것이 PDF/이미지가 아니라 {kind}예요. 지도 파일의 직접 링크인지 확인해 주세요.")
    return data, ext


def filename_for(url: str, ext: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]) or "map"
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem + ext


# ---------- 링크 찾기 ----------
class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._href, self._text = a["href"], []
        elif tag in ("img", "source") and (a.get("src") or a.get("data-src")):
            self.links.append((a.get("src") or a.get("data-src"), a.get("alt", "")))

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def parse_links(html: str, base: str) -> list[tuple[str, str]]:
    p = _Links()
    p.feed(html)
    out = []
    for href, text in p.links:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        out.append((urllib.parse.urljoin(base, href).split("#")[0], text))
    return out


def score_link(url: str, text: str) -> int:
    hay = (urllib.parse.unquote(url) + " " + text).lower()
    s = sum(w for k, w in KEYWORDS if k in hay)
    if any(n in hay for n in NEGATIVE):
        s -= 4
    return s


def _is_file(url: str) -> bool:
    return urllib.parse.urlparse(url).path.lower().endswith(FILE_EXTS)


def find_map_candidates(site_url: str, max_pages: int = 8) -> list[dict]:
    """공식 사이트 페이지와 그 안의 같은 도메인 링크(깊이 1)에서 지도 후보를 점수순으로 돌려준다."""
    site_url = _check_url(site_url)
    host = urllib.parse.urlparse(site_url).netloc.lower().removeprefix("www.")
    seen_pages, cands = set(), {}

    def same_site(u):
        h = urllib.parse.urlparse(u).netloc.lower().split(":")[0]
        return h.split(".")[-2:] == host.split(":")[0].split(".")[-2:]

    def visit(url):
        seen_pages.add(url)
        data, ctype, final = fetch(url, timeout=20, limit=3 * 1024 * 1024)
        if sniff(data):  # 페이지가 아니라 파일 자체였다
            cands[final] = {"url": final, "text": "", "score": 10}
            return []
        html = data.decode("utf-8", errors="replace")
        pages = []
        for link, text in parse_links(html, final):
            sc = score_link(link, text)
            if _is_file(link):
                if sc > 0 and link not in cands:
                    cands[link] = {"url": link, "text": text, "score": sc + 2}
            elif same_site(link) and sc >= 2 and link not in seen_pages:
                pages.append((sc, link))
        return [l for _, l in sorted(pages, reverse=True)]

    queue = visit(site_url)
    for link in queue[: max_pages - 1]:
        if link in seen_pages:
            continue
        try:
            visit(link)
        except MapError:
            continue
    return sorted(cands.values(), key=lambda c: -c["score"])[:15]


def known_source(name: str, year: int | None) -> dict | None:
    for k in KNOWN_SOURCES:
        if k["match"].search(name or "") and year in k["years"]:
            return k["years"][year]
    return None
