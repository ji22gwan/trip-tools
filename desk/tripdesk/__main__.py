import argparse
import threading
import webbrowser

from .server import serve
from .store import Store, data_dir


def main():
    ap = argparse.ArgumentParser(description="Trip Desk: 출장 패키지 만들기")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    try:
        httpd, port = serve(Store(), a.port)
    except OSError:
        httpd, port = serve(Store(), 0)
    url = f"http://127.0.0.1:{port}/"
    print(f"Trip Desk 실행 중: {url}\n데이터 폴더: {data_dir()}\n종료: Ctrl+C")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("종료합니다.")


if __name__ == "__main__":
    main()
