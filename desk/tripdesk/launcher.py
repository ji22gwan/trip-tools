"""프로그램처럼 띄우기: 브라우저를 주소창 없는 앱 창으로 열고, 창을 닫으면 서버도 끝낸다."""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HEARTBEAT_TIMEOUT = 150  # 앱 창을 못 쓰는 대체 방식: 이 시간(초) 동안 화면이 신호를 안 보내면 종료(숨은 탭은 신호가 느려질 수 있어 넉넉히)


def find_browser() -> list[str] | None:
    """앱 창(--app)을 지원하는 크롬 계열을 찾는다. TRIPDESK_BROWSER 로 직접 지정할 수 있다."""
    env = os.environ.get("TRIPDESK_BROWSER")
    if env:
        return [env]
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "microsoft-edge-stable", "brave-browser"]
    for n in names:
        p = shutil.which(n)
        if p:
            return [p]
    cands = []
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [Path(base) / "Google/Chrome/Application/chrome.exe", Path(base) / "Microsoft/Edge/Application/msedge.exe"]
    elif sys.platform == "darwin":
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    for c in cands:
        if c.exists():
            return [str(c)]
    return None


def already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            return b'"tripdesk"' in r.read()
    except Exception:  # noqa: BLE001
        return False


def open_app_window(url: str, profile_dir: Path):
    """앱 창을 연다. 성공하면 Popen, 크롬 계열이 없으면 None."""
    b = find_browser()
    if not b:
        return None
    profile_dir.mkdir(parents=True, exist_ok=True)  # 전용 프로필: 평소 브라우저와 섞이지 않고, 창이 닫힐 때까지 프로세스가 살아 있다
    args = b + [f"--app={url}", f"--user-data-dir={profile_dir}", "--window-size=1320,880", "--class=tripdesk", "--name=tripdesk",
                "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def watch_and_quit(httpd, proc, api, started: float) -> None:
    """앱 창이 닫히면 서버를 끝낸다. 창 프로세스가 곧바로 끝나 버리면(이미 떠 있는 브라우저에 넘겨진 경우) 화면 신호(heartbeat)로 판단한다."""
    def run():
        if proc is not None:
            proc.wait()
            if time.time() - started > 4:
                httpd.shutdown()
                return
        # 신호 방식: 화면이 한 번이라도 신호를 보낸 뒤 오래 끊기면 종료
        while True:
            time.sleep(5)
            last = api.last_ping
            if last and time.time() - last > HEARTBEAT_TIMEOUT:
                httpd.shutdown()
                return

    threading.Thread(target=run, daemon=True).start()
