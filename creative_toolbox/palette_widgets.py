"""Floating palette window and deterministic PNG swatch-sheet export."""
from pathlib import Path
import math

from PySide6.QtCore import Qt, QRect, QSaveFile, QIODevice, QTimer
from PySide6.QtGui import QColor, QColorSpace, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .design_core import COPY_FORMATS, contrast_ratio, validate_library


def label(value):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def swatch_ink(code):
    return '#FFFFFF' if contrast_ratio(code, '#FFFFFF') >= contrast_ratio(code, '#000000') else '#000000'


class FloatingPalette(QWidget):
    def __init__(self, model):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.model = model
        self.setWindowTitle('悬浮色卡 · Creative Toolbox')
        self.resize(440, 380)
        self.setMinimumSize(330, 200)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self._expanded_height = 380
        self._screens = []
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(label('PALETTE / 随手取色'), 1)
        self.pin = QCheckBox('置顶')
        self.pin.setChecked(True)
        header.addWidget(self.pin)
        self.collapse = QPushButton('折叠')
        header.addWidget(self.collapse)
        root.addLayout(header)
        self.palettes = QComboBox()
        root.addWidget(self.palettes)
        options = QHBoxLayout()
        self.format = QComboBox()
        self.format.addItems(COPY_FORMATS)
        options.addWidget(self.format, 1)
        self.favorites = QCheckBox('仅收藏')
        options.addWidget(self.favorites)
        root.addLayout(options)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.cards = QWidget()
        self.grid = QGridLayout(self.cards)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.area.setWidget(self.cards)
        root.addWidget(self.area, 1)
        self.status = label('点击颜色复制；拖动窗口标题栏移动。')
        root.addWidget(self.status)
        self.pin.toggled.connect(self.set_pinned)
        self.collapse.clicked.connect(self.toggle_collapsed)
        self.palettes.currentIndexChanged.connect(lambda index: model.set_preferences(selected=index))
        self.format.currentTextChanged.connect(lambda style: model.set_preferences(style=style))
        self.favorites.toggled.connect(self.refresh)
        model.changed.connect(self.refresh)
        model.message.connect(self.status.setText)
        app = QApplication.instance()
        app.screenAdded.connect(self.watch_screen)
        app.screenRemoved.connect(self.screen_removed)
        for screen in app.screens():
            self.watch_screen(screen)
        self.refresh()

    def refresh(self, *_):
        self.palettes.blockSignals(True)
        self.palettes.clear()
        self.palettes.addItems([p['name'] for p in self.model.library['palettes']])
        self.palettes.setCurrentIndex(self.model.selected)
        self.palettes.blockSignals(False)
        self.format.blockSignals(True)
        self.format.setCurrentText(self.model.copy_format)
        self.format.blockSignals(False)
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.swatches = []
        for index, color in enumerate(self.model.palette['colors']):
            if self.favorites.isChecked() and not color.get('favorite', False):
                continue
            value = self.model.copy_text(index)
            name = ('★ ' if color.get('favorite') else '') + (color['name'] or '未命名')
            swatch = QPushButton(value)
            swatch.setMinimumHeight(62)
            swatch.setToolTip(name + '\n' + value)
            swatch.setAccessibleName(name + '，复制 ' + value)
            swatch.setStyleSheet(f'background:{color["hex"]}; color:{swatch_ink(color["hex"])}; border:none; border-radius:8px; padding:6px;')
            swatch.clicked.connect(lambda checked=False, i=index: self.copy_color(i))
            i = len(self.swatches)
            self.grid.addWidget(swatch, i // 2, i % 2)
            self.swatches.append(swatch)
        if not self.swatches:
            self.grid.addWidget(label('暂无收藏颜色。' if self.favorites.isChecked() else '色板为空，请在配色工作台添加颜色。'), 0, 0, 1, 2)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

    def copy_color(self, index):
        value = self.model.copy_text(index)
        QApplication.clipboard().setText(value)
        self.status.setText('已复制 ' + value)

    def set_pinned(self, enabled):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.keep_on_screen()

    def toggle_collapsed(self):
        if self.area.isHidden():
            self.area.show()
            self.setMinimumHeight(200)
            self.resize(self.width(), self._expanded_height)
            self.collapse.setText('折叠')
        else:
            self._expanded_height = self.height()
            self.area.hide()
            self.setMinimumHeight(0)
            self.layout().activate()
            self.resize(self.width(), self.sizeHint().height())
            self.collapse.setText('展开')
        self.keep_on_screen()

    def watch_screen(self, screen):
        self._screens.append(screen)
        screen.availableGeometryChanged.connect(self.keep_on_screen)
        QTimer.singleShot(0, self.keep_on_screen)

    def screen_removed(self, screen):
        self._screens = [s for s in self._screens if s is not screen]
        QTimer.singleShot(0, self.keep_on_screen)

    def keep_on_screen(self, *_):
        if not self.isVisible():
            return
        app = QApplication.instance()
        screen = app.screenAt(self.frameGeometry().center()) or app.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
        y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
        self.move(self.pos().x() + x - frame.left(), self.pos().y() + y - frame.top())

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.keep_on_screen)


