"""서버 모드 로그인. 표준 라이브러리만 쓴다.

로컬 모드(내 컴퓨터에서만 열림)에는 로그인이 없다. 서버 모드는 다른 곳에서 접속할 수 있으므로
비밀번호 하나로 보호한다. 비밀번호는 scrypt 해시로만 저장하고, 세션은 메모리에 둔다(서버를 다시 켜면 다시 로그인).
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

COOKIE = "tripdesk_session"
SESSION_SECONDS = 30 * 24 * 3600
MIN_PASSWORD = 8
MAX_FAILS = 5  # 1분 안에 이만큼 틀리면 잠시 막는다
FAIL_WINDOW = 60
_SCRYPT = dict(n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def auth_file(home: Path) -> Path:
    return home / "auth.json"


def set_password(home: Path, password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD}자 이상이어야 해요.")
    salt = secrets.token_bytes(16)
    home.mkdir(parents=True, exist_ok=True)
    p = auth_file(home)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 나만 읽을 수 있게
    with os.fdopen(fd, "w") as f:
        json.dump({"salt": salt.hex(), "hash": _derive(password, salt).hex()}, f)


class Auth:
    def __init__(self, home: Path, secure_cookie: bool = False):
        d = json.loads(auth_file(home).read_text())
        self._salt, self._hash = bytes.fromhex(d["salt"]), bytes.fromhex(d["hash"])
        self.secure_cookie = secure_cookie
        self._sessions: dict[str, float] = {}
        self._fails: list[float] = []
        self._lock = threading.Lock()

    def login(self, password) -> str | None:
        """맞으면 세션 토큰, 틀리면 None, 너무 자주 틀렸으면 PermissionError."""
        now = time.time()
        with self._lock:
            self._fails = [t for t in self._fails if now - t < FAIL_WINDOW]
            if len(self._fails) >= MAX_FAILS:
                raise PermissionError
        ok = isinstance(password, str) and hmac.compare_digest(_derive(password, self._salt), self._hash)
        with self._lock:
            if not ok:
                self._fails.append(now)
                return None
            self._sessions = {k: v for k, v in self._sessions.items() if v > now}
            token = secrets.token_urlsafe(32)
            self._sessions[token] = now + SESSION_SECONDS
            return token

    def valid(self, cookie_header: str | None) -> bool:
        token = self._token(cookie_header)
        with self._lock:
            return bool(token) and self._sessions.get(token, 0) > time.time()

    def logout(self, cookie_header: str | None) -> None:
        with self._lock:
            self._sessions.pop(self._token(cookie_header) or "", None)

    def cookie(self, token: str | None) -> str:
        """token 이 None 이면 지우는 쿠키."""
        attrs = f"Path=/; HttpOnly; SameSite=Lax{'; Secure' if self.secure_cookie else ''}"
        return f"{COOKIE}={token or ''}; Max-Age={SESSION_SECONDS if token else 0}; {attrs}"

    @staticmethod
    def _token(cookie_header: str | None) -> str | None:
        for part in (cookie_header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                return v
        return None


LOGIN_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trip Desk 로그인</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f5f7;color:#1c2330;font-family:system-ui,sans-serif}
main{width:min(360px,calc(100vw - 48px));padding:28px;background:#fff;border-radius:14px;box-shadow:0 4px 20px rgba(20,30,50,.1)}
h1{margin:0 0 6px;font-size:20px}p{margin:0 0 16px;color:#5b6472;font-size:14px}
label{display:grid;gap:6px;font-size:13px;color:#5b6472}
input{padding:10px 12px;border:1px solid #cfd5de;border-radius:8px;font:inherit}
button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:8px;background:#2457d6;color:#fff;font:inherit;font-weight:600;cursor:pointer}
:focus-visible{outline:3px solid #7aa2ff;outline-offset:2px}[role=alert]{color:#b3261e}
</style></head><body><main>
<h1>Trip Desk</h1><p>비밀번호를 입력하세요.</p><p id="err" role="alert" hidden></p>
<form id="f"><label>비밀번호 <input id="pw" type="password" autocomplete="current-password" required autofocus></label>
<button type="submit">로그인</button></form></main>
<script>
document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("err");
  const r = await fetch("/api/login", { method: "POST", headers: { "X-TripDesk": "1" }, body: JSON.stringify({ password: document.getElementById("pw").value }) }).catch(() => null);
  if (r && r.ok) return location.reload();
  err.textContent = !r ? "서버에 연결할 수 없어요." : r.status === 429 ? "너무 여러 번 틀렸어요. 1분 뒤에 다시 해 보세요." : "비밀번호가 맞지 않아요.";
  err.hidden = false;
});
</script></body></html>
"""
