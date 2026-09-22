"""Cold-white / cobalt desktop language, with a lightweight painted glass shell.

The material is an in-app approximation; it does not capture or blur the desktop.
Content surfaces stay opaque. No timers or animation are needed to paint it.
"""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import QWidget

TOKENS = {
    "canvas": "#F3F5F9", "surface": "#FFFFFF", "ink": "#202735",
    "muted": "#5C677A", "accent": "#245CDB", "accent_hover": "#194AB8",
    "accent_pressed": "#173D91", "tint": "#EAF0FD", "line": "#DDE3EE",
    "hover": "#F0F3FA", "disabled": "#798394", "danger": "#A33A35",
}
RESOURCES = Path(__file__).parent / "resources"


def icon(name):
    return QIcon(str(RESOURCES / f"{name}.png"))


def application_icon():
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        result.addFile(str(RESOURCES / f"toolbox-{size}.png"))
    return result


_QSS = """
QWidget { color: @ink; font-size: 13px; }
QMainWindow, QDialog, QWidget#floatingSurface { background: @canvas; }
QLabel { background: transparent; }
QWidget#sidebar QLabel { color: @muted; }
QWidget#sidebar QLabel#brand { color: @ink; font-size: 20px; font-weight: 700; }
QWidget#sidebar QPushButton { text-align: left; padding: 12px 14px; background: transparent;
    color: @muted; border: 1px solid transparent; border-radius: 12px; font-size: 14px; }
QWidget#sidebar QPushButton:hover { background: @surface; color: @ink; }
QWidget#sidebar QPushButton:checked { color: @accent; background: @tint; border-color: #D1DDF9; }
QWidget#sidebar QPushButton:focus { border: 2px solid @accent; padding: 11px 13px; }
QLabel#title { font-size: 26px; font-weight: 700; color: @ink; }
QLabel#eyebrow { color: @muted; font-size: 11px; font-weight: 600; }
QLabel#muted { color: @muted; }
QLabel#section { font-size: 16px; font-weight: 600; }
QFrame#card { background: @surface; border: 1px solid @line; border-radius: 18px; }
QFrame#toolRow { background: @surface; border: 1px solid @line; border-radius: 16px; }
QFrame#hero { background: @tint; border: 1px solid #D7E2FC; border-radius: 20px; }
QLabel#heroTitle { font-size: 23px; font-weight: 700; color: @ink; }
QLabel#metric { font-size: 30px; font-weight: 600; color: @ink; }
QLabel#badge { background: @tint; color: @accent; padding: 6px 12px; border-radius: 10px; }
QPushButton { background: @surface; color: @ink; border: 1px solid @line;
    border-radius: 10px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: @hover; border-color: #A7B7D6; }
QPushButton:pressed { background: #DEE7F8; }
QPushButton:checked { background: @tint; color: @accent; border-color: #9EB6EC; }
QPushButton:focus { border: 2px solid @accent; padding: 8px 13px; }
QPushButton#secondary { background: transparent; border-color: transparent; font-weight: 400; }
QPushButton#secondary:hover, QPushButton#secondary:checked { background: @tint; color: @accent; }
QPushButton#secondary:focus { border-color: @accent; }
QPushButton#primary { background: @accent; color: white; border: 1px solid @accent; }
QPushButton#primary:hover { background: @accent_hover; border-color: @accent_hover; }
QPushButton#primary:pressed { background: @accent_pressed; }
QPushButton#primary:focus { border: 2px solid #102A68; }
QPushButton#danger { color: @danger; }
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#secondary:disabled {
    color: @disabled; background: #EDF0F5; border: 1px solid @line; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
    background: @surface; border: 1px solid #B9C4D6; border-radius: 9px; padding: 8px;
    min-height: 19px; selection-background-color: @accent; selection-color: white; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 2px solid @accent; padding: 7px; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled {
    background: #EDF0F5; color: @disabled; border-color: @line; }
QComboBox QAbstractItemView { background: @surface; selection-background-color: @tint;
    selection-color: @ink; padding: 4px; border: 1px solid @line; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox:focus { color: @accent; }
QTableWidget, QListView, QTextBrowser { background: @surface; border: 1px solid @line;
    border-radius: 12px; gridline-color: @line; selection-background-color: @tint; selection-color: @ink; }
QListView { padding: 5px; }
QListWidget::item { padding: 10px 8px; border-radius: 7px; }
QListWidget::item:hover { background: @hover; }
QListWidget::item:selected { background: @tint; color: @accent; }
QListView:focus, QTextBrowser:focus, QTableWidget:focus { border-color: @accent; }
QHeaderView::section { background: #F5F7FB; color: @muted; border: none; padding: 12px 8px; font-weight: 600; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #EEF1F6; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 3px 0; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 0 3px; }
QScrollBar::handle:vertical { background: #BBC6D8; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:horizontal { background: #BBC6D8; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenu { background: @surface; border: 1px solid @line; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; }
QMenu::item:selected { background: @tint; color: @accent; }
QMenu::item:disabled { color: @disabled; }
QTabWidget::pane { border: 1px solid @line; background: @canvas; border-radius: 12px; top: -1px; }
QTabBar::tab { padding: 10px 18px; margin: 0 4px 7px 0; border: 1px solid transparent;
    background: transparent; color: @muted; border-radius: 10px; }
QTabBar::tab:hover { background: @hover; }
QTabBar::tab:selected { background: @surface; color: @accent; border-color: #B9CBF1; }
QSplitter::handle { background: transparent; }

QComboBox { padding-right: 30px; }
QComboBox:focus { padding-right: 29px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
    width: 26px; border: none; }
QComboBox::down-arrow { image: url("RESOURCE/caret-down.png"); width: 12px; height: 12px; }
QSpinBox, QDoubleSpinBox { padding-right: 26px; }
QSpinBox:focus, QDoubleSpinBox:focus { padding-right: 25px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
    width: 24px; border: none; background: transparent; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
    width: 24px; border: none; background: transparent; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("RESOURCE/caret-up.png"); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("RESOURCE/caret-down.png"); width: 10px; height: 10px; }
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled,
QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::down-arrow:disabled { width: 7px; height: 7px; }
QCheckBox::indicator { border: 1px solid #8896AE; border-radius: 5px; background: @surface; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; image: url("RESOURCE/check.png"); }
QCheckBox::indicator:disabled { background: #DEE3EC; border-color: @line; }
QCheckBox::indicator:checked:disabled { background: @disabled; }
QCheckBox::indicator:focus { border: 2px solid @accent; width: 15px; height: 15px; }
QToolTip { background: @ink; color: white; padding: 7px; border: none; }
"""
STYLE = _QSS.replace("RESOURCE", RESOURCES.as_posix())
for _name, _value in sorted(TOKENS.items(), key=lambda item: -len(item[0])):
    STYLE = STYLE.replace('@' + _name, _value)


class WorkspaceCanvas(QWidget):
    def __init__(self, reduced=False):
        super().__init__()
        self.reduced = reduced

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(TOKENS['canvas']))
        if not self.reduced:
            glow = QRadialGradient(80, 0, max(500, self.height()))
            glow.setColorAt(0, QColor('#DFE8FB'))
            glow.setColorAt(1, QColor(TOKENS['canvas']))
            painter.fillRect(self.rect(), glow)
        painter.end()


class GlassPanel(QWidget):
    def __init__(self, reduced=False, radius=22):
        super().__init__()
        self.reduced, self.radius = reduced, radius

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.reduced:
            painter.setBrush(QColor(TOKENS['surface']))
            painter.setPen(QColor(TOKENS['line']))
        else:
            fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
            fill.setColorAt(0, QColor(255, 255, 255, 238))
            fill.setColorAt(.5, QColor(255, 255, 255, 168))
            fill.setColorAt(1, QColor(241, 246, 255, 215))
            painter.setBrush(fill)
            painter.setPen(QColor(255, 255, 255, 245))
        painter.drawRoundedRect(rect, self.radius, self.radius)
        painter.end()