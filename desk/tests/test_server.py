import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import PDF
from tripdesk import server


@pytest.fixture
def app(store):
    httpd, port = server.serve(store, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", port
    httpd.shutdown()


def call(base, method, path, body=None, raw=False, headers=None):
    h = {"X-TripDesk": "1", **(headers or {})}
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_full_flow(app, site):
    base, _ = app
    s, b, _ = call(base, "POST", "/api/trips", {"name": "Test Fair", "venue": "V", "start": "2026-11-24", "end": "2026-11-25"})
    tid = json.loads(b)["trip"]["id"]
    s, b, _ = call(base, "POST", f"/api/trips/{tid}/maps/find", {"siteUrl": site + "/"})
    r = json.loads(b)
    assert s == 200 and r["candidates"][0]["url"].endswith("Hallenplan_2026.pdf")
    s, b, _ = call(base, "POST", f"/api/trips/{tid}/maps/download", {"url": r["candidates"][0]["url"]})
    assert s == 200 and json.loads(b)["view"]["maps"][0]["name"].endswith(".pdf")
    s, b, _ = call(base, "POST", f"/api/trips/{tid}/maps/upload?filename=%EB%82%B4%EC%A7%80%EB%8F%84.pdf", PDF, raw=True)
    assert s == 200 and len(json.loads(b)["maps"]) == 2
    s, b, _ = call(base, "POST", f"/api/trips/{tid}/maps/upload?filename=x.pdf", b"<html>", raw=True)
    assert s == 400
    csv = "업체명,카테고리,일차\nA,로봇,1\nB,센서,2\n".encode()
    s, b, _ = call(base, "POST", f"/api/trips/{tid}/companies/import?filename=l.csv", csv, raw=True)
    assert json.loads(b)["import"]["added"] == 2
    s, b, h = call(base, "GET", f"/api/trips/{tid}/package")
    assert s == 200 and h["Content-Type"] == "application/zip" and b[:2] == b"PK"
    s, b, _ = call(base, "GET", "/")
    assert s == 200 and b"Trip Desk" in b


def test_rejects_foreign_host_and_missing_header(app):
    base, port = app
    assert call(base, "GET", "/api/trips", headers={"Host": "evil.example"})[0] == 403
    req = urllib.request.Request(base + "/api/trips", data=b"{}", method="POST")  # X-TripDesk 없음
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403
    assert call(base, "GET", "/../tripdesk/store.py")[0] in (403, 404)
    assert call(base, "GET", "/api/trips/..%2F..%2Fetc")[0] == 400
