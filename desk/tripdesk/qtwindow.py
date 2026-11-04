"""Trip Desk 전용 창 (PyQt6 + QtWebEngine). 크롬 없이 자체 엔진으로 화면을 보여 준다.

크롬 앱 창과 달리 크롬의 업데이트 알림이 뜨지 않고, 항상 최대화로 열린다.
링크(target=_blank)는 기본 브라우저로, 파일 저장(ZIP·Word 등)은 저장 위치를 물어보고 받는다.
"""
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from PyQt6.QtCore import QStandardPaths, QTimer, QUrl
    from PyQt6.QtGui import QDesktopServices, QIcon
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QFileDialog

    url = argv[1] if len(argv) > 1 else "http://127.0.0.1:8765/"
    app = QApplication(["tripdesk"])
    app.setApplicationName("tripdesk")
    app.setDesktopFileName("tripdesk")
    icon = Path(__file__).resolve().parent.parent / "assets" / "icon-256.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    profile = QWebEngineProfile("tripdesk")  # 이름이 있는 프로필 = 설정(localStorage)이 보존된다
    profile.setHttpAcceptLanguage("ko,en")

    opened = []  # 시험용 기록

    def open_external(u):
        opened.append(u.toString())
        if os.environ.get("TRIPDESK_QT_SHOT"):
            print("OPEN", u.toString(), flush=True)
            return
        QDesktopServices.openUrl(u)

    class Catcher(QWebEnginePage):
        """새 창 요청(target=_blank, window.open)이 향하는 곳. 주소를 받는 즉시 기본 브라우저로 넘기고 막는다."""

        def acceptNavigationRequest(self, u, nav_type, is_main):
            open_external(u)
            return False

    class Page(QWebEnginePage):
        def createWindow(self, _type):
            self._catcher = Catcher(self.profile(), self)
            return self._catcher

        def acceptNavigationRequest(self, u, nav_type, is_main):  # 이 앱 밖의 주소는 창 안에서 열지 않는다
            if is_main and u.host() not in ("127.0.0.1", "localhost") and u.scheme() in ("http", "https"):
                open_external(u)
                return False
            return super().acceptNavigationRequest(u, nav_type, is_main)

    view = QWebEngineView()
    page = Page(profile, view)
    view.setPage(page)
    s = view.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)  # '프롬프트 복사'
    s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

    def on_download(item):
        name = item.downloadFileName() or "download"
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        path, _ = QFileDialog.getSaveFileName(view, "저장 위치", str(Path(start) / name))
        if not path:
            item.cancel()
            return
        item.setDownloadDirectory(str(Path(path).parent))
        item.setDownloadFileName(Path(path).name)
        item.accept()

    profile.downloadRequested.connect(on_download)
    from PyQt6.QtGui import QColor

    page.setBackgroundColor(QColor("#f4f6f8"))
    view.setWindowTitle("Trip Desk")
    avail = app.primaryScreen().availableGeometry()
    view.setGeometry(avail)  # 최대화 상태와 같은 크기로 미리 맞춰 두면 창 관리자가 크기를 다시 바꾸지 않는다
    shown = []

    def show_once(*_):
        # 화면이 그려진 뒤 딱 한 번만 최대화로 연다: 흰 화면 → 줄었다 늘었다 하는 깜박임을 없앤다
        if not shown:
            shown.append(1)
            view.showMaximized()

    page.loadFinished.connect(show_once)
    QTimer.singleShot(2500, show_once)  # 로딩이 늦어도 창은 뜨게
    view.load(QUrl(url))

    shot = os.environ.get("TRIPDESK_QT_SHOT")  # 시험용: 화면을 저장하고 끝낸다
    if shot:
        QTimer.singleShot(4000, lambda: (view.grab().save(shot), app.quit()))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
