"""Local design helpers, independent of the automatic-save controller."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QColorSpace, QFont, QImageReader
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QFontComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .design_core import (
    PaletteStore, contrast_ratio, css_palette, format_color, harmony,
    normalize_hex, note_ms, print_mm, print_pixels, scaled_height,
)


def text(value, name=''):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def action(title, callback):
    widget = QPushButton(title)
    widget.clicked.connect(callback)
    return widget


def number(value, maximum=100000, decimals=2):
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(.01 if decimals else 1, maximum)
    widget.setValue(value)
    return widget


def copy(value):
    QApplication.clipboard().setText(value)


def image_colors(path: str) -> list[str]:
    """Bounded sRGB thumbnail histogram; an approximate palette, not ICC proofing."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 40_000_000:
        raise ValueError('请选择不超过 4000 万像素的图片')
    reader.setScaledSize(size.scaled(QSize(160, 160), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError('无法读取图片：' + reader.errorString())
    if image.colorSpace().isValid():
        image.convertToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    image = image.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    counts, sums = Counter(), {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() < 128:
                continue
            values = (color.red(), color.green(), color.blue())
            key = tuple(v // 32 for v in values)
            counts[key] += 1
            total = sums.setdefault(key, [0, 0, 0])
            for i, v in enumerate(values):
                total[i] += v
    if not counts:
        raise ValueError('图片没有可提取的不透明颜色')
    return ['#' + ''.join(f'{round(v / count):02X}' for v in sums[key])
            for key, count in counts.most_common(6)]


class PalettePage(QWidget):
    def __init__(self, path: Path):
        super().__init__()
        self.store = PaletteStore(path)
        self.library = self.store.load()
        self.edit_index = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(text('把灵感，存成颜色。', 'title'))
        root.addWidget(text('项目色板 · 点击色块复制 · HEX / RGB / HSL · 全部保存在本机', 'muted'))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        library = QWidget()
        layout = QVBoxLayout(library)
        layout.setSpacing(12)
        self.tabs.addTab(library, '我的配色卡')
        row = QHBoxLayout()
        self.palettes = QComboBox()
        row.addWidget(self.palettes, 1)
        row.addWidget(action('新建', self.new_palette))
        row.addWidget(action('重命名', self.rename_palette))
        row.addWidget(action('删除色板', self.remove_palette))
        self.format = QComboBox()
        self.format.addItems(['HEX', 'RGB', 'HSL'])
        row.addWidget(self.format)
        layout.addLayout(row)
        bar = QHBoxLayout()
        for title, callback in [('导入 JSON', self.import_library), ('导出 JSON', self.export_library),
                                ('复制 CSS', self.copy_css), ('图片提色', self.extract_image)]:
            bar.addWidget(action(title, callback))
        bar.addStretch()
        layout.addLayout(bar)
        area = QScrollArea()
        area.setWidgetResizable(True)
        self.cards = QWidget()
        self.grid = QGridLayout(self.cards)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(self.cards)
        layout.addWidget(area, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText('颜色名称，例如：品牌主色')
        self.code = QLineEdit('#355E46')
        self.code.setMaximumWidth(150)
        editor = QHBoxLayout()
        editor.addWidget(self.name, 1)
        editor.addWidget(self.code)
        editor.addWidget(action('选色', self.choose_color))
        self.save_button = action('添加颜色', self.save_color)
        editor.addWidget(self.save_button)
        editor.addWidget(action('取消编辑', self.cancel_edit))
        layout.addLayout(editor)
        row = QHBoxLayout()
        self.harmony_mode = QComboBox()
        self.harmony_mode.addItems(['互补色', '邻近色', '三等分'])
        row.addWidget(text('以输入色号生成新色板'))
        row.addWidget(self.harmony_mode)
        row.addWidget(action('生成配色', self.generate))
        row.addStretch()
        layout.addLayout(row)
        self.status = text(self.store.warning or '点击色块复制；可编辑名称、色号，并导出整个配色库。', 'muted')
        layout.addWidget(self.status)
        self.palettes.currentIndexChanged.connect(self.palette_changed)
        self.format.currentTextChanged.connect(self.render)
        self.build_contrast()
        self.refresh()

    def current(self):
        return self.library['palettes'][max(0, self.palettes.currentIndex())]

    def refresh(self, selected=0):
        self.palettes.blockSignals(True)
        self.palettes.clear()
        self.palettes.addItems([p['name'] for p in self.library['palettes']])
        self.palettes.setCurrentIndex(min(selected, self.palettes.count() - 1))
        self.palettes.blockSignals(False)
        self.cancel_edit()
        self.render()

    def persist(self, candidate, selected=None):
        try:
            self.library = self.store.save(candidate)
        except (ValueError, OSError) as exc:
            self.status.setText(f'未保存：{exc}')
            return False
        self.refresh(self.palettes.currentIndex() if selected is None else selected)
        self.status.setText('已保存到本机。')
        return True

    def palette_changed(self):
        self.cancel_edit()
        self.render()

    def render(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        colors = self.current()['colors']
        if not colors:
            self.grid.addWidget(text('色板还是空的。在下方输入色号，添加第一个颜色。', 'muted'), 0, 0)
        for i, color in enumerate(colors):
            card = QFrame()
            card.setObjectName('card')
            col = QVBoxLayout(card)
            value = format_color(color['hex'], self.format.currentText())
            swatch = action(value, lambda checked=False, v=value: self.copy_color(v))
            ink = '#FFFFFF' if contrast_ratio(color['hex'], '#FFFFFF') >= contrast_ratio(color['hex'], '#000000') else '#000000'
            swatch.setStyleSheet(f'background:{color["hex"]}; color:{ink}; border:none; border-radius:8px;')
            swatch.setMinimumHeight(86)
            swatch.setAccessibleName(f'{color["name"]}，复制 {value}')
            col.addWidget(swatch)
            col.addWidget(text(color['name'] or '未命名颜色'))
            controls = QHBoxLayout()
            controls.addWidget(action('编辑', lambda checked=False, index=i: self.edit_color(index)))
            controls.addWidget(action('移除', lambda checked=False, index=i: self.remove_color(index)))
            col.addLayout(controls)
            self.grid.addWidget(card, i // 3, i % 3)
        for i in range(3):
            self.grid.setColumnStretch(i, 1)

    def copy_color(self, value):
        copy(value)
        self.status.setText(f'已复制 {value}')

    def cancel_edit(self):
        self.edit_index = None
        self.name.clear()
        self.save_button.setText('添加颜色')

    def edit_color(self, index):
        self.edit_index = index
        color = self.current()['colors'][index]
        self.name.setText(color['name'])
        self.code.setText(color['hex'])
        self.save_button.setText('保存修改')

    def save_color(self):
        try:
            color = {'name': self.name.text().strip(), 'hex': normalize_hex(self.code.text())}
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        candidate = deepcopy(self.library)
        colors = candidate['palettes'][self.palettes.currentIndex()]['colors']
        if self.edit_index is None:
            colors.append(color)
        else:
            colors[self.edit_index] = color
        self.persist(candidate)

    def remove_color(self, index):
        candidate = deepcopy(self.library)
        del candidate['palettes'][self.palettes.currentIndex()]['colors'][index]
        self.persist(candidate)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.code.text()), self, '选择颜色')
        if color.isValid():
            self.code.setText(color.name().upper())

    def new_palette(self):
        name, ok = QInputDialog.getText(self, '新建色板', '项目 / 色板名称')
        if ok and name.strip():
            self.add_palette(name.strip(), [])

    def add_palette(self, name, colors):
        candidate = deepcopy(self.library)
        candidate['palettes'].append({'name': name, 'colors': colors})
        return self.persist(candidate, len(candidate['palettes']) - 1)

    def rename_palette(self):
        name, ok = QInputDialog.getText(self, '重命名色板', '名称', text=self.current()['name'])
        if ok and name.strip():
            candidate = deepcopy(self.library)
            candidate['palettes'][self.palettes.currentIndex()]['name'] = name.strip()
            self.persist(candidate)

    def remove_palette(self):
        if len(self.library['palettes']) == 1:
            self.status.setText('至少保留一个色板。可移除其中的颜色。')
            return
        if QMessageBox.question(self, '删除色板', '删除当前色板及其中的颜色？') != QMessageBox.StandardButton.Yes:
            return
        candidate = deepcopy(self.library)
        del candidate['palettes'][self.palettes.currentIndex()]
        self.persist(candidate, 0)

    def import_library(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入并追加色板', '', '配色库 (*.json)')
        if path:
            try:
                incoming = PaletteStore.read(Path(path))
                candidate = deepcopy(self.library)
                candidate['palettes'].extend(incoming['palettes'])
                self.persist(candidate, len(self.library['palettes']))
            except (OSError, ValueError) as exc:
                self.status.setText(f'未导入：{exc}')

    def export_library(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出整个配色库', 'creative-palettes.json', '配色库 (*.json)')
        if path:
            try:
                if Path(path).resolve() == self.store.path.resolve():
                    raise ValueError('请选择独立导出文件，不能覆盖正在使用的配色库')
                PaletteStore.write(Path(path), self.library)
                self.status.setText('配色库已导出。')
            except (OSError, ValueError) as exc:
                self.status.setText(f'未导出：{exc}')

    def copy_css(self):
        copy(css_palette(self.current()))
        self.status.setText('已复制当前色板的 CSS 变量。')

    def generate(self):
        try:
            colors = harmony(self.code.text(), self.harmony_mode.currentText())
            self.add_palette(self.harmony_mode.currentText(), [{'name': f'配色 {i}', 'hex': c} for i, c in enumerate(colors, 1)])
        except ValueError as exc:
            self.status.setText(str(exc))

    def extract_image(self):
        path, _ = QFileDialog.getOpenFileName(self, '从本地图片提取近似主色', '', '图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            try:
                colors = image_colors(path)
                saved = self.add_palette(Path(path).stem[:80], [{'name': f'主色 {i}', 'hex': c} for i, c in enumerate(colors, 1)])
                if saved:
                    self.status.setText('已从缩略图提取近似主色；不保留原图。此结果不用于印刷色彩校样。')
            except (ValueError, OSError) as exc:
                self.status.setText(f'提色失败：{exc}')

    def build_contrast(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.tabs.addTab(page, '文字对比度')
        layout.addWidget(text('检查文字与背景的可读性', 'section'))
        row = QHBoxLayout()
        self.foreground, self.background = QLineEdit('#355E46'), QLineEdit('#FFFFFF')
        row.addWidget(text('文字 HEX'))
        row.addWidget(self.foreground)
        row.addWidget(text('背景 HEX'))
        row.addWidget(self.background)
        layout.addLayout(row)
        self.contrast_preview = text('Aa  创作，让灵感被看见。\nDesign with clarity.')
        self.contrast_preview.setMinimumHeight(160)
        layout.addWidget(self.contrast_preview)
        self.contrast_result = text('')
        layout.addWidget(self.contrast_result)
        layout.addWidget(text('按 WCAG 2.2 的不透明 sRGB 颜色计算。大号文字指至少 18 pt，或至少 14 pt 的粗体；这里只检查颜色对比，不代表整体无障碍合规。', 'muted'))
        layout.addStretch()
        self.foreground.textChanged.connect(self.update_contrast)
        self.background.textChanged.connect(self.update_contrast)
        self.update_contrast()

    def update_contrast(self):
        try:
            fg, bg = normalize_hex(self.foreground.text()), normalize_hex(self.background.text())
            ratio = contrast_ratio(fg, bg)
            self.contrast_preview.setStyleSheet(f'background:{bg}; color:{fg}; padding:24px; font-size:26px; border-radius:12px;')
            results = [f'{title}：{"通过" if ratio >= threshold else "未通过"}' for title, threshold in
                       [('AA 普通文字', 4.5), ('AA 大号文字', 3), ('AAA 普通文字', 7), ('AAA 大号文字', 4.5)]]
            self.contrast_result.setText(f'对比度 {ratio:.2f} : 1\n' + '\n'.join(results))
        except ValueError as exc:
            self.contrast_result.setText(str(exc))


class CalculatorPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(text('少切一个页面，多一点专注。', 'title'))
        root.addWidget(text('印刷尺寸、画面比例、音乐延迟，用同一组本地工具完成。', 'muted'))
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        page = QWidget()
        layout = QVBoxLayout(page)
        tabs.addTab(page, '印刷与像素')
        layout.addWidget(text('物理尺寸 ↔ 像素', 'section'))
        self.print_direction = QComboBox()
        self.print_direction.addItems(['毫米 → 像素', '像素 → 毫米'])
        self.print_width, self.print_height, self.ppi = number(210), number(297), number(300, 9600)
        grid = QGridLayout()
        for i, (title, field) in enumerate([('转换方向', self.print_direction), ('宽', self.print_width), ('高', self.print_height), ('PPI（每英寸像素）', self.ppi)]):
            grid.addWidget(text(title), i, 0)
            grid.addWidget(field, i, 1)
        layout.addLayout(grid)
        self.print_result = text('', 'metric')
        layout.addWidget(self.print_result)
        layout.addWidget(action('复制结果', lambda: copy(self.print_result.text())))
        layout.addWidget(text('像素取最接近的整数。PPI 描述图像像素密度；打印机 DPI 不是同一个量。换算不会修改图片，也不包含出血。', 'muted'))
        layout.addStretch()
        for field in (self.print_width, self.print_height, self.ppi):
            field.valueChanged.connect(self.update_print)
        self.print_direction.currentIndexChanged.connect(self.update_print)
        self.update_print()
        page = QWidget()
        layout = QVBoxLayout(page)
        tabs.addTab(page, '等比缩放')
        layout.addWidget(text('输入原始尺寸，以新宽度计算高度', 'section'))
        self.ratio_width, self.ratio_height, self.target_width = number(1920, decimals=0), number(1080, decimals=0), number(1280, decimals=0)
        grid = QGridLayout()
        for i, (title, field) in enumerate([('原始宽度 px', self.ratio_width), ('原始高度 px', self.ratio_height), ('目标宽度 px', self.target_width)]):
            grid.addWidget(text(title), i, 0)
            grid.addWidget(field, i, 1)
            field.valueChanged.connect(self.update_ratio)
        layout.addLayout(grid)
        self.ratio_result = text('', 'metric')
        layout.addWidget(self.ratio_result)
        layout.addWidget(action('复制尺寸', lambda: copy(self.ratio_result.text())))
        layout.addWidget(text('结果四舍五入至整数像素。', 'muted'))
        layout.addStretch()
        self.update_ratio()
        page = QWidget()
        layout = QVBoxLayout(page)
        tabs.addTab(page, 'BPM 与延迟')
        layout.addWidget(text('为 Delay / Reverb 计算节拍时长', 'section'))
        row = QHBoxLayout()
        row.addWidget(text('BPM（四分音符 / 分钟）'))
        self.bpm = number(120, 1000)
        row.addWidget(self.bpm)
        self.note_modifier = QComboBox()
        self.note_modifier.addItems(['普通', '附点', '三连音'])
        row.addWidget(self.note_modifier)
        layout.addLayout(row)
        self.tempo_result = text('')
        self.tempo_result.setStyleSheet('font-size:22px; padding:24px; background:white; border-radius:12px;')
        layout.addWidget(self.tempo_result)
        layout.addWidget(action('复制时值表', lambda: copy(self.tempo_result.text())))
        layout.addWidget(text('仅作数值计算；不监听麦克风、MIDI 或宿主播放状态。', 'muted'))
        layout.addStretch()
        self.bpm.valueChanged.connect(self.update_tempo)
        self.note_modifier.currentIndexChanged.connect(self.update_tempo)
        self.update_tempo()

    def update_print(self):
        width, height, ppi = self.print_width.value(), self.print_height.value(), self.ppi.value()
        if self.print_direction.currentIndex() == 0:
            result = f'{print_pixels(width, ppi)} × {print_pixels(height, ppi)} px'
        else:
            result = f'{print_mm(width, ppi):.2f} × {print_mm(height, ppi):.2f} mm'
        self.print_result.setText(result)

    def update_ratio(self):
        target = self.target_width.value()
        height = scaled_height(self.ratio_width.value(), self.ratio_height.value(), target)
        self.ratio_result.setText(f'{target:.0f} × {height} px')

    def update_tempo(self):
        self.tempo_result.setText('\n'.join(f'1/{n} 音符     {note_ms(self.bpm.value(), n, self.note_modifier.currentText()):.2f} ms' for n in (1, 2, 4, 8, 16, 32)))


class FontPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(text('让文字，找到合适的声音。', 'title'))
        root.addWidget(text('对照本机已安装字体；输入同一段文案，比较两种排版效果。', 'muted'))
        self.sample = QPlainTextEdit('创作，让灵感被看见。\nThe quick brown fox jumps over the lazy dog.\n0123456789  Aa Bb Cc')
        self.sample.setMaximumHeight(110)
        root.addWidget(self.sample)
        controls = QHBoxLayout()
        controls.addWidget(text('字号 pt'))
        self.size = QSpinBox()
        self.size.setRange(8, 96)
        self.size.setValue(28)
        controls.addWidget(self.size)
        self.bold = QCheckBox('粗体')
        controls.addWidget(self.bold)
        controls.addStretch()
        root.addLayout(controls)
        columns = QHBoxLayout()
        self.fonts, self.previews = [], []
        for i in range(2):
            col = QVBoxLayout()
            family = QFontComboBox()
            self.fonts.append(family)
            col.addWidget(family)
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            self.previews.append(preview)
            col.addWidget(preview, 1)
            col.addWidget(action('复制字体名称', lambda checked=False, widget=family: self.copy_family(widget)))
            family.currentFontChanged.connect(self.update_preview)
            columns.addLayout(col, 1)
        root.addLayout(columns, 1)
        self.status = text('缺少字形时系统可能回退到其他字体。预览不代表字体拥有商业使用授权。', 'muted')
        root.addWidget(self.status)
        self.sample.textChanged.connect(self.update_preview)
        self.size.valueChanged.connect(self.update_preview)
        self.bold.toggled.connect(self.update_preview)
        self.update_preview()

    def copy_family(self, field):
        copy(field.currentFont().family())
        self.status.setText('已复制字体名称：' + field.currentFont().family())

    def update_preview(self):
        for field, preview in zip(self.fonts, self.previews):
            font = QFont(field.currentFont())
            font.setPointSize(self.size.value())
            font.setBold(self.bold.isChecked())
            preview.setFont(font)
            preview.setStyleSheet(f"font-size:{self.size.value()}pt; font-weight:{700 if self.bold.isChecked() else 400};")
            preview.setPlainText(self.sample.toPlainText())
