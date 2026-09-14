"""Native font browser with virtualized previews and independent metadata."""
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QAbstractListModel, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QStyledItemDelegate, QStyle, QTabWidget, QVBoxLayout, QWidget,
)

from .library import FontLibrary, read_file, write_file

SAMPLE = "创作，让灵感被看见。\nThe quick brown fox jumps over the lazy dog.\n0123456789  Aa Bb Cc"


def label(value, name=""):
    item = QLabel(value)
    item.setObjectName(name)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    return item


def button(value, callback):
    item = QPushButton(value)
    item.clicked.connect(callback)
    return item


def catalog():
    result = {}
    for family in QFontDatabase.families():
        if not QFontDatabase.isPrivateFamily(family):
            result[family] = {
                "styles": QFontDatabase.styles(family),
                "mono": QFontDatabase.isFixedPitch(family),
                "systems": [QFontDatabase.writingSystemName(s) for s in QFontDatabase.writingSystems(family)],
            }
    return result


class FontListModel(QAbstractListModel):
    def __init__(self, library, available, parent=None):
        super().__init__(parent)
        self.library, self.available = library, available
        self.families = []
        self.reload()

    def reload(self):
        self.beginResetModel()
        self.families = sorted(set(self.available) | set(self.library.data["fonts"]), key=str.casefold)
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.families)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.families):
            return None
        family = self.families[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole):
            return family
        if role == Qt.ItemDataRole.ToolTipRole:
            value = self.library.metadata(family)
            return family + "\n" + " · ".join(value["tags"]) + ("\n当前不可用；整理信息保留。" if family not in self.available else "")


class FontFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query, self.scope, self.system = "", "all", ""
        self.mono = False

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        family = model.families[row]
        meta = model.library.metadata(family)
        available = model.available.get(family)
        if self.scope == "favorites" and not meta["favorite"]:
            return False
        if self.scope == "missing" and available is not None:
            return False
        if self.scope.startswith("group:") and self.scope[6:] not in meta["groups"]:
            return False
        if self.mono and (not available or not available["mono"]):
            return False
        if self.system and (not available or self.system not in available["systems"]):
            return False
        searchable = " ".join([family, meta["alias"], *meta["tags"]]).casefold()
        return all(word in searchable for word in self.query.casefold().split())


