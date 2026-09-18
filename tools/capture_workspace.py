"""Capture workspace entries with isolated preferences and an inert backend."""
import os
os.environ.pop("QT_QPA_PLATFORM", None)
import tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.core import Snapshot
from creative_toolbox.storage import Store, Settings
from creative_toolbox.platforms.unavailable import UnavailableBackend

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "demo"
ARTIFACTS = ROOT / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(exist_ok=True)


class DemoBackend:
    platform = "win32" if os.name == "nt" else "darwin"
    label = "本地工具 / 示例数据"
    def capture(self):
        return Snapshot(None, 0, 0, can_send=False)
    def send(self, *_):
        raise AssertionError("Capture must never send keys")


app = QApplication([])
app.setStyleSheet(STYLE)
app.setFont(QFont("Microsoft YaHei UI" if os.name == "nt" else "PingFang SC", 10))
with tempfile.TemporaryDirectory() as tmp:
    window = MainWindow(DemoBackend(), Store(Path(tmp), DemoBackend.platform), Settings(), start_timer=False)
    window.resize(1180, 800)
    window.show()

    def home():
        window.grab().save(str(OUT / "workspace-home.png"))
        window.navigate("tools")
        QTimer.singleShot(200, directory)

    def directory():
        window.grab().save(str(OUT / "workspace-tools.png"))
        window.entry_pages["tools"].search.setText("毫米")
        QTimer.singleShot(150, search)

    def search():
        window.grab().save(str(ARTIFACTS / "workspace-search.png"))
        window.resize(1020, 720)
        window.navigate("library")
        QTimer.singleShot(150, compact)

    def compact():
        window.grab().save(str(ARTIFACTS / "workspace-library-compact.png"))
        window.hide()
        degraded = MainWindow(
            UnavailableBackend(DemoBackend.platform, "系统保存适配未能加载（ImportError）。请检查系统依赖后重启；字体、配色与换算仍可使用。"),
            Store(Path(tmp) / "degraded", DemoBackend.platform), Settings(), start_timer=False)
        degraded.navigate("protection")
        degraded.show()
        window.degraded = degraded
        QTimer.singleShot(200, finish)

    def finish():
        window.degraded.grab().save(str(ARTIFACTS / "workspace-degraded.png"))
        window.degraded.quit_app()
        window.quit_app()

    QTimer.singleShot(350, home)
    app.exec()
