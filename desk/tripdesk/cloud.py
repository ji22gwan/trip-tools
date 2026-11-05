"""Worker 패키지 보관함 연동: Desk 가 만든 출장 패키지를 서버에 올린다. 폰은 같은 서버에서 내려받는다."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .store import StoreError, data_dir


def _state_home() -> Path:
    return Path(os.environ.get("TRIP_TOOLS_HOME") or Path.home() / ".trip-tools")


def load_config() -> dict:
    """install-worker 가 같은 컴퓨터에 남긴 기록(주소·토큰)을 읽는다. Desk 설정(settings.json)에 직접 적은 값이 있으면 그것이 우선."""
    cfg = {"workerUrl": "", "token": "", "storage": True}
    home = _state_home()
    env, js = home / "install.env", home / "install.json"
    try:
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                k, _, v = line.partition("=")
                v = v.strip().strip('"')
                if k == "WORKER_URL":
                    cfg["workerUrl"] = v
                elif k == "TOKEN":
                    cfg["token"] = v
                elif k == "KV_ID":
                    cfg["storage"] = bool(v)
        elif js.exists():
            d = json.loads(js.read_text(encoding="utf-8-sig"))
            cfg.update(workerUrl=d.get("WORKER_URL", ""), token=d.get("TOKEN", ""), storage=bool(d.get("KV_ID")))
    except (OSError, ValueError):
        pass
    try:
        st = json.loads((data_dir() / "settings.json").read_text(encoding="utf-8"))
        cfg["workerUrl"] = st.get("workerUrl") or cfg["workerUrl"]
        cfg["token"] = st.get("workerToken") or cfg["token"]
    except (OSError, ValueError):
        pass
    cfg["workerUrl"] = cfg["workerUrl"].rstrip("/")
    return cfg


def status() -> dict:
    c = load_config()
    return {"ready": bool(c["workerUrl"] and c["token"] and c["storage"]), "workerUrl": c["workerUrl"], "hasToken": bool(c["token"]), "storage": c["storage"]}


def upload_package(trip_id: str, trip_name: str, data: bytes) -> dict:
    c = load_config()
    if not (c["workerUrl"] and c["token"]):
        raise StoreError("번역 서버 설치 기록을 찾지 못했어요. 이 컴퓨터에서 install-worker 를 실행했는지 확인해 주세요. (ZIP 파일로 옮기는 방법은 그대로 쓸 수 있어요.)")
    if not c["storage"]:
        raise StoreError("패키지 보관함(KV)이 만들어지지 않았어요. install-worker 를 다시 실행해 보세요. 그동안은 ZIP 파일로 옮길 수 있어요.")
    req = urllib.request.Request(f"{c['workerUrl']}/packages/{trip_id}", data=data, method="PUT",
                                 headers={"Authorization": f"Bearer {c['token']}", "Content-Type": "application/zip", "X-Trip-Name": urllib.parse.quote(trip_name),
                                          "User-Agent": "TripDesk/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error", "")
        except ValueError:
            err = ""
        msg = {"unauthorized": "토큰이 맞지 않아요(서버가 거절).", "too_large": "패키지가 너무 커요(24MB 초과). 지도 파일을 줄이거나 ZIP 으로 옮겨 주세요.",
               "storage_not_configured": "서버에 패키지 보관함이 없어요. install-worker 를 다시 실행해 주세요."}.get(err, f"서버 응답 오류({e.code})")
        raise StoreError(msg) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise StoreError(f"서버에 연결하지 못했어요: {getattr(e, 'reason', e)}") from None


def _call(method: str, path: str) -> dict:
    c = load_config()
    if not (c["workerUrl"] and c["token"]):
        raise StoreError("번역 서버 설치 기록을 찾지 못했어요. 이 컴퓨터에서 install-worker 를 실행했는지 확인해 주세요.")
    req = urllib.request.Request(f"{c['workerUrl']}{path}", method=method, headers={"Authorization": f"Bearer {c['token']}", "User-Agent": "TripDesk/1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise StoreError({401: "토큰이 맞지 않아요(서버가 거절).", 503: "서버에 패키지 보관함이 없어요."}.get(e.code, f"서버 응답 오류({e.code})")) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise StoreError(f"서버에 연결하지 못했어요: {getattr(e, 'reason', e)}") from None


def list_packages() -> list[dict]:
    """서버 보관함에 올라가 있는 출장 패키지 목록(id, name, size, at)."""
    return _call("GET", "/packages").get("packages", [])


def delete_package(pkg_id: str) -> None:
    if not pkg_id or "/" in pkg_id:
        raise StoreError("지울 패키지를 알 수 없어요.")
    _call("DELETE", f"/packages/{urllib.parse.quote(pkg_id)}")
