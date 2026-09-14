"""Capture the real Windows font workspace with isolated metadata."""
import os
os.environ.pop("QT_QPA_PLATFORM", None)
import tempfile
from pathlib import Path
from PySide6.QtCore import QTimer, QItemSelectionModel
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from tests.test_safety import FakeBackend

root = Path(__file__).resolve().parents[1]
out = root / "assets" / "demo"
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyleSheet(STYLE)
app.setFont(QFont("Microsoft YaHei UI", 10))
with tempfile.TemporaryDirectory() as tmp:
    backend = FakeBackend()
    backend.label = "本机字体 / 示例整理数据"
    window = MainWindow(backend, Store(Path(tmp), "win32"), Settings(), start_timer=False)
    window.resize(1280, 900)
    page = window.font_page
    available = page.model.available
    families = [f for f in ["Microsoft YaHei", "Microsoft YaHei UI", "SimSun", "KaiTi", "Arial", "Georgia", "Consolas"] if f in available]
    if len(families) < 3:
        families = list(available)[:5]
    print("Available families:", len(available), "Demo:", families, flush=True)
    gid = page.library.add_group("音乐节海报")
    page.library.add_group("字幕与片头")
    page.library.membership(families, gid)
    page.library.tag(families, "标题候选")
    page.library.edit([f for f in ["Arial", "Consolas"] if f in families], favorite=True)
    page.model.reload()
    page.populate_groups("group:"+gid)
    page.sample.setPlainText("秋日音乐节  Autumn Sounds 2026")
    page.size.setValue(25)
    window.switch_page(6)
    window.show()
    def capture():
        window.grab().save(str(out / "font-library.png"))
        for row in range(min(3, page.proxy.rowCount())):
            page.list.selectionModel().select(page.proxy.index(row, 0), QItemSelectionModel.SelectionFlag.Select)
        page.compare_selected()
        QTimer.singleShot(350, finish)
    def finish():
        window.grab().save(str(out / "font-compare.png"))
        window.resize(1020, 720)
        QTimer.singleShot(250, compact)
    def compact():
        print("Compact size:", window.width(), window.height(), "Preview height:", page.previews[0].height(), flush=True)
        if "Arial" in page.model.available and "Bold" in page.model.available["Arial"]["styles"]:
            page.fonts[0].setCurrentText("Arial")
            page.styles[0].setCurrentText("Bold")
            assert page.previews[0].font().bold(), "Real Bold style must reach the preview"
        (root / "artifacts").mkdir(exist_ok=True)
        window.grab().save(str(root / "artifacts" / "font-compact.png"))
        window.quit_app()
    QTimer.singleShot(600, capture)
    app.exec()
