import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


class Site(BaseHTTPRequestHandler):
    """가짜 전시회 사이트."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        routes = {
            "/": (200, "text/html", b'<html><body><a href="/docs/privacy.pdf">Privacy</a>'
                  b'<a href="/docs/Hallenplan_2026.pdf">Hall plan</a><a href="/visit/plan">Floor plan page</a>'
                  b'<a href="https://other.example/x.pdf">Floor plan elsewhere</a></body></html>'),
            "/visit/plan": (200, "text/html", b'<html><body><img src="/img/venue_map.png" alt="Venue map"></body></html>'),
            "/docs/Hallenplan_2026.pdf": (200, "application/pdf", PDF),
            "/docs/privacy.pdf": (200, "application/pdf", PDF),
            "/img/venue_map.png": (200, "image/png", PNG),
            "/fake.pdf": (200, "application/pdf", b"<html>Access denied page</html>"),
            "/blocked.pdf": (403, "text/html", b"no"),
        }
        code, ctype, body = routes.get(p, (404, "text/html", b"nf"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="session")
def site():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def store(tmp_path):
    from tripdesk.store import Store

    return Store(tmp_path / "home")
