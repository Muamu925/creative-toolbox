"""Capture the image inbox with programmatically drawn sample images and isolated data."""
import os
os.environ.pop("QT_QPA_PLATFORM", None)
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from creative_toolbox.core import Snapshot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "demo"
ART = ROOT / "artifacts" / "asset-review"
OUT.mkdir(parents=True, exist_ok=True)
ART.mkdir(parents=True, exist_ok=True)


class DemoBackend:
    platform = "win32" if os.name == "nt" else "darwin"
    label = "本地素材 / 示例数据"
    def capture(self):
        return Snapshot(None, 0, 0, can_send=False)
    def send(self, *_):
        raise AssertionError("No keys sent during capture")


def sample(path, background, accent, title, tall=False):
    image = QImage(800, 1050 if tall else 560, QImage.Format.Format_RGB32)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(accent))
    painter.drawEllipse(330, 100, 420, 420)
    painter.setBrush(QColor("#e6dec9"))
    painter.drawRect(0, 350, 480, 250)
    painter.setPen(QColor("#203c31"))
    font = QFont("Arial")
    font.setPixelSize(60)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(45, 100, title)
    font.setPixelSize(22)
    painter.setFont(font)
    painter.drawText(48, image.height() - 42, "CREATIVE TOOLBOX / SAMPLE REFERENCE")
    painter.end()
    assert image.save(str(path), "PNG")


app = QApplication([])
app.setStyleSheet(STYLE)
app.setFont(QFont("Microsoft YaHei UI" if os.name == "nt" else "PingFang SC", 10))
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    window = MainWindow(DemoBackend(), Store(root / "data", DemoBackend.platform), Settings(), start_timer=False)
    window.resize(1180, 800)
    window.open_tool("assets")
    page = window.tool_pages["assets"]
    window.show()

    def empty():
        window.grab().save(str(ART / "empty.png"))
        ids = []
        for index, (title, bg, accent, word) in enumerate([
            ("秋日音乐节 · 海报构图", "#d7dfce", "#748e68", "AUTUMN"),
            ("自然色调 · 封面方向", "#eadfc5", "#b48768", "NATURE"),
            ("片头版式 · 暖色研究", "#e9d7d2", "#c88470", "RHYTHM"),
        ]):
            path = root / f"sample-{index}.png"
            sample(path, bg, accent, word, index == 0)
            asset_id, _ = page.store.add_file(path)
            page.store.update(asset_id, title, ["海报", "自然"] if index == 0 else ["候选"],
                              "程序生成示例 · 非外部作品", "留意标题与留白的关系。", index == 0)
            ids.append(asset_id)
        page.refresh(selected=ids[0])
        window.demo_ids = ids
        QTimer.singleShot(250, full)

    def full():
        window.grab().save(str(OUT / "asset-inbox.png"))
        window.resize(1020, 720)
        QTimer.singleShot(200, compact)

    def compact():
        window.grab().save(str(ART / "compact.png"))
        page.open_reference()
        QTimer.singleShot(200, reference)

    def reference():
        page.reference.grab().save(str(OUT / "asset-reference.png"))
        page.reference.close()
        page.store.set_deleted(window.demo_ids[2], True)
        page.scope.setCurrentIndex(page.scope.findData("trash"))
        QTimer.singleShot(150, finish)

    def finish():
        window.grab().save(str(ART / "trash.png"))
        window.quit_app()

    QTimer.singleShot(300, empty)
    app.exec()
