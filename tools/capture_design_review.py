"""Render review states using isolated data and an inert backend."""
import os
# Use native platform fonts by default; CI can explicitly choose offscreen.
import sys
import tempfile
from pathlib import Path
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from creative_toolbox.platforms.unavailable import UnavailableBackend


def main():
    output = Path("artifacts/design-review") / (sys.argv[1] if len(sys.argv) > 1 else "after")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    with tempfile.TemporaryDirectory() as temp:
        window = MainWindow(UnavailableBackend("win32", "隔离审阅：不连接其他应用"),
                            Store(Path(temp), "win32"), Settings(), start_timer=False)
        window.show()
        for route in ("home", "tools", "library", "palettes", "calculators", "fonts", "protection", "settings", "help"):
            if route in ("palettes", "calculators", "fonts"):
                window.open_tool(route)
            else:
                window.navigate(route)
            for width, height in ((1180, 800), (1020, 720)):
                window.resize(width, height)
                app.processEvents()
                app.processEvents()
                window.grab().save(str(output / f"{route}-{width}.png"))
        window.reduce_transparency.setChecked(True)
        window.navigate("settings")
        app.processEvents()
        window.grab().save(str(output / "settings-solid-1020.png"))
        window.quit_app()
        window.close()
    print(output.resolve())


if __name__ == "__main__":
    main()
