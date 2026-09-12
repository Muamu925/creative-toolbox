"""Capture actual widget states with isolated demo data; does not control other apps.

Run with the development Python on Windows. GIF encoding is a separate optional
Pillow step documented in docs/LAUNCH.md; Pillow is not a runtime dependency.
"""
import os
os.environ.pop('QT_QPA_PLATFORM', None)
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer, QPoint, QMimeData
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QFileDialog

from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from tests.test_safety import FakeBackend

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts' / 'demo-frames'
OUTPUT.mkdir(parents=True, exist_ok=True)
PUBLIC = ROOT / 'assets' / 'demo'
PUBLIC.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(QFont('Microsoft YaHei UI', 10))
app.setStyleSheet(STYLE)
original = QMimeData()
clipboard = app.clipboard()
for mime in clipboard.mimeData().formats():
    original.setData(mime, clipboard.mimeData().data(mime))
last_copied = None

with tempfile.TemporaryDirectory() as tmp:
    backend = FakeBackend()
    backend.label = '示例数据 / UI demo'
    window = MainWindow(backend, Store(Path(tmp), 'win32'), Settings(), start_timer=False)
    window.resize(1100, 800)
    window.show()
    window.switch_page(4)
    page = window.palette_page
    steps = [
        ('01  项目配色 / Project palettes', lambda: None),
        ('02  打开悬浮色卡 / Floating palette', page.open_floating),
        ('03  选择复制格式 / Choose a copy format', lambda: page.model.set_preferences(style='HEX（无 #）')),
        ('04  点击即可复制 / Click to copy', lambda: page.floating.swatches[0].click()),
        ('05  收藏常用颜色 / Favorite your colors', lambda: (page.model.toggle_favorite(0), page.model.toggle_favorite(3), page.floating.favorites.setChecked(True))),
        ('06  导出色卡 / Export a swatch sheet', lambda: export()),
    ]
    def export():
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(PUBLIC / 'palette-sheet.png'), 'PNG')):
            page.export_png()

    index = 0
    def begin_step():
        global last_copied
        title, action = steps[index]
        action()
        if index == 3:
            last_copied = clipboard.text()
        QTimer.singleShot(250, capture)

    def capture():
        global index
        canvas = QImage(1280, 880, QImage.Format.Format_RGB32)
        canvas.fill(QColor('#E8EEE8'))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        heading = QFont('Microsoft YaHei UI')
        heading.setPixelSize(27)
        heading.setBold(True)
        painter.setFont(heading)
        painter.setPen(QColor('#203C31'))
        painter.drawText(28, 48, steps[index][0])
        small = QFont(heading)
        small.setPixelSize(15)
        small.setBold(False)
        painter.setFont(small)
        painter.drawText(28, 76, 'Creative Toolbox 0.2.0 · 实际界面操作序列 / Actual UI states, sample data')
        shot = window.grab().scaled(910, 700, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        shot.setDevicePixelRatio(1.0)
        painter.drawPixmap(20, 110, shot)
        if page.floating and page.floating.isVisible():
            floating = page.floating.grab().scaled(320, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            floating.setDevicePixelRatio(1.0)
            painter.drawPixmap(945, 220, floating)
        else:
            painter.drawText(954, 270, 'Floating palettes')
            painter.drawText(954, 300, 'Copy · Favorite · Export')
        painter.drawText(28, 838, 'github.com/Muamu925/creative-toolbox')
        painter.end()
        canvas.save(str(OUTPUT / f'{index:02}.png'))
        if index == 2:
            canvas.save(str(PUBLIC / 'workspace.png'))
        index += 1
        if index < len(steps):
            QTimer.singleShot(80, begin_step)
        else:
            if last_copied is not None and clipboard.text() == last_copied:
                clipboard.setMimeData(original)
            window.quit_app()
    QTimer.singleShot(400, begin_step)
    app.exec()
print('Captured six actual UI states in artifacts/demo-frames.')
