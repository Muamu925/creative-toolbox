"""Lightweight entry pages. Opening the directory never constructs a tool."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from .theme import icon
from .workspace import TOOLS, TOOL_BY_ID, search_tools


def text(value, name=""):
    item = QLabel(value)
    item.setObjectName(name)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    return item


class WorkspacePage(QWidget):
    open_requested = Signal(str)
    favorite_requested = Signal(str)
    directory_requested = Signal()
    help_requested = Signal()

    def __init__(self, kind, store, protection_reason=""):
        super().__init__()
        self.kind, self.store = kind, store
        self.protection_reason = protection_reason
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        heading, subtitle = {
            "home": ("创作，从这里继续。", "收集灵感、整理资料，让手边的工具各就其位。"),
            "library": ("你的资源库", "收集参考图片，整理字体与色板；资料保存在本机。"),
            "tools": ("所有工具", "直接开始一个小任务，无需先创建项目。"),
        }[kind]
        root.addWidget(text(heading, "title"))
        root.addWidget(text(subtitle, "muted"))
        self.notice = text("", "muted")
        root.addWidget(self.notice)
        if kind == "tools":
            root.addWidget(text("搜索工具", "section"))
            self.search = QLineEdit()
            self.search.setAccessibleName("搜索工具")
            self.search.setClearButtonEnabled(True)
            self.search.setPlaceholderText("搜索工具，例如：字体、毫米、BPM、提色、保存")
            self.search.textChanged.connect(self.refresh)
            root.addWidget(self.search)
        elif kind == "home":
            collect = QPushButton("收集参考图片")
            collect.setObjectName("primary")
            collect.clicked.connect(lambda: self.open_requested.emit("assets"))
            quick = QHBoxLayout()
            quick.setSpacing(10)
            quick.addWidget(collect)
            action = QPushButton("浏览全部工具 →")
            action.clicked.connect(self.directory_requested.emit)
            quick.addWidget(action)
            quick.addStretch()
            root.addLayout(quick)
            guide = QPushButton("第一次使用？查看上手指南")
            guide.setObjectName("secondary")
            guide.clicked.connect(self.help_requested.emit)
            root.addWidget(guide, 0, Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(0, 0, 8, 0)
        self.rows.setSpacing(12)
        scroll.setWidget(self.body)
        self.body.setAutoFillBackground(False)
        root.addWidget(scroll, 1)
        self.visible_tool_ids = []
        self.refresh()

    def add_tool(self, tool, compact=False):
        self.visible_tool_ids.append(tool.id)
        card = QFrame()
        card.setObjectName("toolRow")
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 18, 14)
        badge = QLabel()
        badge.setPixmap(icon(tool.id).pixmap(28, 28))
        badge.setFixedWidth(42)
        row.addWidget(badge)
        copy = QVBoxLayout()
        copy.setSpacing(5)
        copy.addWidget(text(tool.name, "section"))
        if not compact:
            copy.addWidget(text(tool.description, "muted"))
            if tool.requires_protection and self.protection_reason:
                copy.addWidget(text("保护暂不可用 · 可查看规则与诊断", "muted"))
        row.addLayout(copy, 1)
        star = QPushButton("已收藏" if tool.id in self.store.data["favorites"] else "收藏")
        star.setCheckable(True)
        star.setObjectName("secondary")
        star.setChecked(tool.id in self.store.data["favorites"])
        star.setAccessibleName(("取消收藏" if star.isChecked() else "收藏") + tool.name)
        star.setEnabled(not self.store.read_only)
        star.clicked.connect(lambda checked=False, key=tool.id: self.favorite_requested.emit(key))
        row.addWidget(star)
        action = QPushButton("打开  →")
        action.setObjectName("secondary")
        action.setAccessibleName("打开" + tool.name)
        action.clicked.connect(lambda checked=False, key=tool.id: self.open_requested.emit(key))
        row.addWidget(action)
        self.rows.addWidget(card)

    def refresh(self, *_):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.visible_tool_ids = []
        self.notice.setText(self.store.warning)
        self.notice.setVisible(bool(self.store.warning))
        if self.kind == "home":
            self.rows.addWidget(text("常用工具", "section"))
            favorites = [TOOL_BY_ID[key] for key in self.store.data["favorites"] if key in TOOL_BY_ID]
            for tool in favorites:
                self.add_tool(tool, compact=True)
            if not favorites:
                self.rows.addWidget(text("还没有收藏的工具。在工具页点击「收藏」，下次从这里打开。", "muted"))
            self.rows.addWidget(text("最近使用", "section"))
            recent = [TOOL_BY_ID[item["id"]] for item in self.store.data["recent"] if item["id"] in TOOL_BY_ID]
            for tool in recent[:5]:
                action = QPushButton(tool.name + "  →")
                action.clicked.connect(lambda checked=False, key=tool.id: self.open_requested.emit(key))
                self.rows.addWidget(action)
            if not recent:
                self.rows.addWidget(text("最近打开的工具会显示在这里，方便下次继续。", "muted"))
        else:
            matches = search_tools(self.search.text()) if self.kind == "tools" else [tool for tool in TOOLS if tool.area == "library"]
            for tool in matches:
                self.add_tool(tool)
            if not matches:
                self.rows.addWidget(text("没有找到工具。试试「尺寸」「字体」或「保存」。", "muted"))
        self.rows.addStretch()
