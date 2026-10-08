"""Capture only this app, with isolated data and no native input backend.

Run on macOS with .venv-mac/bin/python tools/mac_smoke.py.
"""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from creative_toolbox.platforms.unavailable import UnavailableBackend
from creative_toolbox.storage import Store
from creative_toolbox.ui import MainWindow, STYLE

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
app.setStyleSheet(STYLE)
temporary = tempfile.TemporaryDirectory(prefix="creative-toolbox-mac-")
store = Store(Path(temporary.name), "darwin")
window = MainWindow(UnavailableBackend("darwin", "界面检查模式"), store, store.load(), False)
window.reduce_motion.setChecked(True)
output = ROOT / "artifacts" / "mac-review"
output.mkdir(parents=True, exist_ok=True)
steps = [(width, height, route) for width, height in ((1180, 800), (1020, 720))
         for route in ("home", "library", "tools", "assets", "fonts", "palettes", "calculators", "settings", "help")]
errors = []


def capture_next():
    try:
        if not steps:
            window.mac_desktop.show_launcher()
            window.mac_desktop.launcher.search.setText("字体")
            app.processEvents()
            window.mac_desktop.launcher.grab().save(str(output / "launcher.png"))
            QTest.keyClick(window.mac_desktop.launcher.search, Qt.Key.Key_Return)
            assert window.pages.currentWidget() is window.tool_pages["fonts"]
            window.quit_app()
            return
        width, height, route = steps.pop(0)
        window.resize(width, height)
        if route in ("assets", "fonts", "palettes", "calculators"):
            window.open_tool(route)
            assert route in window.tool_pages, f"Failed to load {route}"
        else:
            window.navigate(route)
        app.processEvents()
        window.grab().save(str(output / f"{route}-{width}.png"))
        print(f"Captured {route} at {window.width()} x {window.height()}", flush=True)
        QTimer.singleShot(150, capture_next)
    except Exception as exc:
        errors.append(str(exc))
        window.quit_app()


window.show()
QTimer.singleShot(300, capture_next)
app.exec()
temporary.cleanup()
if errors:
    raise SystemExit("; ".join(errors))
print("Native page and launcher smoke checks passed.")
