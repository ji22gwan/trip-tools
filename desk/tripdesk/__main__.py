import argparse
import os
import sys
import threading
import time
import webbrowser

from . import auth, launcher, mapfinder
from .server import serve
from .store import Store, data_dir


def main():
    ap = argparse.ArgumentParser(description="Trip Desk: 출장 준비·보고서 도구")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    ap.add_argument("--app", action="store_true", help="주소창 없는 앱 창으로 열고, 창을 닫으면 종료한다")
    ap.add_argument("--server", action="store_true", help="서버 모드: 로그인 필수, 브라우저를 열지 않고 계속 실행한다")
    ap.add_argument("--set-password", action="store_true", help="서버 모드 비밀번호를 정한다")
    a = ap.parse_args()

    if a.set_password:
        import getpass

        pw = os.environ.get("TRIPDESK_PASSWORD") or getpass.getpass("새 비밀번호: ")
        try:
            auth.set_password(data_dir(), pw)
        except ValueError as e:
            sys.exit(str(e))
        print(f"비밀번호를 저장했어요: {auth.auth_file(data_dir())}")
        return

    if a.server:
        if not auth.auth_file(data_dir()).is_file():
            sys.exit("서버 모드는 비밀번호가 필요해요. 먼저 실행하세요: python3 -m tripdesk --set-password")
        # 리버스 프록시(HTTPS) 뒤에서 쓸 때: TRIPDESK_ALLOWED_HOSTS=trip.example.com TRIPDESK_SECURE_COOKIE=1
        hosts = [h.strip() for h in os.environ.get("TRIPDESK_ALLOWED_HOSTS", "").split(",") if h.strip()]
        mapfinder.PUBLIC_ONLY = True
        httpd, port = serve(Store(), a.port, host=os.environ.get("TRIPDESK_HOST", "127.0.0.1"), allowed_hosts=hosts,
                            auth=auth.Auth(data_dir(), secure_cookie=os.environ.get("TRIPDESK_SECURE_COOKIE") == "1"))
        print(f"Trip Desk 서버 모드: http://{httpd.server_address[0]}:{port}/\n데이터 폴더: {data_dir()}\n종료: Ctrl+C", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("종료합니다.")
        return

    if a.app:
        # 터미널 없이 실행되므로 오류가 사라지지 않게 로그 파일에 남긴다
        data_dir().mkdir(parents=True, exist_ok=True)
        log = open(data_dir() / "tripdesk.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} 시작")
        if launcher.already_running(a.port):  # 이미 떠 있으면 창만 하나 더 연다
            launcher.open_app_window(f"http://127.0.0.1:{a.port}/", data_dir() / "browser-profile")
            return

    try:
        httpd, port, api = serve(Store(), a.port, with_api=True)
    except OSError:
        httpd, port, api = serve(Store(), 0, with_api=True)
    url = f"http://127.0.0.1:{port}/"
    print(f"Trip Desk 실행 중: {url}\n데이터 폴더: {data_dir()}\n종료: Ctrl+C")

    if a.app:
        started = time.time()
        proc = launcher.open_app_window(url, data_dir() / "browser-profile")
        if proc is None:
            print("앱 창을 지원하는 브라우저(Chrome/Edge/Chromium)를 찾지 못해 기본 브라우저로 열어요.")
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        launcher.watch_and_quit(httpd, proc, api, started)
    elif not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("종료합니다.")


if __name__ == "__main__":
    main()
