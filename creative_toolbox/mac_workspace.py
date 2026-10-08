"""Mac workbench: a lightweight home and keyboard-first tool launcher.

Only the catalogue is read here. Resources still load on first use.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from .workspace import TOOLS, TOOL_BY_ID, search_tools
from .workspace_ui import text
from .theme import icon


class CommandPalette(QDialog):
    open_requested = Signal(str)
    route_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速打开")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索工具或页面，例如：字体、色板、BPM")
        self.search.setAccessibleName("搜索工具和页面")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setAccessibleName("匹配的工具和页面")
        layout.addWidget(self.results, 1)
        self.hint = text("↑ ↓ 选择    ↵ 打开    esc 关闭", "muted")
        layout.addWidget(self.hint)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.open_current)
        self.results.itemActivated.connect(self.open_current)
        self.search.installEventFilter(self)
        self.refresh()

    def refresh(self):
        self.results.clear()
        query = self.search.text().strip()
        for tool in search_tools(query):
            item = QListWidgetItem(icon(tool.id), f"{tool.name}    ·    {tool.description}")
            item.setData(Qt.ItemDataRole.UserRole, ("tool", tool.id))
            self.results.addItem(item)
        for key, title, keywords in (("home", "工作台", "home"),
                                      ("library", "搜索全部资料", "资源 library search"),
                                      ("settings", "设置", "settings preferences"),
                                      ("help", "使用帮助", "help")):
            if all(word in (title + keywords).casefold() for word in query.casefold().split()):
                item = QListWidgetItem(icon(key), title)
                item.setData(Qt.ItemDataRole.UserRole, ("route", key))
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        self.hint.setText("↑ ↓ 选择    ↵ 打开    esc 关闭" if self.results.count()
                          else "未找到匹配项。请使用工具名称或功能关键词搜索。")

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                self.results.setCurrentRow(max(0, min(self.results.count() - 1,
                                                       self.results.currentRow() + step)))
                return True
        return super().eventFilter(watched, event)

    def open_current(self, *_):
        item = self.results.currentItem()
        if item is None:
            return
        kind, key = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        (self.open_requested if kind == "tool" else self.route_requested).emit(key)

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus()
        self.search.selectAll()


class MacHomePage(QWidget):
    open_requested = Signal(str)
    favorite_requested = Signal(str)
    directory_requested = Signal()
    help_requested = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body.setObjectName("macHome")
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(4, 8, 4, 16)
        self.rows.setSpacing(20)
        scroll.setWidget(self.body)
        root.addWidget(scroll)
        self.refresh()

    def refresh(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.visible_tool_ids = []
        heading = QWidget()
        top = QVBoxLayout(heading)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(text("创作工作台", "macWelcome"))
        top.addWidget(text("集中管理创作资源，快速访问常用工具。", "muted"))
        self.rows.addWidget(heading)
        if self.store.warning:
            self.rows.addWidget(text(self.store.warning, "muted"))

        capture = QFrame()
        capture.setObjectName("macCapture")
        row = QHBoxLayout(capture)
        row.setContentsMargins(22, 22, 22, 22)
        badge = QLabel()
        badge.setPixmap(icon("assets").pixmap(38, 38))
        row.addWidget(badge)
        row.addSpacing(12)
        copy = QVBoxLayout()
        copy.addWidget(text("图片素材管理", "section"))
        copy.addWidget(text("导入参考图片，按集合归类，并提取图片配色。", "muted"))
        row.addLayout(copy, 1)
        collect = QPushButton("收集图片")
        collect.setObjectName("primary")
        collect.clicked.connect(lambda: self.open_requested.emit("assets"))
        row.addWidget(collect)
        self.rows.addWidget(capture)

        title = QWidget()
        line = QHBoxLayout(title)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(text("常用工具", "section"))
        line.addStretch()
        all_tools = QPushButton("全部工具  →")
        all_tools.setObjectName("secondary")
        all_tools.clicked.connect(self.directory_requested.emit)
        line.addWidget(all_tools)
        self.rows.addWidget(title)
        favorites = [TOOL_BY_ID[key] for key in self.store.data["favorites"] if key in TOOL_BY_ID]
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for i, tool in enumerate(favorites):
            self.visible_tool_ids.append(tool.id)
            card = QFrame()
            card.setObjectName("macToolCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 14)
            layout.setSpacing(10)
            head = QHBoxLayout()
            badge = QLabel()
            badge.setPixmap(icon(tool.id).pixmap(26, 26))
            head.addWidget(badge)
            head.addStretch()
            favorite = QPushButton("★")
            favorite.setObjectName("secondary")
            favorite.setToolTip("取消收藏" + tool.name)
            favorite.setAccessibleName("取消收藏" + tool.name)
            favorite.setEnabled(not self.store.read_only)
            favorite.clicked.connect(lambda checked=False, key=tool.id: self.favorite_requested.emit(key))
            head.addWidget(favorite)
            layout.addLayout(head)
            layout.addWidget(text(tool.name, "section"))
            layout.addWidget(text(tool.description, "muted"), 1)
            action = QPushButton("打开  →")
            action.setAccessibleName("打开" + tool.name)
            action.setObjectName("secondary")
            action.clicked.connect(lambda checked=False, key=tool.id: self.open_requested.emit(key))
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignRight)
            grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        if not favorites:
            grid.addWidget(text("暂无收藏工具。可在「全部工具」中添加收藏。", "muted"), 0, 0, 1, 3)
        self.rows.addWidget(grid_widget)
        self.rows.addWidget(text("最近使用", "section"))
        recent = [TOOL_BY_ID[item["id"]] for item in self.store.data["recent"] if item["id"] in TOOL_BY_ID]
        if not recent:
            self.rows.addWidget(text("暂无使用记录。已打开的工具将显示在此列表中。", "muted"))
        else:
            for tool in recent[:3]:
                action = QPushButton(icon(tool.id), tool.name + "    →")
                action.setObjectName("macRecent")
                action.clicked.connect(lambda checked=False, key=tool.id: self.open_requested.emit(key))
                self.rows.addWidget(action)
        self.rows.addStretch()
        guide = QPushButton("查看使用指南  ↗")
        guide.setObjectName("secondary")
        guide.clicked.connect(self.help_requested.emit)
        self.rows.addWidget(guide, 0, Qt.AlignmentFlag.AlignLeft)