def palette_image(palette: dict) -> QImage:
    """Draw saved sRGB colors and complete names, independent of screen/UI size."""
    palette = validate_library({'schema': 1, 'palettes': [palette]})['palettes'][0]
    colors = palette['colors']
    if not colors:
        raise ValueError('色板为空，请先添加颜色')
    width, margin, gap = 1200, 40, 24
    columns = min(4, len(colors))
    cell_width = (width - margin * 2 - gap * (columns - 1)) // columns
    font = QFont(QApplication.font())
    font.setPixelSize(24)
    title_font = QFont(font)
    title_font.setPixelSize(38)
    title_font.setBold(True)
    flags = Qt.TextFlag.TextWrapAnywhere | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    metrics = QFontMetrics(font)
    title_height = QFontMetrics(title_font).boundingRect(QRect(0, 0, width - 80, 2000), flags, palette['name']).height()
    top = margin + title_height + 56
    row_heights = []
    for row in range(math.ceil(len(colors) / columns)):
        values = colors[row * columns:(row + 1) * columns]
        name_height = max(metrics.boundingRect(QRect(0, 0, cell_width, 2000), flags, c['name'] or '未命名颜色').height() for c in values)
        row_heights.append(156 + name_height + 56)
    height = top + sum(row_heights) + gap * (len(row_heights) - 1) + margin + 30
    image = QImage(width, height, QImage.Format.Format_RGB32)
    if image.isNull():
        raise ValueError('无法分配导出图片内存')
    image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    image.fill(QColor('#F4F6F3'))
    image.setText('Title', palette['name'])
    image.setText('Colors', '\n'.join(f'{c["name"]}\t{c["hex"]}' for c in colors))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor('#203C31'))
        painter.setFont(title_font)
        painter.drawText(QRect(margin, margin, width - 80, title_height + 4), flags, palette['name'])
        painter.setFont(font)
        painter.drawText(margin, margin + title_height + 34, f'{len(colors)} COLORS / sRGB')
        y = top
        for row, row_height in enumerate(row_heights):
            for col in range(columns):
                index = row * columns + col
                if index >= len(colors):
                    break
                color = colors[index]
                x = margin + col * (cell_width + gap)
                painter.setPen(QColor('#CDD8CF'))
                painter.setBrush(QColor(color['hex']))
                painter.drawRoundedRect(x, y, cell_width, 140, 12, 12)
                painter.setPen(QColor('#203C31'))
                painter.drawText(QRect(x, y + 156, cell_width, row_height - 196), flags, color['name'] or '未命名颜色')
                painter.drawText(x, y + row_height - 12, color['hex'])
            y += row_height + gap
        painter.drawText(margin, height - 24, 'Creative Toolbox / Color Palette')
    finally:
        painter.end()
    return image


def export_palette_png(palette: dict, path: Path):
    image = palette_image(palette)
    output = QSaveFile(str(path))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if not image.save(output, 'PNG'):
        output.cancelWriting()
        raise OSError('无法编码 PNG 色卡')
    if not output.commit():
        raise OSError(output.errorString())
