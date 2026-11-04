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

    class Page(QWebEnginePage):
        def createWindow(self, _type):  # target=_blank, window.open → 기본 브라우저
            tmp = QWebEnginePage(self)
            tmp.urlChanged.connect(lambda u: (QDesktopServices.openUrl(u), tmp.deleteLater()))
            return tmp

        def acceptNavigationRequest(self, u, nav_type, is_main):  # 이 앱 밖의 주소는 창 안에서 열지 않는다
            if is_main and u.host() not in ("127.0.0.1", "localhost") and u.scheme() in ("http", "https"):
                QDesktopServices.openUrl(u)
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
    view.setWindowTitle("Trip Desk")
    view.load(QUrl(url))
    view.showMaximized()

    shot = os.environ.get("TRIPDESK_QT_SHOT")  # 시험용: 화면을 저장하고 끝낸다
    if shot:
        QTimer.singleShot(4000, lambda: (view.grab().save(shot), app.quit()))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
