"""Image inbox, metadata editor and floating reference viewer."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImageReader, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QComboBox, QCheckBox, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QFileDialog, QMessageBox, QFormLayout,
    QProgressBar, QDialog, QScrollArea, QSizePolicy,
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
    PAGE_SIZE = 60

    def __init__(self, data_root: Path):
        super().__init__()
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
        self.applied_filter = ("", "all")
        self.exit_after_job = False
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label("把参考收好，创作时找得到。", "title"))
        layout.addWidget(label("拖入 PNG / JPEG，或主动粘贴图片。先收集，之后再整理。", "muted"))
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
        self.preview.setMinimumHeight(115)
        self.preview.setMaximumHeight(190)
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
        self.save_button = button("保存整理", self.save_details, True)
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
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.addWidget(scroll, 1)
        right_box.addLayout(actions)
        right_box.addWidget(self.remove_button)
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
        self.status = label("图片仅保存在本机；移到回收站后仍可恢复。", "muted")
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
        rows, total = self.store.list_assets(self.search.text(), self.scope.currentData(), self.offset, self.PAGE_SIZE)
        if not rows and self.offset:
            self.offset = 0
            rows, total = self.store.list_assets(self.search.text(), self.scope.currentData(), 0, self.PAGE_SIZE)
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
        self.applied_filter = (self.search.text(), self.scope.currentData())
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
        self.reference_button.setEnabled(bool(self.current_id))
        self.remove_button.setEnabled(bool(self.current_id and not self.worker))

    def filter_changed(self):
        if self.closed or self.worker:
            return
        if not self.confirm_details():
            self.search.blockSignals(True)
            self.scope.blockSignals(True)
            self.search.setText(self.applied_filter[0])
            self.scope.setCurrentIndex(self.scope.findData(self.applied_filter[1]))
            self.search.blockSignals(False)
            self.scope.blockSignals(False)
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
                self.preview.setPixmap(pixmap.scaled(QSize(max(240, self.preview.width()), 185),
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
        self.status.setText("名称、标签、来源与备注已保存。")
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
                       self.previous, self.next):
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
                       self.list, self.search, self.scope):
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
