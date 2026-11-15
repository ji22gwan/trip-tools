"""서버 모드: 로그인, 허용 호스트, 종료 차단, 지도 내려받기의 내부 주소 차단."""
import json
import stat
import threading
import urllib.error
import urllib.request

import pytest

from tripdesk import auth, mapfinder, server

PW = "correct-horse"


@pytest.fixture
def srv(store, tmp_path):
    auth.set_password(tmp_path, PW)
    a = auth.Auth(tmp_path)
    httpd, port = server.serve(store, 0, auth=a, allowed_hosts=["trip.example.com"])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", a
    httpd.shutdown()


def call(base, method, path, body=None, cookie=None, host=None, header=True):
    h = {"X-TripDesk": "1"} if header else {}
    if cookie:
        h["Cookie"] = cookie
    if host:
        h["Host"] = host
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login(base, pw=PW):
    code, _, headers = call(base, "POST", "/api/login", {"password": pw})
    return code, (headers.get("Set-Cookie") or "").split(";")[0]


def test_everything_needs_login(srv):
    base, _ = srv
    assert call(base, "GET", "/api/trips")[0] == 401
    assert call(base, "POST", "/api/trips", {"name": "x"})[0] == 401
    assert call(base, "GET", "/app.js")[0] == 401  # 화면 코드도 로그인 뒤에만
    code, body, _ = call(base, "GET", "/")
    assert code == 200 and "비밀번호" in body.decode() and "app.js" not in body.decode()


def test_login_logout(srv):
    base, _ = srv
    assert login(base, "wrong-password")[0] == 401
    assert call(base, "POST", "/api/login", {"nope": 1})[0] == 401
    code, cookie = login(base)
    assert code == 200 and cookie.startswith("tripdesk_session=")
    assert call(base, "GET", "/api/trips", cookie=cookie)[0] == 200
    assert b"app.js" in call(base, "GET", "/", cookie=cookie)[1]
    assert json.loads(call(base, "GET", "/api/ping", cookie=cookie)[1])["server"] is True
    assert call(base, "POST", "/api/logout", {}, cookie=cookie)[0] == 200
    assert call(base, "GET", "/api/trips", cookie=cookie)[0] == 401
    assert call(base, "GET", "/api/trips", cookie="tripdesk_session=guess")[0] == 401


def test_cookie_flags(srv, tmp_path):
    _, a = srv
    assert "HttpOnly" in a.cookie("t") and "SameSite=Lax" in a.cookie("t") and "Secure" not in a.cookie("t")
    assert "Secure" in auth.Auth(tmp_path, secure_cookie=True).cookie("t")


def test_login_is_rate_limited(srv):
    base, _ = srv
    codes = [login(base, "wrong-password")[0] for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert login(base)[0] == 429  # 맞는 비밀번호도 잠시 막힌다


def test_login_needs_the_custom_header(srv):
    base, _ = srv
    assert call(base, "POST", "/api/login", {"password": PW}, header=False)[0] == 403


def test_cannot_quit_from_the_screen(srv):
    base, _ = srv
    _, cookie = login(base)
    assert call(base, "POST", "/api/quit", {}, cookie=cookie)[0] == 400
    assert call(base, "GET", "/api/trips", cookie=cookie)[0] == 200  # 서버는 계속 돈다


def test_allowed_hosts(srv):
    base, _ = srv
    _, cookie = login(base)
    assert call(base, "GET", "/api/trips", cookie=cookie, host="trip.example.com")[0] == 200
    assert call(base, "GET", "/api/trips", cookie=cookie, host="evil.example.com")[0] == 403


def test_password_is_hashed_and_private(tmp_path):
    auth.set_password(tmp_path, PW)
    p = auth.auth_file(tmp_path)
    assert PW not in p.read_text()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        auth.set_password(tmp_path, "short")


def test_local_mode_is_unchanged(store):
    httpd, port = server.serve(store, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        assert call(base, "GET", "/api/trips")[0] == 200  # 로그인 없음
        assert json.loads(call(base, "GET", "/api/ping")[1])["server"] is False
    finally:
        httpd.shutdown()


def test_map_download_refuses_internal_addresses(monkeypatch):
    monkeypatch.setattr(mapfinder, "PUBLIC_ONLY", True)
    for url in ["http://127.0.0.1:8765/api/trips", "http://localhost/x.pdf", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/map.pdf", "http://[::1]/x"]:
        with pytest.raises(mapfinder.MapError):
            mapfinder.fetch(url)
