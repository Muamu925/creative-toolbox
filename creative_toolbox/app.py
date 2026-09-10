from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Creative Toolbox")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--screenshot", type=Path, help="Capture this app's own UI, then exit; always observation mode")
    parser.add_argument("--quit-after", type=int, help="Exit after N seconds (smoke testing)")
    args = parser.parse_args()
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .platforms import create_backend
    from .storage import Store, data_directory
    from .ui import MainWindow, STYLE

    app = QApplication(sys.argv[:1])
    app.setApplicationName("CreativeToolbox")
    app.setOrganizationName("CreativeToolbox")
    app.setQuitOnLastWindowClosed(False)
    font = QFont("Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC", 10)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    store = Store(args.data_dir or data_directory(), sys.platform)
    store.root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(store.root / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "工具箱已在运行", "请从系统托盘或菜单栏打开已有的工具箱。")
        return 0
    try:
        backend = create_backend()
    except Exception as exc:
        QMessageBox.critical(None, "启动失败", f"系统适配无法加载：{type(exc).__name__}: {exc}")
        return 1
    window = MainWindow(backend, store, store.load())
    window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
            window.quit_app()
        QTimer.singleShot(1200, capture)
    if args.quit_after:
        QTimer.singleShot(args.quit_after * 1000, window.quit_app)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