class FontDelegate(QStyledItemDelegate):
    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return QSize(260, max(104, QFontMetrics(QFont("", self.page.size.value())).height() + 55))

    def paint(self, painter, option, index):
        family = index.data(Qt.ItemDataRole.UserRole)
        meta = self.page.library.metadata(family)
        available = self.page.model.available.get(family)
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#e1eddc" if selected else "#ffffff"))
        painter.setClipRect(option.rect.adjusted(10, 0, -10, 0))
        painter.setFont(option.font)
        painter.setPen(QColor("#284d3b"))
        caption = ("★  " if meta["favorite"] else "") + family
        if meta["alias"]:
            caption += " · " + meta["alias"]
        if not available:
            caption += " · 当前不可用"
        else:
            caption += f" · {len(available['styles'])} 个样式"
        rect = option.rect.adjusted(12, 7, -12, -7)
        painter.drawText(rect.left(), rect.top()+16, QFontMetrics(option.font).elidedText(caption, Qt.TextElideMode.ElideRight, rect.width()))
        if available:
            styles = available["styles"]
            font = QFontDatabase.font(family, "Regular" if "Regular" in styles else (styles[0] if styles else ""), self.page.size.value())
            painter.setFont(font)
            sample = " ".join(self.page.sample.toPlainText().splitlines())
            painter.drawText(rect.adjusted(0, 29, 0, -17), Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine, sample)
        else:
            painter.setPen(QColor("#8b7462"))
            painter.drawText(rect.left(), rect.top()+53, "预览不可用；重新安装后可刷新")
        painter.setFont(option.font)
        painter.setPen(QColor("#718077"))
        tags = " · ".join(meta["tags"]) or "选择后可加入分组、收藏或标记标签"
        painter.drawText(rect.left(), rect.bottom()-1, QFontMetrics(option.font).elidedText(tags, Qt.TextElideMode.ElideRight, rect.width()))
        painter.setPen(QColor("#e7ede4"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class FontPage(QWidget):
    def __init__(self, path=None, available=None):
        super().__init__()
        self.library = FontLibrary(path)
        self._catalog_override = available
        self.model = FontListModel(self.library, catalog() if available is None else available, self)
        self.proxy = FontFilter(self)
        self.proxy.setSourceModel(self.model)
        self._refreshing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(label("让好字体，下次也找得到。", "title"))
        root.addWidget(label("本机字体 · 项目分组 · 标签收藏 · 多栏对照。缺字可能由系统回退显示。", "muted"))
        self.sample = QPlainTextEdit(self.library.data["preferences"].get("sample") or SAMPLE)
        self.sample.setMaximumHeight(70)
        self.sample.setToolTip("预览文案最多保存 2000 字；整理操作不会安装或删除字体。")
        root.addWidget(self.sample)
        row = QHBoxLayout()
        row.addWidget(label("预览字号"))
        self.size = QSpinBox()
        self.size.setRange(8, 96)
        self.size.setValue(self.library.data["preferences"].get("size", 28))
        row.addWidget(self.size)
        row.addWidget(button("中英样句", lambda: self.sample.setPlainText(SAMPLE)))
        row.addStretch()
        row.addWidget(button("刷新字体", self.refresh_catalog))
        row.addWidget(button("导入整理", self.import_backup))
        row.addWidget(button("导出备份", self.export_backup))
        root.addLayout(row)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        browse = QWidget()
        layout = QVBoxLayout(browse)
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索字体名、别名或标签（空格组合）")
        self.search.setClearButtonEnabled(True)
        filter_row.addWidget(self.search, 1)
        self.system = QComboBox()
        self.system.setMaximumWidth(180)
        self.populate_systems()
        filter_row.addWidget(self.system)
        self.mono = QCheckBox("等宽")
        filter_row.addWidget(self.mono)
        layout.addLayout(filter_row)
        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.groups = QListWidget()
        left_layout.addWidget(self.groups)
        left_layout.addWidget(button("＋ 新建分组", self.add_group))
        small = QHBoxLayout()
        small.addWidget(button("改名", self.rename_group))
        small.addWidget(button("删组", self.delete_group))
        left_layout.addLayout(small)
        split.addWidget(left)
        self.list = QListView()
        self.list.setModel(self.proxy)
        self.list.setItemDelegate(FontDelegate(self))
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setStyleSheet("QListView {background:white; border:1px solid #d5dfd1; border-radius:6px;}")
        split.addWidget(self.list)
        split.setStretchFactor(1, 1)
        split.setSizes([155, 630])
        layout.addWidget(split, 1)
        self.count = label("", "muted")
        layout.addWidget(self.count)
        batch = QHBoxLayout()
        self.operations = QComboBox()
        self.operations.addItems(["加入分组…", "移出当前分组", "收藏所选", "取消收藏", "添加标签…", "移除标签…"])
        batch.addWidget(self.operations)
        batch.addWidget(button("执行", self.batch_action))
        batch.addWidget(button("详情 / 备注", self.edit_details))
        batch.addStretch()
        batch.addWidget(button("对照所选（2–4）", self.compare_selected))
        layout.addLayout(batch)
        self.tabs.addTab(browse, "字体库")
        compare = QWidget()
        compare_layout = QVBoxLayout(compare)
        compare_layout.addWidget(label("选择真实可用的字体样式。缺字时系统可能回退；预览不代表商用授权。", "muted"))
        count_row = QHBoxLayout()
        count_row.addWidget(label("对照数量"))
        self.compare_count = QSpinBox()
        self.compare_count.setRange(2, 4)
        count_row.addWidget(self.compare_count)
        count_row.addStretch()
        compare_layout.addLayout(count_row)
        compare_body = QWidget()
        grid = QGridLayout(compare_body)
        self.fonts, self.styles, self.previews, self.cards = [], [], [], []
        available_names = sorted(self.model.available, key=str.casefold)
        for i in range(4):
            card = QWidget()
            column = QVBoxLayout(card)
            column.setContentsMargins(0, 0, 0, 0)
            family = QComboBox()
            family.addItems(available_names)
            family.setMinimumContentsLength(10)
            family.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            family.setCurrentIndex(min(i, max(0, len(available_names)-1)))
            style = QComboBox()
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setMinimumHeight(140)
            self.fonts.append(family)
            self.styles.append(style)
            self.previews.append(preview)
            self.cards.append(card)
            column.addWidget(family)
            column.addWidget(style)
            column.addWidget(preview, 1)
            column.addWidget(button("复制字体名称", lambda checked=False, index=i: self.copy_family(index)))
            grid.addWidget(card, i//2, i%2)
            family.currentTextChanged.connect(lambda _, index=i: self.update_styles(index))
            style.currentTextChanged.connect(self.update_preview)
        compare_scroll = QScrollArea()
        compare_scroll.setWidgetResizable(True)
        compare_scroll.setWidget(compare_body)
        compare_layout.addWidget(compare_scroll, 1)
        self.tabs.addTab(compare, "多栏对照")
        self.status = label(self.library.warning or "Ctrl / Command 多选，Shift 连选；分组与标签保存在本机。", "muted")
        root.addWidget(self.status)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.repaint_list)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self.flush_preferences)
        self.sample.textChanged.connect(self.sample_changed)
        self.size.valueChanged.connect(self.sample_changed)
        self.search.textChanged.connect(self.apply_filter)
        self.system.currentIndexChanged.connect(self.apply_filter)
        self.mono.toggled.connect(self.apply_filter)
        self.groups.currentRowChanged.connect(self.apply_filter)
        self.list.selectionModel().selectionChanged.connect(self.update_count)
        self.compare_count.valueChanged.connect(self.update_cards)
        for i in range(4):
            self.update_styles(i)
        self.update_cards()
        self.populate_groups()
        QApplication.instance().aboutToQuit.connect(self.flush_preferences)

    def selected(self):
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectionModel().selectedIndexes()]

    def populate_systems(self):
        current = self.system.currentData() if self.system.count() else ""
        self.system.blockSignals(True)
        self.system.clear()
        self.system.addItem("全部文字系统", "")
        systems = sorted({s for v in self.model.available.values() for s in v["systems"]})
        for system in systems:
            self.system.addItem(system, system)
        self.system.setCurrentIndex(max(0, self.system.findData(current)))
        self.system.blockSignals(False)

    def populate_groups(self, scope=None):
        scope = scope or self.proxy.scope
        self.groups.blockSignals(True)
        self.groups.clear()
        for name, value in [("全部字体", "all"), ("★ 收藏", "favorites"), ("当前不可用", "missing"),
                            *[(name, "group:"+gid) for gid, name in self.library.data["groups"].items()]]:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.groups.addItem(item)
            if value == scope:
                self.groups.setCurrentItem(item)
        if self.groups.currentRow() < 0:
            self.groups.setCurrentRow(0)
        self.groups.blockSignals(False)
        self.apply_filter()

    def apply_filter(self, *args):
        if self._refreshing:
            return
        self.proxy.query = self.search.text().strip()
        self.proxy.system = self.system.currentData() or ""
        self.proxy.mono = self.mono.isChecked()
        item = self.groups.currentItem()
        self.proxy.scope = item.data(Qt.ItemDataRole.UserRole) if item else "all"
        self.proxy.invalidate()
        self.update_count()

    def update_count(self, *args):
        parts = [f"显示 {self.proxy.rowCount()} / {self.model.rowCount()} 个家族", f"已选 {len(self.selected())} 个"]
        if self.search.text().strip():
            parts.append("搜索："+self.search.text().strip())
        if self.proxy.system:
            parts.append(self.proxy.system)
        if self.proxy.mono:
            parts.append("等宽")
        if self.proxy.rowCount() == 0:
            parts.append("无匹配字体，可清除筛选或切换分组")
        self.count.setText(" · ".join(parts))

    def run_change(self, operation, message="已保存字体整理信息。"):
        selected = set(self.selected())
        try:
            result = operation()
        except (OSError, ValueError) as exc:
            self.status.setText("未保存："+str(exc))
            return False
        self.model.reload()
        self.populate_groups()
        selection = self.list.selectionModel()
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            if index.data(Qt.ItemDataRole.UserRole) in selected:
                selection.select(index, selection.SelectionFlag.Select)
        self.status.setText(message)
        return True

    def add_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称（最多 80 字）")
        if ok:
            self.run_change(lambda: self.library.add_group(name))

    def current_gid(self):
        return self.proxy.scope[6:] if self.proxy.scope.startswith("group:") else None

    def rename_group(self):
        gid = self.current_gid()
        if not gid:
            self.status.setText("请先选择左侧的自定义分组。")
            return
        name, ok = QInputDialog.getText(self, "重命名分组", "新名称", text=self.library.data["groups"][gid])
        if ok:
            self.run_change(lambda: self.library.rename_group(gid, name))

    def delete_group(self):
        gid = self.current_gid()
        if not gid:
            self.status.setText("请先选择左侧的自定义分组。")
            return
        if QMessageBox.question(self, "删除分组", "删除此分组？字体文件、标签、备注和其他分组都会保留。") == QMessageBox.StandardButton.Yes:
            self.run_change(lambda: self.library.delete_group(gid))

    def batch_action(self):
        families = self.selected()
        if not families:
            self.status.setText("请先选择字体，可按 Ctrl / Command 多选。")
            return
        choice = self.operations.currentIndex()
        if choice == 0:
            groups = self.library.data["groups"]
            if not groups:
                self.status.setText("请先新建一个分组。")
                return
            name, ok = QInputDialog.getItem(self, "加入分组", "所选字体同时保留在原有分组中", list(groups.values()), editable=False)
            if ok:
                gid = next(g for g, n in groups.items() if n == name)
                self.run_change(lambda: self.library.membership(families, gid))
        elif choice == 1:
            self.run_change(lambda: self.library.membership(families, self.current_gid(), False))
        elif choice in (2, 3):
            self.run_change(lambda: self.library.edit(families, favorite=choice == 2))
        else:
            tag, ok = QInputDialog.getText(self, "标签", "输入一个标签（最多 40 字）")
            if ok:
                self.run_change(lambda: self.library.tag(families, tag, choice == 4))

    def edit_details(self):
        families = self.selected()
        if len(families) != 1:
            self.status.setText("详情与备注请只选择一款字体。")
            return
        family = families[0]
        meta = self.library.metadata(family)
        dialog = QDialog(self)
        dialog.setWindowTitle("字体详情与备注")
        dialog.resize(510, 440)
        form = QFormLayout(dialog)
        form.addRow(label(family, "section"))
        form.addRow("分组", label("、".join(self.library.data["groups"][g] for g in meta["groups"]) or "未分组"))
        form.addRow("标签", label("、".join(meta["tags"]) or "无"))
        alias, source = QLineEdit(meta["alias"]), QLineEdit(meta["source"])
        alias.setMaxLength(120)
        source.setMaxLength(2000)
        note = QPlainTextEdit(meta["note"])
        form.addRow("别名", alias)
        form.addRow("来源 / 许可链接", source)
        form.addRow("用途与授权备注", note)
        form.addRow(label("备注由你填写；工具箱不会根据字体名判断商用授权。来源链接仅保存为文本。", "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.run_change(lambda: self.library.edit([family], alias=alias.text(), source=source.text(), note=note.toPlainText()))

    def update_styles(self, i):
        family = self.fonts[i].currentText()
        previous = self.styles[i].currentText()
        self.styles[i].blockSignals(True)
        self.styles[i].clear()
        self.styles[i].addItems(self.model.available.get(family, {}).get("styles", []))
        index = self.styles[i].findText(previous)
        if index < 0:
            index = self.styles[i].findText("Regular")
        self.styles[i].setCurrentIndex(max(0, index))
        self.styles[i].blockSignals(False)
        self.update_preview()

    def update_preview(self, *args):
        for family, style, preview in zip(self.fonts, self.styles, self.previews):
            name = family.currentText()
            usable = name in self.model.available and bool(style.currentText())
            preview.setEnabled(usable)
            font = QFontDatabase.font(name, style.currentText(), self.size.value()) if usable else QFont()
            preview.setFont(font)
            preview.setStyleSheet(f"font-size:{self.size.value()}pt; min-height:140px;")
            preview.setPlainText(self.sample.toPlainText() if usable else "字体当前不可用")
            preview.moveCursor(QTextCursor.MoveOperation.Start)

    def update_cards(self, *args):
        for i, card in enumerate(self.cards):
            card.setVisible(i < self.compare_count.value())

    def compare_selected(self):
        families = self.selected()
        if not 2 <= len(families) <= 4:
            self.status.setText("请选择 2–4 款字体进行对照。")
            return
        if any(f not in self.model.available for f in families):
            self.status.setText("所选字体中有当前不可用项，请先刷新或重新选择。")
            return
        self.compare_count.setValue(len(families))
        for i, family in enumerate(families):
            self.fonts[i].setCurrentText(family)
        self.tabs.setCurrentIndex(1)

    def copy_family(self, i):
        family = self.fonts[i].currentText()
        if family in self.model.available:
            QApplication.clipboard().setText(family)
            self.status.setText("已复制字体名称："+family)

    def repaint_list(self):
        self.list.doItemsLayout()
        self.list.viewport().update()

    def sample_changed(self, *args):
        self.update_preview()
        self.preview_timer.start()
        self.save_timer.start()

    def flush_preferences(self):
        self.save_timer.stop()
        if self.library.read_only:
            return False
        prefs = {"sample": self.sample.toPlainText(), "size": self.size.value()}
        if prefs == self.library.data["preferences"]:
            return True
        try:
            self.library.change(lambda d: d.update(preferences=prefs))
        except (ValueError, OSError) as exc:
            self.status.setText("预览设置未保存："+str(exc))
            return False
        return True

    def refresh_catalog(self):
        self.model.available = catalog() if self._catalog_override is None else self._catalog_override
        self._refreshing = True
        self.model.reload()
        self.populate_systems()
        names = sorted(self.model.available, key=str.casefold)
        for i, box in enumerate(self.fonts):
            current = box.currentText()
            box.blockSignals(True)
            box.clear()
            box.addItems(names)
            box.setCurrentText(current)
            box.blockSignals(False)
            self.update_styles(i)
        self._refreshing = False
        self.apply_filter()
        self.status.setText("已刷新系统字体。当前不可用字体的分组、标签与备注仍保留。")

    def import_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入字体整理备份", "", "JSON (*.json)")
        if not path:
            return
        try:
            incoming = read_file(path)
        except (ValueError, OSError) as exc:
            self.status.setText("导入失败："+str(exc))
            return
        unavailable = sum(f not in self.model.available for f in incoming["fonts"])
        description = (f"合并 {len(incoming['fonts'])} 条字体记录与 {len(incoming['groups'])} 个分组。\n"
                       f"其中 {unavailable} 款字体当前不可用，记录会保留。\n"
                       "按完整字体家族名称匹配；不自动推断跨系统别名。收藏和标签合并，冲突备注保留本机值。")
        if QMessageBox.question(self, "预览导入", description) != QMessageBox.StandardButton.Yes:
            return
        conflicts = []
        if self.run_change(lambda: conflicts.extend(self.library.merge(incoming)), "已合并备份；当前文案与字号保持不变。"):
            if conflicts:
                QMessageBox.information(self, "导入冲突", "以下字段保留了本机值，导入文件未修改：\n"+"\n".join(conflicts[:30]))

    def export_backup(self):
        if self.library.read_only:
            self.status.setText("当前原库未成功加载，请直接备份原 fonts.json 文件。")
            return
        if not self.flush_preferences():
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出字体整理备份", "font-library.json", "JSON (*.json)")
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(".json")
            if destination.exists() and QMessageBox.question(self, "覆盖备份", "补全 .json 扩展名后文件已存在，是否覆盖该备份？") != QMessageBox.StandardButton.Yes:
                return
        try:
            if self.library.path and destination.resolve() == self.library.path.resolve():
                raise ValueError("请选择独立备份文件，不要覆盖正在使用的字体库")
            write_file(destination, self.library.data)
            self.status.setText("已导出分组、标签、备注与预览设置；不包含字体文件。")
        except (ValueError, OSError) as exc:
            self.status.setText("导出失败："+str(exc))

    def closeEvent(self, event):
        self.flush_preferences()
        super().closeEvent(event)
