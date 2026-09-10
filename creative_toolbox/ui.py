from __future__ import annotations

import os
import plistlib
import sys
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QStackedWidget, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .controller import Controller, Event
from .core import Profile, resolve_shortcut
from .storage import Settings, Store


STYLE = """
QWidget { color: #233a34; font-size: 13px; }
QMainWindow, QDialog { background: #f4f6f3; }
QWidget#sidebar { background: #1c302b; }
QWidget#sidebar QLabel { color: #a9bcb4; background: transparent; }
QWidget#sidebar QLabel#brand { color: #f4f7f3; font-size: 21px; font-weight: 700; }
QWidget#sidebar QPushButton { border: none; text-align: left; padding: 13px 18px;
    background: transparent; color: #b7c9bf; border-radius: 8px; font-size: 14px; }
QWidget#sidebar QPushButton:checked { color: #fff; background: #365147; }
QWidget#sidebar QPushButton:hover { background: #2a4439; }
QLabel#title { font-size: 29px; font-weight: 700; color: #203c31; }
QLabel#eyebrow { color: #628170; font-size: 11px; font-weight: 600; }
QLabel#muted { color: #718077; }
QLabel#section { font-size: 16px; font-weight: 700; }
QFrame#card { background: #ffffff; border: 1px solid #e0e7df; border-radius: 14px; }
QFrame#hero { background: #e6eee4; border: 1px solid #d7e3d4; border-radius: 16px; }
QLabel#heroTitle { font-size: 24px; font-weight: 700; color: #294f3d; }
QLabel#metric { font-size: 30px; font-weight: 700; color: #2a4b3b; }
QLabel#badge { background: #edf1e9; color: #497055; padding: 6px 12px; border-radius: 10px; }
QPushButton { background: #ffffff; color: #2c4a3b; border: 1px solid #d7e0d5;
    border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #edf2e9; border-color: #aabfa7; }
QPushButton:pressed { background: #dfe9d9; }
QPushButton:disabled { color: #9ca79e; background: #f1f3ef; border-color: #e4e9e1; }
QPushButton#primary { background: #355e46; color: white; border: none; }
QPushButton#primary:hover { background: #447755; }
QPushButton#danger { color: #9a5442; }
QLineEdit, QSpinBox, QComboBox { background: white; border: 1px solid #d5dfd1;
    border-radius: 6px; padding: 8px; min-height: 19px; selection-background-color: #426e50; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #558963; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e2eddf;
    selection-color: #233a34; padding: 4px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QTableWidget { background: white; border: 1px solid #e0e7df; border-radius: 10px;
    gridline-color: #edf0ea; selection-background-color: #e7efdf; selection-color: #233a34; }
QHeaderView::section { background: #f0f4ed; color: #667b69; border: none;
    padding: 12px 8px; font-weight: 600; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #eef1eb; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: #c7d3c3; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: #fff; border: 1px solid #d5dfd1; padding: 6px; }
QMenu::item { padding: 8px 22px; }
QMenu::item:selected { background: #e7efdf; }
QToolTip { background: #203c31; color: white; padding: 6px; border: none; }
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    item = QLabel(text)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text: str, callback=None, primary=False) -> QPushButton:
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    if callback:
        item.clicked.connect(callback)
    return item


def panel(name="card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    return frame, layout


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#355e46"))
    painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
    painter.setBrush(QColor("#e9edc8"))
    painter.drawRoundedRect(15, 15, 14, 34, 5, 5)
    painter.drawRoundedRect(35, 15, 14, 14, 5, 5)
    painter.setBrush(QColor("#b3cf9c"))
    painter.drawRoundedRect(35, 35, 14, 14, 5, 5)
    painter.end()
    return QIcon(pixmap)


def style_combo(platform: str, inherit=False) -> QComboBox:
    box = QComboBox()
    if inherit:
        box.addItem("继承全局设置", "inherit")
    box.addItem("自动跟随系统", "auto")
    box.addItem("Windows · Ctrl+S", "windows")
    box.addItem("macOS · ⌘+S" + ("（此系统不可用）" if platform != "darwin" else ""), "macos")
    if platform != "darwin":
        box.model().item(box.findData("macos")).setEnabled(False)
    box.addItem("自定义组合键", "custom")
    return box


class ShortcutInput(QLineEdit):
    def __init__(self, text: str, platform: str):
        super().__init__(text)
        self.platform, self.recording = platform, False
        self.setPlaceholderText("例如 Ctrl+Shift+S 或 Cmd+S")

    def record(self):
        self.recording = True
        self.setPlaceholderText("按下组合键；Esc 取消录制")
        self.setFocus()
        self.selectAll()

    def focusOutEvent(self, event):
        self.recording = False
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self.recording:
            return super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            self.recording = False
            return
        mods = event.modifiers()
        values = []
        # Qt swaps Control/Meta semantics on macOS to keep standard shortcuts portable.
        if mods & Qt.KeyboardModifier.ControlModifier:
            values.append("Cmd" if self.platform == "darwin" else "Ctrl")
        if mods & Qt.KeyboardModifier.MetaModifier:
            values.append("Ctrl" if self.platform == "darwin" else "Cmd")
        if mods & Qt.KeyboardModifier.AltModifier:
            values.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            values.append("Shift")
        key = event.key()
        main = chr(key) if 48 <= key <= 90 else ""
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            main = f"F{key - Qt.Key.Key_F1 + 1}"
        if main and values:
            self.setText("+".join((*values, main)))
            self.recording = False
        event.accept()


class ProfileDialog(QDialog):
    def __init__(self, platform: str, existing: Profile | None = None, parent=None):
        super().__init__(parent)
        self.platform, self.existing, self.result_profile = platform, existing, None
        self.setWindowTitle("应用保护规则")
        self.setMinimumWidth(530)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        layout.addWidget(label("为你的应用设置规则", "section"))
        layout.addWidget(label("通过程序身份匹配，不依赖窗口标题或软件品牌。", "muted", True))
        form = QFormLayout()
        form.setSpacing(12)
        self.name = QLineEdit(existing.name if existing else "")
        self.identity = QLineEdit(existing.identity if existing else "")
        self.identity.setPlaceholderText("例如 C:\\Apps\\Editor.exe" if platform == "win32" else "例如 com.vendor.editor")
        identity_row = QHBoxLayout()
        identity_row.addWidget(self.identity, 1)
        identity_row.addWidget(button("选择程序", self.browse))
        form.addRow("应用名称", self.name)
        form.addRow("程序路径 / 名称" if platform == "win32" else "应用 Bundle ID", identity_row)
        self.enabled = QCheckBox("启用此应用的规则")
        self.enabled.setChecked(existing.enabled if existing else True)
        form.addRow("保护状态", self.enabled)
        self.interval = QSpinBox()
        self.interval.setRange(10, 7200)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(existing.interval if existing else 120)
        self.idle = QSpinBox()
        self.idle.setRange(2, 600)
        self.idle.setSuffix(" 秒")
        self.idle.setValue(existing.idle if existing else 8)
        form.addRow("请求最短间隔", self.interval)
        form.addRow("输入空闲时间", self.idle)
        self.style = style_combo(platform, True)
        self.style.setCurrentIndex(self.style.findData(existing.style if existing else "inherit"))
        self.custom = ShortcutInput(existing.custom if existing else ("Cmd+S" if platform == "darwin" else "Ctrl+S"), platform)
        self.record = button("录制", self.custom.record)
        row = QHBoxLayout()
        row.addWidget(self.custom, 1)
        row.addWidget(self.record)
        form.addRow("保存快捷键", self.style)
        form.addRow("自定义组合键", row)
        self.style.currentIndexChanged.connect(self.update_custom)
        self.update_custom()
        self.reminder = QCheckBox("仅提醒，不自动发送按键")
        self.reminder.setChecked(existing.reminder_only if existing else False)
        form.addRow("应用模式", self.reminder)
        layout.addLayout(form)
        layout.addWidget(label("录音、演奏、播放或渲染可能发生在输入空闲时。\n当前版本无法读取这些内部状态，建议相关软件先使用「仅提醒」。", "muted", True))
        self.error = label("", "muted", True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox()
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        save = buttons.addButton("保存规则", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.accepted.connect(self.accept_profile)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_custom(self):
        active = self.style.currentData() == "custom"
        self.custom.setEnabled(active)
        self.record.setEnabled(active)

    def browse(self):
        if self.platform == "darwin":
            path = QFileDialog.getExistingDirectory(self, "选择 .app 应用", "/Applications")
            if path:
                try:
                    with (Path(path) / "Contents" / "Info.plist").open("rb") as stream:
                        info = plistlib.load(stream)
                    self.identity.setText(info["CFBundleIdentifier"])
                    self.name.setText(info.get("CFBundleDisplayName", Path(path).stem))
                except (OSError, KeyError, ValueError):
                    self.error.setText("请选择有效的 .app，或从前台应用自动添加。")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择应用程序", "", "应用程序 (*.exe)")
            if path:
                self.identity.setText(str(Path(path)))
                if not self.name.text():
                    self.name.setText(Path(path).stem)

    def accept_profile(self):
        try:
            self.result_profile = Profile(
                self.existing.id if self.existing else uuid.uuid4().hex,
                self.name.text().strip(), self.identity.text().strip(), self.platform,
                self.enabled.isChecked(), self.interval.value(), self.idle.value(),
                self.style.currentData(), self.custom.text().strip(), self.reminder.isChecked())
            self.result_profile.validate()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, backend, store: Store, settings: Settings, start_timer=True):
        super().__init__()
        self.store, self.settings, self.backend = store, settings, backend
        self.controller = Controller(backend, settings, self.on_event)
        self.events: list[tuple[str, Event]] = []
        self.quitting = False
        self.capture_seconds = 0
        self.setWindowTitle("创作工具箱 · Creative Toolbox")
        self.setWindowIcon(app_icon())
        self.resize(1180, 800)
        self.setMinimumSize(1020, 720)
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(204)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 30, 20, 22)
        side.setSpacing(8)
        logo = label("")
        logo.setPixmap(app_icon().pixmap(42, 42))
        side.addWidget(logo)
        side.addSpacing(10)
        side.addWidget(label("创作工具箱", "brand"))
        side.addWidget(label("CREATIVE TOOLBOX"))
        side.addSpacing(35)
        side.addWidget(label("工作空间"))
        self.nav = []
        for i, name in enumerate(("01   智能保存", "02   应用规则", "03   活动记录", "04   偏好设置")):
            nav = button(name, lambda checked=False, index=i: self.switch_page(index))
            nav.setCheckable(True)
            side.addWidget(nav)
            self.nav.append(nav)
        side.addStretch()
        side.addWidget(label("留住每一次灵感。"))
        side.addWidget(label("本地运行  /  v0.1.0"))
        root.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(32, 25, 32, 16)
        content.setSpacing(18)
        top = QHBoxLayout()
        top.addWidget(label("WORKSPACE  /  创作守护", "eyebrow"))
        top.addStretch()
        top.addWidget(label(backend.label, "muted"))
        self.mode_badge = label("●  观察模式", "badge")
        top.addWidget(self.mode_badge)
        content.addLayout(top)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        root.addLayout(content, 1)
        self.build_dashboard()
        self.build_profiles()
        self.build_events()
        self.build_preferences()
        bottom = QHBoxLayout()
        self.footer = label("仅记录活动时间与状态，不记录输入内容。", "muted")
        bottom.addWidget(self.footer)
        bottom.addStretch()
        content.addLayout(bottom)
        self.make_tray()
        self.switch_page(0)
        self.refresh_profiles()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)
        if start_timer:
            self.timer.start()
        self.tick()
        self.on_event(Event("system", "工具箱", "已启动观察模式；自动保存需本次手动开启"))
        if store.warning:
            self.on_event(Event("error", "配置", store.warning))

    def page(self, title: str, subtitle: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(subtitle, "muted", True))
        self.pages.addWidget(page)
        return layout

    def build_dashboard(self):
        layout = self.page("安心创作，适时保存。", "为设计、剪辑、三维和音乐软件，建立属于你的保存节奏。")
        hero, hero_layout = panel("hero")
        header = QHBoxLayout()
        header.addWidget(label("SMART SAVE", "eyebrow"))
        header.addStretch()
        self.profile_count = label("0 个应用已启用", "muted")
        header.addWidget(self.profile_count)
        hero_layout.addLayout(header)
        self.hero_title = label("先观察，再开启保护", "heroTitle")
        hero_layout.addWidget(self.hero_title)
        self.hero_description = label("观察模式只显示何时满足规则，不会向其他应用发送按键。", "muted", True)
        hero_layout.addWidget(self.hero_description)
        row = QHBoxLayout()
        self.arm_button = button("开启自动保存", self.toggle_automatic, True)
        self.pause_button = button("暂停", self.toggle_pause)
        row.addWidget(self.arm_button)
        row.addWidget(self.pause_button)
        row.addStretch()
        row.addWidget(button("重新开始", self.restart))
        hero_layout.addLayout(row)
        layout.addWidget(hero)
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.idle_metric, self.request_metric, self.observe_metric = label("0s", "metric"), label("0", "metric"), label("0", "metric")
        for heading, value, hint in (("输入空闲", self.idle_metric, "鼠标 / 键盘活动间隙"),
                                     ("保存请求", self.request_metric, "本次运行 · 非成功次数"),
                                     ("观察记录", self.observe_metric, "本次运行 · 未发送按键")):
            box, col = panel()
            col.setSpacing(5)
            col.addWidget(label(heading, "muted"))
            col.addWidget(value)
            col.addWidget(label(hint, "muted"))
            metrics.addWidget(box, 1)
        layout.addLayout(metrics)
        live, live_layout = panel()
        row = QHBoxLayout()
        row.addWidget(label("此刻的工作状态", "section"))
        row.addStretch()
        row.addWidget(button("管理应用 →", lambda: self.switch_page(1)))
        live_layout.addLayout(row)
        self.live_app = label("等待前台应用", "section")
        self.live_title = label("", "muted")
        self.live_title.setMaximumWidth(760)
        self.live_state = label("", "", True)
        self.live_shortcut = label("", "muted", True)
        live_layout.addWidget(self.live_app)
        live_layout.addWidget(self.live_title)
        live_layout.addWidget(self.live_state)
        live_layout.addWidget(self.live_shortcut)
        layout.addWidget(live)
        layout.addWidget(label("初版能力：识别前台应用与输入状态。录音、渲染、未命名文档和保存结果仍需人工确认。", "muted", True))
        layout.addStretch()

    def build_profiles(self):
        layout = self.page("每个应用，各有节奏。", "预设仅作起点，默认未启用。推荐从实际运行的应用添加，准确识别版本。")
        bar = QHBoxLayout()
        bar.addWidget(button("＋ 添加应用", self.add_profile, True))
        self.capture_button = button("从前台应用添加", self.begin_capture)
        bar.addWidget(self.capture_button)
        bar.addStretch()
        bar.addWidget(button("编辑", self.edit_profile))
        bar.addWidget(button("启用 / 停用", self.flip_profile))
        delete = button("移除", self.remove_profile)
        delete.setObjectName("danger")
        bar.addWidget(delete)
        layout.addLayout(bar)
        self.profile_table = QTableWidget(0, 5)
        self.profile_table.setHorizontalHeaderLabels(["应用", "保护", "保存快捷键", "间隔 / 空闲", "模式"])
        self.profile_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.profile_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.profile_table.setColumnWidth(0, 200)
        self.profile_table.verticalHeader().hide()
        self.profile_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.profile_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.profile_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.profile_table.setShowGrid(False)
        self.profile_table.cellDoubleClicked.connect(lambda *_: self.edit_profile())
        layout.addWidget(self.profile_table, 1)
        note, col = panel()
        col.addWidget(label("先确认，再交给工具箱", "section"))
        col.addWidget(label("请先手动保存目标文件，并确认应用内的保存快捷键。自动模式只检查可观测的通用状态；音乐和剪辑预设采用「仅提醒」。双击应用可修改。", "muted", True))
        layout.addWidget(note)

    def build_events(self):
        layout = self.page("每一步，都有记录。", "区分观察、提醒和保存请求。发送快捷键不代表文件已写入磁盘。")
        row = QHBoxLayout()
        row.addWidget(label("本次运行", "section"))
        row.addStretch()
        row.addWidget(button("打开日志文件夹", self.open_data))
        row.addWidget(button("清空本次视图", self.clear_event_view))
        layout.addLayout(row)
        self.event_table = QTableWidget(0, 4)
        self.event_table.setHorizontalHeaderLabels(["时间", "类型", "应用", "说明"])
        self.event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.event_table.setColumnWidth(0, 90)
        self.event_table.setColumnWidth(1, 95)
        self.event_table.setColumnWidth(2, 130)
        self.event_table.verticalHeader().hide()
        self.event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.event_table.setWordWrap(True)
        self.event_table.setShowGrid(False)
        layout.addWidget(self.event_table, 1)
        layout.addWidget(label("历史日志保留在本地；不包含文档标题、文件内容或键盘输入文本。", "muted", True))

    def build_preferences(self):
        layout = self.page("让工具适应你的习惯。", "设置作为应用的默认值，每个应用都可以独立覆盖。")
        card, col = panel()
        col.addWidget(label("保存快捷键", "section"))
        form = QFormLayout()
        form.setSpacing(14)
        self.global_style = style_combo(self.backend.platform)
        self.global_style.setCurrentIndex(self.global_style.findData(self.settings.style))
        self.global_custom = ShortcutInput(self.settings.custom, self.backend.platform)
        row = QHBoxLayout()
        row.addWidget(self.global_custom, 1)
        self.global_record = button("录制", self.global_custom.record)
        row.addWidget(self.global_record)
        form.addRow("快捷键方案", self.global_style)
        form.addRow("自定义组合键", row)
        col.addLayout(form)
        self.global_style.currentIndexChanged.connect(self.update_global_custom)
        self.update_global_custom()
        col.addWidget(label("自动：Windows 使用 Ctrl+S，macOS 使用 ⌘+S。\n切换只改变发送的组合键，不会修改创作软件本身的快捷键。", "muted", True))
        col.addWidget(button("保存偏好设置", self.save_preferences, True), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)
        local, local_layout = panel()
        local_layout.addWidget(label("本地运行，随时可控", "section"))
        local_layout.addWidget(label("每次启动从观察模式开始。关闭窗口后可继续在系统托盘运行；在托盘菜单中选择「退出」即可停止。\n此初版尚未实现版本备份、云同步或软件内部工作状态适配。", "muted", True))
        local_layout.addWidget(button("打开配置与日志文件夹", self.open_data), 0, Qt.AlignmentFlag.AlignLeft)
        if self.backend.platform == "darwin":
            local_layout.addWidget(button("打开 macOS 辅助功能设置", lambda: QDesktopServices.openUrl(QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"))))
            local_layout.addWidget(button("打开 macOS 输入监控设置", lambda: QDesktopServices.openUrl(QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"))))
        layout.addWidget(local)
        layout.addStretch()

    def update_global_custom(self):
        active = self.global_style.currentData() == "custom"
        self.global_custom.setEnabled(active)
        self.global_record.setEnabled(active)

    def make_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("创作工具箱 · 观察模式")
        menu = QMenu(self)
        menu.addAction("打开工具箱", self.show_main)
        self.tray_pause = menu.addAction("暂停保护", self.toggle_pause)
        menu.addAction("切回观察模式", self.disarm)
        menu.addSeparator()
        menu.addAction("退出", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_main() if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def show_main(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if not self.quitting and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()
            if not self.quitting:
                self.quit_app()

    def quit_app(self):
        self.quitting = True
        self.timer.stop()
        self.tray.hide()
        QApplication.instance().quit()

    def disarm(self):
        self.controller.automatic = False
        self.controller.restart()
        self.update_mode()

    def toggle_automatic(self):
        if self.controller.automatic:
            self.disarm()
            self.on_event(Event("system", "工具箱", "已切回观察模式"))
            return
        if not any(p.enabled for p in self.settings.profiles):
            QMessageBox.information(self, "先添加应用", "请先在应用规则中启用至少一个应用。")
            self.switch_page(1)
            return
        result = QMessageBox.question(self, "开启本次自动保存", "工具箱将向已启用的前台应用发送保存快捷键。\n\n请先手动保存文件，并确认保存快捷键正确。当前版本不能判断录音、渲染、全部编辑状态或保存结果；这些场景请使用「仅提醒」或暂停。\n\n开启后仍可随时暂停，每次重新启动会回到观察模式。",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if result != QMessageBox.StandardButton.Yes:
            return
        self.controller.automatic = True
        self.controller.paused = False
        self.controller.restart()
        self.update_mode()
        self.on_event(Event("system", "工具箱", "已开启本次自动保存；所有间隔重新计时"))

    def toggle_pause(self):
        self.controller.paused = not self.controller.paused
        self.controller.restart()
        self.update_mode()
        self.on_event(Event("system", "工具箱", "保护已暂停" if self.controller.paused else "已恢复，间隔重新计时"))

    def restart(self):
        self.controller.restart()
        self.on_event(Event("system", "工具箱", "已清除本次失败状态并重新计时"))

    def update_mode(self):
        auto, paused = self.controller.automatic, self.controller.paused
        self.mode_badge.setText("●  已暂停" if paused else ("●  自动模式" if auto else "●  观察模式"))
        self.hero_title.setText("给创作留一点呼吸" if auto else "先观察，再开启保护")
        self.hero_description.setText("仅在已启用应用中等待输入停顿；需要时可暂停或切回观察。" if auto else "观察模式只显示何时满足规则，不会向其他应用发送按键。")
        self.arm_button.setText("切回观察模式" if auto else "开启自动保存")
        self.pause_button.setText("恢复" if paused else "暂停")
        self.tray_pause.setText("恢复保护" if paused else "暂停保护")
        self.tray.setToolTip("创作工具箱 · " + self.mode_badge.text()[3:])

    def on_event(self, event: Event):
        now = datetime.now().strftime("%H:%M:%S")
        self.events.append((now, event))
        self.events = self.events[-200:]
        row = self.event_table.rowCount()
        self.event_table.insertRow(row)
        kind = {"system": "系统", "observe": "观察", "request": "保存请求", "reminder": "提醒", "error": "需处理"}.get(event.kind, event.kind)
        for i, text in enumerate((now, kind, event.app, event.message)):
            self.event_table.setItem(row, i, QTableWidgetItem(text))
        self.event_table.resizeRowToContents(row)
        if row >= 200:
            self.event_table.removeRow(0)
        self.event_table.scrollToBottom()
        try:
            self.store.event(event.kind, event.app, event.message)
        except OSError:
            self.footer.setText("本地日志暂时无法写入；本次状态仍可在活动记录中查看。")
        if event.kind in ("reminder", "error") and self.controller.automatic:
            self.tray.showMessage(event.app, event.message, QSystemTrayIcon.MessageIcon.Information, 4500)

    def tick(self):
        try:
            snap, decision = self.controller.tick()
            self.idle_metric.setText(f"{min(int(snap.idle), 9999)}s")
            self.request_metric.setText(str(self.controller.requests))
            self.observe_metric.setText(str(self.controller.observations))
            target = snap.target
            self.live_app.setText(target.name if target else "等待前台应用")
            title = target.title if target else "窗口不可用时，不会执行保存"
            self.live_title.setText(self.live_title.fontMetrics().elidedText(title, Qt.TextElideMode.ElideMiddle, 710))
            self.live_title.setToolTip(title)
            self.live_state.setText(decision.message + (f" · {decision.remaining} 秒" if decision.remaining else ""))
            profile = next((p for p in self.settings.profiles if p.id == decision.profile_id), None)
            if profile:
                style = self.settings.style if profile.style == "inherit" else profile.style
                custom = self.settings.custom if profile.style == "inherit" else profile.custom
                shortcut = resolve_shortcut(style, custom, self.backend.platform).text()
                self.live_shortcut.setText(f"{profile.name}  /  {shortcut}  /  {'仅提醒' if profile.reminder_only else '通用模式 · 保存结果未确认'}")
            else:
                self.live_shortcut.setText("添加或启用应用后，这里会显示它的保存规则。")
            if snap.permission:
                self.live_shortcut.setText(snap.permission)
        except Exception as exc:
            self.controller.paused = True
            self.update_mode()
            self.live_state.setText("状态检测异常，已暂停。请重新启动或检查系统权限。")
            if not getattr(self, "_reported_capture_error", False):
                self._reported_capture_error = True
                self.on_event(Event("error", "状态检测", f"检测失败：{type(exc).__name__}"))

    def selected_profile(self):
        row = self.profile_table.currentRow()
        return self.settings.profiles[row] if 0 <= row < len(self.settings.profiles) else None

    def commit_settings(self, profiles=None, style=None, custom=None):
        candidate = Settings(profiles if profiles is not None else self.settings.profiles,
                             style if style is not None else self.settings.style,
                             custom if custom is not None else self.settings.custom)
        try:
            self.store.save(candidate)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "设置未保存", str(exc))
            return False
        self.settings = candidate
        self.controller.settings = candidate
        self.disarm()
        self.refresh_profiles()
        self.on_event(Event("system", "设置", "设置已保存；切回观察模式以检查新规则"))
        return True

    def add_profile(self, checked=False, seed=None):
        dialog = ProfileDialog(self.backend.platform, seed, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            profile = dialog.result_profile
            duplicates = [p for p in self.settings.profiles if p.platform == profile.platform and p.identity.casefold() == profile.identity.casefold()]
            if duplicates:
                QMessageBox.information(self, "应用已存在", "此程序已经有规则，请编辑现有规则。")
                return
            self.commit_settings([*self.settings.profiles, profile])

    def edit_profile(self):
        existing = self.selected_profile()
        if not existing:
            return
        dialog = ProfileDialog(self.backend.platform, existing, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.commit_settings([dialog.result_profile if p.id == existing.id else p for p in self.settings.profiles])

    def flip_profile(self):
        existing = self.selected_profile()
        if existing:
            self.commit_settings([replace(p, enabled=not p.enabled) if p.id == existing.id else p for p in self.settings.profiles])

    def remove_profile(self):
        existing = self.selected_profile()
        if existing:
            self.commit_settings([p for p in self.settings.profiles if p.id != existing.id])

    def refresh_profiles(self):
        self.profile_table.setRowCount(len(self.settings.profiles))
        for row, profile in enumerate(self.settings.profiles):
            style = self.settings.style if profile.style == "inherit" else profile.style
            custom = self.settings.custom if profile.style == "inherit" else profile.custom
            try:
                shortcut = resolve_shortcut(style, custom, self.backend.platform).text()
            except ValueError:
                shortcut = "需配置"
            values = (profile.name, "已启用" if profile.enabled else "未启用", shortcut,
                      f"{profile.interval}s / {profile.idle}s", "仅提醒" if profile.reminder_only else "通用")
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(profile.identity if col == 0 else value)
                self.profile_table.setItem(row, col, item)
            self.profile_table.setRowHeight(row, 62)
        if self.settings.profiles:
            self.profile_table.selectRow(0)
        self.profile_count.setText(f"{sum(p.enabled for p in self.settings.profiles)} 个应用已启用")

    def begin_capture(self):
        self.capture_seconds = 5
        self.capture_button.setEnabled(False)
        self.capture_button.setText("请切换到目标应用 · 5 秒")
        self.capture_timer = QTimer(self)
        self.capture_timer.setInterval(1000)
        self.capture_timer.timeout.connect(self.capture_countdown)
        self.capture_timer.start()

    def capture_countdown(self):
        self.capture_seconds -= 1
        if self.capture_seconds > 0:
            self.capture_button.setText(f"请切换到目标应用 · {self.capture_seconds} 秒")
            return
        self.capture_timer.stop()
        self.capture_timer.deleteLater()
        self.capture_button.setEnabled(True)
        self.capture_button.setText("从前台应用添加")
        try:
            target = self.backend.capture().target
        except Exception:
            target = None
        self.show_main()
        if not target or target.pid == os.getpid():
            QMessageBox.information(self, "未选中目标应用", "请再次点击，然后在 5 秒内切换到要保护的软件。")
            return
        seed = Profile(uuid.uuid4().hex, Path(target.name).stem, target.identity, self.backend.platform,
                       reminder_only=any(word in target.name.casefold() for word in ("cubase", "nuendo", "resolve", "premiere", "ableton", "live", "logic", "reaper", "fl64", "studio one")))
        self.add_profile(seed=seed)

    def save_preferences(self):
        self.commit_settings(style=self.global_style.currentData(), custom=self.global_custom.text().strip())

    def clear_event_view(self):
        self.event_table.setRowCount(0)
        self.events.clear()

    def open_data(self):
        self.store.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root.resolve())))
