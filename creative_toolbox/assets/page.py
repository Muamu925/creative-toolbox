"""Image inbox, metadata editor and floating reference viewer."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QPixmap, QImageReader, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QComboBox, QCheckBox, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QFileDialog, QMessageBox, QFormLayout,
    QProgressBar, QDialog, QScrollArea, QSizePolicy, QInputDialog, QMenu, QDialogButtonBox,
)
from .library import AssetStore, MAX_BATCH, MAX_PIXELS
from .jobs import AssetJob


def label(value, name=""):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setObjectName(name)
    return widget


def button(value, slot, primary=False):
    widget = QPushButton(value)
    widget.clicked.connect(slot)
    widget.setObjectName("primary" if primary else "secondary")
    return widget


def load_preview(path, maximum=1200):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
        raise ValueError("预览不可用")
    reader.setScaledSize(size.scaled(QSize(maximum, maximum), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError("预览不可用；可从完整备份恢复")
    return QPixmap.fromImage(image)


class ReferenceWindow(QDialog):
    def __init__(self, title, pixmap, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle(title + " · 图片参考")
        self.resize(620, 520)
        self.setMinimumSize(300, 240)
        self.pixmap = pixmap
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.pin = QCheckBox("始终置顶")
        self.pin.setChecked(True)
        self.pin.toggled.connect(self.set_pinned)
        top.addWidget(self.pin)
        top.addStretch()
        top.addWidget(button("关闭", self.close))
        root.addLayout(top)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(1, 1)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        root.addWidget(self.image, 1)
        root.addWidget(label("适应窗口显示 · 预览最长边 1200 px，托管原件保持不变", "muted"))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        QApplication.instance().screenRemoved.connect(self.ensure_visible)

    def set_pinned(self, checked):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.image.setPixmap(self.pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_visible()
        self.image.setPixmap(self.pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    def ensure_visible(self, *_):
        if not any(screen.availableGeometry().intersects(self.frameGeometry()) for screen in QApplication.screens()):
            area = QApplication.primaryScreen().availableGeometry()
            self.move(area.center() - self.rect().center())


class AssetPage(QWidget):
    palette_requested = Signal()
    feedback = Signal(str)
    PAGE_SIZE = 60

    def __init__(self, data_root: Path):
        super().__init__()
        self.palette_provider = None
        self.local_palette_model = None
        self.import_collection = None
        self.data_root = Path(data_root)
        self.location_file = self.data_root / "asset-location.json"
        root = self.data_root / "assets"
        if self.location_file.exists():
            if self.location_file.stat().st_size > 4096:
                raise ValueError("素材库位置设置过大")
            raw = json.loads(self.location_file.read_text(encoding="utf-8"))
            name = raw.get("directory")
            if raw.get("schema") != 1 or not isinstance(name, str) or not re.fullmatch(r"assets-restored-[0-9a-f]{32}", name):
                raise ValueError("素材库位置设置无效，原文件已保留")
            root = self.data_root / name
            if not (root / "library.sqlite3").exists():
                raise ValueError("恢复的素材库目录缺失；请检查数据目录")
        self.store = AssetStore(root)
        interrupted = self.store.recover_tasks()
        self.worker = None
        self.reference = None
        self.current_id = None
        self.dirty = False
        self.loading = False
        self.closed = False
        self.offset = 0
        self.applied_filter = ("", "all", None)
        self.exit_after_job = False
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label("图片素材", "title"))
        layout.addWidget(label("拖入或粘贴图片，稍后整理。支持 PNG / JPEG。", "muted"))
        bar = QHBoxLayout()
        self.import_button = button("导入图片", self.choose_files, True)
        self.paste_button = button("粘贴图片", self.paste_image)
        self.backup_button = button("备份素材库", self.backup)
        self.restore_backup_button = button("恢复备份", self.restore_backup)
        for widget in (self.import_button, self.paste_button, self.backup_button, self.restore_backup_button):
            bar.addWidget(widget)
        bar.addStretch()
        layout.addLayout(bar)
        filters = QHBoxLayout()
        filters.addWidget(label("查找"))
        self.search = QLineEdit()
        self.search.setAccessibleName("搜索素材名称、标签、来源或备注")
        self.search.setPlaceholderText("名称、标签、来源或备注")
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 1)
        self.scope = QComboBox()
        for name, key in (("全部素材", "all"), ("待整理", "inbox"), ("回收站", "trash")):
            self.scope.addItem(name, key)
        self.scope.setAccessibleName("素材范围")
        filters.addWidget(self.scope)
        layout.addLayout(filters)
        groups = QHBoxLayout()
        groups.addWidget(label("集合"))
        self.collection = QComboBox()
        self.collection.setAccessibleName("筛选图片集合")
        self.collection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.collection.setMinimumContentsLength(10)
        groups.addWidget(self.collection, 1)
        self.manage_collections = QPushButton("管理集合")
        self.manage_collections.setObjectName("secondary")
        menu = QMenu(self.manage_collections)
        menu.addAction("新建集合", lambda: self.edit_collection(False))
        self.rename_collection_action = menu.addAction("重命名当前集合", lambda: self.edit_collection(True))
        self.delete_collection_action = menu.addAction("移除当前集合", self.remove_collection)
        menu.aboutToShow.connect(lambda: [
            action.setEnabled(bool(self.collection.currentData()))
            for action in (self.rename_collection_action, self.delete_collection_action)])
        self.manage_collections.setMenu(menu)
        groups.addWidget(self.manage_collections)
        layout.addLayout(groups)
        self.reload_collections()
        self.splitter = QSplitter()
        layout.addWidget(self.splitter, 1)
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        self.count = label("", "muted")
        left_box.addWidget(self.count)
        self.list = QListWidget()
        self.list.setIconSize(QSize(84, 64))
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setAccessibleName("图片素材列表")
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        left_box.addWidget(self.list, 1)
        self.empty = label("还没有素材。拖入图片或点击「导入图片」。", "muted")
        left_box.addWidget(self.empty)
        pages = QHBoxLayout()
        self.previous = button("上一页", lambda: self.change_page(-1))
        self.next = button("下一页", lambda: self.change_page(1))
        pages.addWidget(self.previous)
        pages.addWidget(self.next)
        left_box.addLayout(pages)
        self.splitter.addWidget(left)
        detail = QWidget()
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(14, 0, 0, 0)
        self.preview = QLabel("选择图片查看预览")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(80)
        self.preview.setMaximumHeight(120)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail_box.addWidget(self.preview)
        self.dimensions = label("", "muted")
        detail_box.addWidget(self.dimensions)
        self.editor = QWidget()
        form = QFormLayout(self.editor)
        form.setContentsMargins(0, 0, 0, 0)
        self.title = QLineEdit()
        self.title.setMaxLength(200)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("用逗号分隔，例如：海报, 自然")
        self.source = QLineEdit()
        self.source.setMaxLength(2000)
        self.source.setPlaceholderText("可选，记录网页地址或作者")
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(70)
        self.reviewed = QCheckBox("已整理")
        for name, widget in (("名称", self.title), ("标签", self.tags), ("来源", self.source), ("备注", self.notes)):
            widget.setAccessibleName("素材" + name)
            form.addRow(name, widget)
        form.addRow("", self.reviewed)
        detail_box.addWidget(self.editor)
        actions = QHBoxLayout()
        self.save_button = button("保存整理", self.save_and_refresh, True)
        self.reference_button = button("置顶查看", self.open_reference)
        self.remove_button = button("移到回收站", self.toggle_trash)
        for widget in (self.save_button, self.reference_button):
            actions.addWidget(widget)
        self.origin = label("", "muted")
        self.origin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail_box.addWidget(self.origin)
        detail_box.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(detail)
        detail.setAutoFillBackground(False)
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.addWidget(scroll, 1)
        right_box.addLayout(actions)
        more = QPushButton("更多操作")
        more.setObjectName("secondary")
        self.more_button = more
        menu = QMenu(more)
        self.membership_action = menu.addAction("加入 / 移出集合", self.organize_collections)
        self.extract_action = menu.addAction("从图片创建色板", self.extract_palette)
        self.linked_action = menu.addAction("打开关联色板", self.open_linked_palette)
        more.setMenu(menu)
        footer = QHBoxLayout()
        footer.addWidget(more)
        footer.addWidget(self.remove_button)
        right_box.addLayout(footer)
        self.splitter.addWidget(right)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([370, 430])
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.cancel_button = button("取消任务", self.cancel_job)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel_button)
        layout.addLayout(progress_row)
        self.progress.hide()
        self.cancel_button.hide()
        self.status = label("移到回收站的图片仍可恢复。", "muted")
        layout.addWidget(self.status)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(80)
        self.errors.hide()
        layout.addWidget(self.errors)
        self.location = label("", "muted")
        layout.addWidget(self.location)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.filter_changed)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.scope.currentIndexChanged.connect(self.filter_changed)
        self.collection.currentIndexChanged.connect(self.filter_changed)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.list.itemDoubleClicked.connect(lambda *_: self.open_reference())
        for field in (self.title, self.tags, self.source):
            field.textChanged.connect(self.mark_dirty)
        self.notes.textChanged.connect(self.mark_dirty)
        self.reviewed.toggled.connect(self.mark_dirty)
        self.refresh()
        if interrupted:
            self.status.setText(f"发现 {interrupted} 个中断任务；已完成的素材保留，可重新选择剩余图片导入。")

    def mark_dirty(self, *_):
        if not self.loading and self.current_id:
            self.dirty = True
        self.save_button.setEnabled(bool(self.current_id and self.dirty and not self.worker))

    def confirm_details(self):
        if not self.dirty:
            return True
        result = QMessageBox.question(self, "整理尚未保存", "保存当前素材的名称、标签与备注？",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if result == QMessageBox.StandardButton.Cancel:
            return False
        if result == QMessageBox.StandardButton.Save:
            return self.save_details()
        self.dirty = False
        return True

    def refresh(self, selected=None):
        rows, total = self.store.list_assets(self.search.text(), self.scope.currentData(), self.offset, self.PAGE_SIZE, self.collection.currentData())
        if not rows and self.offset:
            self.offset = 0
            rows, total = self.store.list_assets(self.search.text(), self.scope.currentData(), 0, self.PAGE_SIZE, self.collection.currentData())
        wanted = selected or self.current_id
        self.list.blockSignals(True)
        self.list.clear()
        selection = None
        for row in rows:
            item = QListWidgetItem(row["title"] + ("  · 待整理" if not row["reviewed"] else ""))
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(row["title"] + "\n" + " · ".join(row["tags"]))
            try:
                item.setIcon(QIcon(load_preview(self.store.path_for(row["id"], True), 100)))
            except (OSError, ValueError):
                item.setToolTip(row["title"] + "\n预览缺失，可从备份恢复")
            self.list.addItem(item)
            if row["id"] == wanted:
                selection = item
        self.list.setCurrentItem(selection)
        self.list.blockSignals(False)
        self.empty.setVisible(total == 0)
        self.empty.setText("没有符合条件的素材。调整搜索或范围。" if self.search.text() else
                           ("回收站为空。" if self.scope.currentData() == "trash" else "还没有素材。拖入图片或点击「导入图片」。"))
        self.applied_filter = (self.search.text(), self.scope.currentData(), self.collection.currentData())
        self.count.setText(f"{total} 张 · 本页 {len(rows)} 张" + (f" · 第 {self.offset // self.PAGE_SIZE + 1} 页" if total else ""))
        self.previous.setEnabled(self.offset > 0 and not self.worker)
        self.next.setEnabled(self.offset + self.PAGE_SIZE < total and not self.worker)
        if not selection:
            self.current_id = None
            self.load_details(None)
        elif selected:
            self.current_id = selected
            self.load_details(selected)
        counts = self.store.counts()
        self.location.setText(f"本地素材库 · 原件 {counts['bytes'] / 1024**2:.1f} MiB · 待整理 {counts['inbox']} 张")
        self.location.setToolTip(str(self.store.root))
        self.save_button.setEnabled(bool(self.current_id and self.dirty and not self.worker))
        self.more_button.setEnabled(bool(self.current_id and not self.worker))
        self.reference_button.setEnabled(bool(self.current_id))
        self.remove_button.setEnabled(bool(self.current_id and not self.worker))

    def filter_changed(self):
        if self.closed or self.worker:
            return
        if not self.confirm_details():
            self.search.blockSignals(True)
            self.scope.blockSignals(True)
            self.collection.blockSignals(True)
            self.search.setText(self.applied_filter[0])
            self.scope.setCurrentIndex(self.scope.findData(self.applied_filter[1]))
            self.search.blockSignals(False)
            self.scope.blockSignals(False)
            self.collection.setCurrentIndex(max(0, self.collection.findData(self.applied_filter[2])))
            self.collection.blockSignals(False)
            return
        self.offset = 0
        self.refresh()

    def change_page(self, step):
        if self.confirm_details():
            self.offset = max(0, self.offset + step * self.PAGE_SIZE)
            self.refresh()

    def selection_changed(self, current, previous):
        if not self.confirm_details():
            self.list.blockSignals(True)
            self.list.setCurrentItem(previous)
            self.list.blockSignals(False)
            return
        self.current_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.load_details(self.current_id)

    def load_details(self, asset_id):
        self.loading = True
        self.dirty = False
        self.editor.setEnabled(bool(asset_id) and not self.worker)
        self.more_button.setEnabled(bool(asset_id) and not self.worker)
        self.reference_button.setEnabled(bool(asset_id))
        self.remove_button.setEnabled(bool(asset_id) and not self.worker)
        self.save_button.setEnabled(False)
        if not asset_id:
            for field in (self.title, self.tags, self.source):
                field.clear()
            self.notes.clear()
            self.reviewed.setChecked(False)
            self.preview.clear()
            self.preview.setText("选择图片查看预览")
            self.dimensions.clear()
            self.origin.clear()
            self.origin.setToolTip("")
        else:
            record = self.store.get(asset_id)
            self.title.setText(record["title"])
            self.tags.setText(", ".join(record["tags"]))
            self.source.setText(record["source"])
            self.notes.setPlainText(record["notes"])
            self.reviewed.setChecked(bool(record["reviewed"]))
            self.origin.setText("收集自剪贴板" if record["origin"] == "剪贴板" else "原始文件路径已保留（悬停查看）")
            self.origin.setToolTip(record["origin"])
            self.remove_button.setText("恢复素材" if record["deleted"] else "移到回收站")
            self.dimensions.setText(f"{record['width']} × {record['height']} px · {record['ext'].upper()} · {record['size'] / 1024:.0f} KiB")
            try:
                pixmap = load_preview(self.store.path_for(asset_id, True), 600)
                self.preview.setPixmap(pixmap.scaled(QSize(max(240, self.preview.width()), 115),
                                                    Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
            except (OSError, ValueError) as exc:
                self.preview.clear()
                self.preview.setText(str(exc))
        self.loading = False

    def save_details(self):
        if not self.current_id or self.worker:
            return False
        try:
            self.store.update(self.current_id, self.title.text(),
                              re.split("[,，]", self.tags.text()), self.source.text(),
                              self.notes.toPlainText(), self.reviewed.isChecked())
        except Exception as exc:
            self.status.setText("整理未保存：" + str(exc))
            return False
        self.dirty = False
        self.save_button.setEnabled(False)
        self.status.setText("整理已保存")
        self.feedback.emit("整理已保存")
        # Do not rebuild the list in currentItemChanged; preserve its live item pointers.
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == self.current_id:
                item.setText(self.title.text().strip() + ("" if self.reviewed.isChecked() else "  · 待整理"))
        return True

    def toggle_trash(self):
        if not self.current_id or not self.confirm_details():
            return
        asset_id = self.current_id
        try:
            deleted = not self.store.get(asset_id)["deleted"]
            self.store.set_deleted(asset_id, deleted)
            self.refresh()
            self.status.setText("已移到回收站，原件保留，可切换「回收站」恢复。" if deleted else "已恢复素材。")
        except Exception as exc:
            self.status.setText("操作未完成：" + str(exc))

    def open_reference(self):
        if not self.current_id:
            return
        try:
            record = self.store.get(self.current_id)
            pixmap = load_preview(self.store.path_for(self.current_id, True))
            if self.reference:
                self.reference.close()
                self.reference.deleteLater()
            self.reference = ReferenceWindow(record["title"], pixmap, self)
            self.reference.show()
        except Exception as exc:
            self.status.setText("无法打开参考：" + str(exc))

    def save_and_refresh(self):
        if self.save_details():
            self.refresh()

    def reload_collections(self, selected=None):
        chosen = self.collection.currentData() if selected is None else selected
        self.collection.blockSignals(True)
        self.collection.clear()
        self.collection.addItem("所有集合", None)
        for record in self.store.collections():
            self.collection.addItem(f"{record['name']} · {record['count']}", record["id"])
        self.collection.setCurrentIndex(max(0, self.collection.findData(chosen)))
        self.collection.blockSignals(False)

    def edit_collection(self, rename=False):
        if self.worker or not self.confirm_details():
            return
        identifier = self.collection.currentData() if rename else None
        if rename and not identifier:
            return
        current = next((c["name"] for c in self.store.collections() if c["id"] == identifier), "")
        name, accepted = QInputDialog.getText(self, "重命名集合" if rename else "新建集合",
                                             "集合名称，例如：音乐节海报、片头参考", text=current)
        if not accepted:
            return
        try:
            identifier = self.store.save_collection(name, identifier)
            self.reload_collections(identifier)
            self.offset = 0
            self.refresh()
            self.status.setText("集合已保存。在此集合内导入的图片会自动加入。")
        except Exception as exc:
            self.status.setText("集合未保存：" + str(exc))

    def remove_collection(self):
        identifier = self.collection.currentData()
        if not identifier or self.worker or not self.confirm_details():
            return
        answer = QMessageBox.question(self, "移除集合",
            "仅移除这个集合及其归类关系；图片仍保留在全部素材中。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_collection(identifier)
            self.reload_collections()
            self.refresh()
            self.status.setText("集合已移除，图片仍保留。")
        except Exception as exc:
            self.status.setText("集合未移除：" + str(exc))

    def organize_collections(self):
        if not self.current_id or self.worker or not self.confirm_details():
            return
        collections = self.store.collections()
        if not collections:
            self.status.setText("请先在「管理集合」中新建集合，再加入图片。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("整理图片所属集合")
        dialog.resize(400, 420)
        box = QVBoxLayout(dialog)
        box.addWidget(label("一张图片可以属于多个集合。取消勾选只移出集合，图片仍保留。"))
        choices = QListWidget()
        choices.setAccessibleName("图片所属集合")
        box.addWidget(choices)
        memberships = set(self.store.asset_collections(self.current_id))
        for record in collections:
            item = QListWidgetItem(record["name"])
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if record["id"] in memberships else Qt.CheckState.Unchecked)
            choices.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.store.set_collections(self.current_id, [
                choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count())
                if choices.item(i).checkState() == Qt.CheckState.Checked])
            self.reload_collections()
            self.refresh()
            self.status.setText("图片所属集合已保存。")
        except Exception as exc:
            self.status.setText("集合归类未保存：" + str(exc))

    def palette_model(self):
        if self.palette_provider:
            return self.palette_provider()
        if self.local_palette_model is None:
            from ..palette_model import PaletteModel
            self.local_palette_model = PaletteModel(self.data_root / "palettes.json", self)
        return self.local_palette_model

    def extract_palette(self):
        if not self.current_id or self.worker or not self.confirm_details():
            return
        try:
            model = self.palette_model()
            if model.store.read_only:
                raise ValueError(model.store.warning)
            if len(model.library["palettes"]) >= 100:
                raise ValueError("配色库已有 100 个色板，请先整理配色库")
            self.start_job("extract", self.current_id)
        except Exception as exc:
            self.status.setText("无法开始提色：" + str(exc))

    def create_palette_from_result(self, result):
        dialog = QDialog(self)
        dialog.setWindowTitle("从参考图创建色板")
        dialog.resize(460, 300)
        box = QVBoxLayout(dialog)
        box.addWidget(label("近似主色 · 保存后可从色板跳回来源图片", "section"))
        swatches = QHBoxLayout()
        for code in result["colors"]:
            chip = label(code)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            from ..design_core import contrast_ratio
            foreground = "#FFFFFF" if contrast_ratio(code, "#FFFFFF") >= 4.5 else "#203C31"
            chip.setStyleSheet(f"background:{code}; color:{foreground}; padding:12px 4px; border-radius:6px;")
            swatches.addWidget(chip)
        box.addLayout(swatches)
        box.addWidget(label("色板名称"))
        name = QLineEdit(result["source"]["title"][:80])
        name.setMaxLength(80)
        name.setAccessibleName("新色板名称")
        box.addWidget(name)
        box.addWidget(label("从预览图提取最多 6 个近似主色；透明区域可能忽略，不用于印刷校样。", "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存并打开色板")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        name.textChanged.connect(lambda value: buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(value.strip())))
        box.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.status.setText("已取消创建色板，素材保持不变。")
            return
        try:
            model = self.palette_model()
            if not model.add_from_asset(name.text().strip(), result["colors"], result["source"]):
                self.status.setText("色板未保存，请检查配色库状态或磁盘空间；素材仍保留。")
                return
            self.status.setText("已创建关联色板；来源图片和集合保持不变。")
            self.palette_requested.emit()
        except Exception as exc:
            self.status.setText("色板未保存：" + str(exc))

    def open_linked_palette(self):
        if not self.current_id or self.worker or not self.confirm_details():
            return
        try:
            model = self.palette_model()
            matches = model.source_palettes(self.store.library_id, self.current_id)
            if not matches:
                self.status.setText("这张图片尚无关联色板。可从「更多操作」选择「从图片创建色板」。")
                return
            chosen = matches[0][0]
            if len(matches) > 1:
                labels = [f"{index + 1}. {name}" for index, name in matches]
                value, accepted = QInputDialog.getItem(self, "选择关联色板", "色板", labels, 0, False)
                if not accepted:
                    return
                chosen = matches[labels.index(value)][0]
            if model.set_preferences(selected=chosen):
                self.palette_requested.emit()
            else:
                self.status.setText("无法打开色板：选择状态未保存。")
        except Exception as exc:
            self.status.setText("无法打开关联色板：" + str(exc))

    def show_source(self, source):
        if self.worker:
            raise ValueError("素材任务正在进行，结束后再查看来源")
        if source["library_id"] != self.store.library_id:
            raise ValueError("来源属于另一个素材库；颜色仍可使用，请先恢复对应图片库")
        record = self.store.get(source["asset_id"])
        if record["hash"] != source["hash"]:
            raise ValueError("来源图片标识不匹配，未跳转")
        if not self.confirm_details():
            return False
        self.search_timer.stop()
        for field in (self.search, self.scope, self.collection):
            field.blockSignals(True)
        self.search.clear()
        self.scope.setCurrentIndex(self.scope.findData("trash" if record["deleted"] else "all"))
        self.collection.setCurrentIndex(0)
        for field in (self.search, self.scope, self.collection):
            field.blockSignals(False)
        rows, _ = self.store.list_assets(scope=self.scope.currentData(), limit=10000)
        position = next(i for i, row in enumerate(rows) if row["id"] == record["id"])
        self.offset = position // self.PAGE_SIZE * self.PAGE_SIZE
        self.refresh(selected=record["id"])
        return True

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "导入图片", "", "图片 (*.png *.jpg *.jpeg)")
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        if self.worker or not self.confirm_details():
            return
        if not paths or len(paths) > MAX_BATCH:
            self.status.setText("每次请选择 1–100 张 PNG / JPEG 图片。")
            return
        try:
            estimate = sum(Path(path).stat().st_size for path in paths if Path(path).is_file())
        except OSError as exc:
            self.status.setText("无法读取导入文件：" + str(exc))
            return
        result = QMessageBox.question(self, "收集图片",
            f"将 {len(paths)} 个文件复制到本地素材库，预计原件占用 {estimate / 1024**2:.1f} MiB。\n"
            "相同原件共用存储，每次收集各保留一条记录。损坏或不支持的文件会列出原因。\n\n"
            + str(self.store.root), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes)
        if result == QMessageBox.StandardButton.Yes:
            self.start_job("import", [str(path) for path in paths])

    def paste_image(self):
        if self.worker or not self.confirm_details():
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            self.status.setText("剪贴板中没有图片。请先复制图片，再点击「粘贴图片」。")
            return
        if image.width() * image.height() > MAX_PIXELS:
            self.status.setText("剪贴板图片超过 4000 万像素。")
            return
        self.start_job("clipboard", image.copy())

    def backup(self):
        if self.worker or not self.confirm_details():
            return
        path, _ = QFileDialog.getSaveFileName(self, "备份素材库", "素材库备份.zip", "ZIP (*.zip)")
        if path:
            destination = Path(path)
            if destination.suffix.lower() != ".zip":
                destination = destination.with_name(destination.name + ".zip")
                if destination.exists() and QMessageBox.question(self, "替换备份", "同名 ZIP 已存在，是否替换？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                    return
            self.start_job("backup", destination)

    def restore_backup(self):
        if self.worker or not self.confirm_details():
            return
        path, _ = QFileDialog.getOpenFileName(self, "恢复素材库备份", "", "ZIP (*.zip)")
        if not path:
            return
        result = QMessageBox.question(self, "恢复为独立素材库",
            "将先校验备份，恢复到新目录，成功后切换到恢复的素材库。\n"
            "当前素材库目录保留；此操作不会合并两个库，也不包含字体和配色数据。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if result == QMessageBox.StandardButton.Yes:
            destination = self.data_root / ("assets-restored-" + uuid.uuid4().hex)
            self.start_job("restore", (Path(path), destination))

    def start_job(self, kind, payload):
        if self.worker:
            return
        self.search_timer.stop()
        self.import_collection = self.collection.currentData() if kind in ("import", "clipboard") else None
        self.worker = AssetJob(self.store.root, kind, payload, self)
        self.worker.progress.connect(self.job_progress)
        self.worker.finished.connect(self.job_finished)
        self.errors.clear()
        self.errors.hide()
        self.status.setText("正在准备任务…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        for widget in (self.import_button, self.paste_button, self.backup_button, self.restore_backup_button,
                       self.editor, self.save_button, self.remove_button, self.list, self.search, self.scope,
                       self.previous, self.next, self.collection, self.manage_collections, self.more_button):
            widget.setEnabled(False)
        self.worker.start()

    def job_progress(self, done, total, message):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status.setText(f"{message} · {done}/{total}")

    def cancel_job(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消，已完成的素材会保留…")

    def activate_restored(self, path):
        replacement = AssetStore(path)
        fd, name = tempfile.mkstemp(dir=self.data_root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump({"schema": 1, "directory": path.name}, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.location_file)
        except Exception:
            replacement.close()
            raise
        finally:
            Path(name).unlink(missing_ok=True)
        self.store.close()
        self.store = replacement
        self.reload_collections()
        self.current_id = None
        self.offset = 0
        if self.reference:
            self.reference.close()
            self.reference.deleteLater()
            self.reference = None

    def job_finished(self):
        job = self.worker
        result = job.result
        self.worker = None
        job.deleteLater()
        for widget in (self.import_button, self.paste_button, self.backup_button, self.restore_backup_button,
                       self.list, self.search, self.scope, self.collection, self.manage_collections):
            widget.setEnabled(True)
        self.progress.hide()
        self.cancel_button.hide()
        kind, state = result["kind"], result["state"]
        if kind == "restore" and state == "success":
            try:
                self.activate_restored(Path(result["path"]))
            except Exception as exc:
                result["errors"].append("备份已恢复但未切换：" + str(exc))
                state = "failed"
        if kind in ("import", "clipboard"):
            self.status.setText(f"{'已取消' if state == 'cancelled' else '收集完成'} · 新增 {len(result['ids'])} 条记录 · "
                                f"共用原件 {result['duplicates']} 张 · 失败 {len(result['errors'])} 项")
        else:
            self.status.setText(("备份已保存：" if kind == "backup" else "已切换到恢复的素材库：") +
                                result.get("path", "") if state == "success" else
                                ("任务已取消，原素材库保留。" if state == "cancelled" else "任务未完成，原素材库保留。"))
        if self.import_collection and result["ids"]:
            for asset_id in result["ids"]:
                try:
                    self.store.set_collections(asset_id, [self.import_collection])
                except Exception as exc:
                    result["errors"].append("图片已入库，但未加入集合：" + str(exc))
            self.import_collection = None
        self.reload_collections()
        if kind == "extract":
            if state == "success" and not self.exit_after_job:
                self.create_palette_from_result(result)
            else:
                self.status.setText("提色已取消。" if state == "cancelled" else "提色未完成，请查看原因。")
        self.errors.setPlainText("\n".join(result["errors"]))
        self.errors.setVisible(bool(result["errors"]))
        self.refresh(selected=result["ids"][0] if result["ids"] else None)
        if self.current_id:
            self.editor.setEnabled(True)
        if self.exit_after_job:
            self.exit_after_job = False
            self.window().quit_app()

    def can_exit(self):
        if self.worker:
            result = QMessageBox.question(self, "任务尚未结束", "取消当前素材任务并在处理结束后退出？已完成的素材会保留。",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                          QMessageBox.StandardButton.Cancel)
            if result == QMessageBox.StandardButton.Yes:
                self.exit_after_job = True
                self.cancel_job()
            return False
        return self.confirm_details()

    def shutdown(self):
        self.closed = True
        self.search_timer.stop()
        if self.reference:
            self.reference.close()
        self.store.close()

    def dragEnterEvent(self, event):
        if not self.worker and event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.import_paths(paths)
