"""Project specification editor, independent copies and reference inspection."""
from copy import deepcopy
from pathlib import Path
import sqlite3

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)
from .projects import (ProjectStore, SCENES, FIELDS, new_project, palette_copy,
                       font_copy, image_reference, resolve_image, export_project)
from .theme import icon


def label(value, name=""):
    widget = QLabel(value)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(value, callback, primary=False):
    widget = QPushButton(value)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class ResourcePicker(QDialog):
    def __init__(self, title, rows, parent):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 430)
        self.rows, self.value = rows, None
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setAccessibleName("搜索可选资源")
        self.search.setPlaceholderText("输入名称筛选")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setAccessibleName(title)
        layout.addWidget(self.list, 1)
        self.status = label("", "muted")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.choose)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.list.itemActivated.connect(self.choose)
        self.search.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.list.clear()
        words = self.search.text().casefold().split()
        for title, value in self.rows:
            if all(word in title.casefold() for word in words):
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, value)
                self.list.addItem(item)
        self.status.setText(f"{self.list.count()} 项可选资源" if self.list.count() else "暂无匹配资源。请调整关键词或先在资源库添加资料。")
        if self.list.count():
            self.list.setCurrentRow(0)

    def choose(self, *_):
        if self.list.currentItem():
            self.value = self.list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.accept()


class ProjectPage(QWidget):
    feedback = Signal(str)
    image_requested = Signal(dict)

    def __init__(self, root):
        super().__init__()
        self.root = Path(root)
        self.store = ProjectStore(root)
        self.current = None
        self.dirty = False
        self.loading = False
        self.resources = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(label("项目", "title"))
        heading.addStretch()
        self.new_button = button("新建项目", self.create_project, True)
        heading.addWidget(self.new_button)
        layout.addLayout(heading)
        layout.addWidget(label("记录项目规格，关联参考资料，导出项目说明。", "muted"))
        self.warning = label(self.store.warning, "muted")
        self.warning.setVisible(bool(self.store.warning))
        layout.addWidget(self.warning)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 10, 0)
        self.search = QLineEdit()
        self.search.setAccessibleName("搜索项目名称、客户与规格")
        self.search.setPlaceholderText("搜索项目")
        self.search.setClearButtonEnabled(True)
        column.addWidget(self.search)
        self.scope = QComboBox()
        self.scope.setAccessibleName("项目状态筛选")
        self.scope.addItem("进行中的项目", False)
        self.scope.addItem("已归档项目", True)
        column.addWidget(self.scope)
        self.list = QListWidget()
        self.list.setAccessibleName("项目列表")
        column.addWidget(self.list, 1)
        self.count = label("", "muted")
        column.addWidget(self.count)
        self.duplicate_button = button("复制项目", self.duplicate_project)
        column.addWidget(self.duplicate_button)
        splitter.addWidget(left)
        self.right = QWidget()
        detail = QVBoxLayout(self.right)
        detail.setContentsMargins(10, 0, 0, 0)
        self.project_title = label("未选择项目", "section")
        detail.addWidget(self.project_title)
        self.empty = label("创建项目规格卡，集中记录规格、参考图片、配色与字体候选。\n新建项目仅需填写名称，其他信息均可选填。", "muted")
        detail.addWidget(self.empty)
        self.tabs = QTabWidget()
        detail.addWidget(self.tabs, 1)
        specs = QWidget()
        spec_layout = QVBoxLayout(specs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        spec_layout.addWidget(scroll)
        form_widget = QWidget()
        self.form = QFormLayout(form_widget)
        self.form.setSpacing(12)
        scroll.setWidget(form_widget)
        self.name = self.field("项目名称 *", "name", 120)
        self.scene = QComboBox()
        self.scene.setAccessibleName("项目类型")
        for key, (name, _) in SCENES.items():
            self.scene.addItem(name, key)
        self.form.addRow("项目类型", self.scene)
        self.client = self.field("客户 / 委托方", "client", 200)
        self.due = self.field("截止日期", "due", 10)
        self.due.setPlaceholderText("YYYY-MM-DD（可选）")
        self.directory = QLineEdit()
        self.directory.setMaxLength(2000)
        self.directory.setAccessibleName("项目目录")
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory, 1)
        directory_row.addWidget(button("选择", self.choose_directory))
        directory_row.addWidget(button("打开", self.open_directory))
        self.form.addRow("项目目录", directory_row)
        self.spec_fields = {}
        for key, title in FIELDS.items():
            widget = self.field(title, key, 500)
            self.spec_fields[key] = widget
        self.delivery = QPlainTextEdit()
        self.delivery.setAccessibleName("交付要求")
        self.delivery.setPlaceholderText("文件格式、命名规范、交付清单等（可选）")
        self.delivery.setMaximumHeight(100)
        self.form.addRow("交付要求", self.delivery)
        self.notes = QPlainTextEdit()
        self.notes.setAccessibleName("项目备注")
        self.notes.setMaximumHeight(100)
        self.form.addRow("项目备注", self.notes)
        self.form.addRow(label("规格为手动填写的项目要求，不读取宿主工程内容。", "muted"))
        self.tabs.addTab(specs, "项目规格")

        resources = QWidget()
        resource_layout = QVBoxLayout(resources)
        resource_layout.addWidget(label("图片使用素材库引用；配色与字体候选保存为项目独立副本。", "muted"))
        actions = QHBoxLayout()
        for title, callback in (("关联图片", self.add_image), ("添加配色副本", self.add_palette), ("添加字体候选", self.add_font)):
            actions.addWidget(button(title, callback))
        resource_layout.addLayout(actions)
        self.resource_list = QListWidget()
        self.resource_list.setAccessibleName("项目资源列表")
        resource_layout.addWidget(self.resource_list, 1)
        self.swatches = QWidget()
        self.swatch_layout = QHBoxLayout(self.swatches)
        self.swatch_layout.setContentsMargins(0, 0, 0, 0)
        self.swatch_layout.setSpacing(5)
        resource_layout.addWidget(self.swatches)
        self.resource_detail = label("选择资源查看详情。", "muted")
        self.resource_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        resource_layout.addWidget(self.resource_detail)
        resource_actions = QHBoxLayout()
        self.inspect_button = button("查看 / 编辑", self.inspect_resource)
        self.copy_button = button("复制资源内容", self.copy_resource)
        self.remove_button = button("移出项目", self.remove_resource)
        for widget in (self.inspect_button, self.copy_button, self.remove_button):
            resource_actions.addWidget(widget)
        resource_layout.addLayout(resource_actions)
        self.tabs.addTab(resources, "项目资源")
        footer = QHBoxLayout()
        self.status = label("请选择项目，或新建项目规格卡。", "muted")
        detail.addWidget(self.status)
        self.archive_button = button("归档项目", self.archive_project)
        self.export_button = button("导出说明", self.export)
        self.save_button = button("保存项目", self.save, True)
        for widget in (self.archive_button, self.export_button, self.save_button):
            footer.addWidget(widget)
        detail.addLayout(footer)
        splitter.addWidget(self.right)
        splitter.setSizes([230, 680])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        self.search.textChanged.connect(self.refresh_list)
        self.scope.currentIndexChanged.connect(self.refresh_list)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.scene.currentIndexChanged.connect(self.scene_changed)
        for widget in (self.name, self.client, self.due, self.directory, *self.spec_fields.values()):
            widget.textChanged.connect(self.mark_dirty)
        self.delivery.textChanged.connect(self.mark_dirty)
        self.notes.textChanged.connect(self.mark_dirty)
        self.resource_list.currentRowChanged.connect(self.resource_selected)
        self.resource_list.itemActivated.connect(self.inspect_resource)
        self.new_button.setEnabled(not self.store.read_only)
        self.refresh_list()
        self.set_editor_enabled()

    def field(self, title, key, maximum):
        widget = QLineEdit()
        widget.setMaxLength(maximum)
        widget.setAccessibleName(title)
        self.form.addRow(title, widget)
        return widget

    def set_editor_enabled(self):
        enabled = self.current is not None and not self.store.read_only
        self.empty.setVisible(self.current is None)
        self.tabs.setVisible(self.current is not None)
        self.tabs.setEnabled(enabled)
        for widget in (self.save_button, self.export_button, self.archive_button, self.duplicate_button):
            widget.setEnabled(enabled)

    def scene_changed(self):
        labels = dict(SCENES[self.scene.currentData()][1])
        for key, widget in self.spec_fields.items():
            self.form.setRowVisible(widget, key in labels)
            self.form.labelForField(widget).setText(labels.get(key, FIELDS[key]))
        self.mark_dirty()

    def mark_dirty(self, *_):
        if self.current is not None and not self.loading:
            self.dirty = True
            self.status.setText("项目包含未保存的修改。")

    def refresh_list(self, *_):
        self.list.blockSignals(True)
        self.list.clear()
        try:
            projects = self.store.list() if not self.store.read_only else []
            words = self.search.text().casefold().split()
            for p in projects:
                haystack = " ".join([p["name"], p["client"], *p["specs"].values()]).casefold()
                if p["archived"] != self.scope.currentData() or not all(word in haystack for word in words):
                    continue
                item = QListWidgetItem(p["name"] + "\n" + SCENES[p["scene"]][0])
                item.setData(Qt.ItemDataRole.UserRole, p["id"])
                self.list.addItem(item)
                if self.current and p["id"] == self.current["id"]:
                    self.list.setCurrentItem(item)
            self.count.setText(f"{self.list.count()} 个项目" if self.list.count() else "暂无匹配项目。")
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.status.setText(str(exc))
        finally:
            self.list.blockSignals(False)

    def selection_changed(self, item, previous):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.current and key == self.current["id"]:
            return
        if not self.confirm_details():
            self.refresh_list()
            return
        self.open_project(key, confirm=False)

    def open_project(self, key, confirm=True):
        if confirm and not self.confirm_details():
            return False
        try:
            project = self.store.get(key)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.status.setText(str(exc))
            return False
        self.load(project)
        return True

    def load(self, project):
        self.loading = True
        self.current = deepcopy(project)
        for key in ("name", "client", "due", "directory"):
            getattr(self, key).setText(project[key])
        self.scene.setCurrentIndex(self.scene.findData(project["scene"]))
        self.scene_changed()
        for key, widget in self.spec_fields.items():
            widget.setText(project["specs"].get(key, ""))
        self.delivery.setPlainText(project["delivery"])
        self.notes.setPlainText(project["notes"])
        self.resources = deepcopy(project["resources"])
        self.refresh_resources()
        self.project_title.setText(project["name"])
        self.archive_button.setText("恢复项目" if project["archived"] else "归档项目")
        self.scope.setCurrentIndex(int(project["archived"]))
        self.loading = False
        self.dirty = False
        self.status.setText(f"已保存 · 修订 {project['revision']}")
        self.set_editor_enabled()
        self.refresh_list()

    def candidate(self):
        p = deepcopy(self.current)
        for key in ("name", "client", "due", "directory"):
            p[key] = getattr(self, key).text().strip()
        p.update(scene=self.scene.currentData(), specs={key: widget.text().strip() for key, widget in self.spec_fields.items() if widget.text().strip()},
                 delivery=self.delivery.toPlainText(), notes=self.notes.toPlainText(), resources=deepcopy(self.resources))
        return p

    def save(self, *_):
        if self.current is None:
            return False
        try:
            saved = self.store.save(self.candidate())
        except (ValueError, OSError, sqlite3.Error, TypeError) as exc:
            self.status.setText("项目未保存：" + str(exc))
            return False
        self.load(saved)
        self.feedback.emit("项目已保存")
        return True

    def confirm_details(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "保存项目修改", "当前项目包含未保存的修改。是否保存？",
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        if answer == QMessageBox.StandardButton.Discard:
            self.load(self.current)
            return True
        return False

    def create_project(self):
        if not self.confirm_details():
            return
        name, accepted = QInputDialog.getText(self, "新建项目", "项目名称")
        if accepted:
            try:
                self.search.clear()
                self.load(self.store.save(new_project(name)))
                self.name.setFocus()
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.status.setText("项目未创建：" + str(exc))

    def duplicate_project(self):
        if not self.current or not self.confirm_details():
            return
        name, accepted = QInputDialog.getText(self, "复制项目", "新项目名称", text=self.current["name"] + " · 副本")
        if accepted:
            try:
                self.search.clear()
                self.load(self.store.duplicate(self.current["id"], name))
                self.feedback.emit("已创建独立项目副本")
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.status.setText(str(exc))

    def archive_project(self):
        if not self.current or not self.confirm_details():
            return
        p = deepcopy(self.current)
        p["archived"] = not p["archived"]
        try:
            self.load(self.store.save(p))
            self.feedback.emit("项目已归档" if p["archived"] else "项目已恢复")
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.status.setText(str(exc))

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目目录", self.directory.text())
        if path:
            self.directory.setText(path)

    def open_directory(self):
        path = Path(self.directory.text()).expanduser()
        if not self.directory.text().strip() or not path.is_dir():
            self.status.setText("项目目录不存在，请重新选择。")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.status.setText("项目目录未能打开。")

    def add_resource(self, item):
        if len(self.resources) >= 100:
            self.status.setText("每个项目最多保存 100 项资源。")
            return
        if item["kind"] == "image" and any(r["kind"] == "image" and (r["library_id"], r["asset_id"]) ==
                                                   (item["library_id"], item["asset_id"]) for r in self.resources):
            self.status.setText("该图片已关联到当前项目。")
            return
        self.resources.append(deepcopy(item))
        self.refresh_resources()
        self.resource_list.setCurrentRow(len(self.resources) - 1)
        self.mark_dirty()

    def add_image(self):
        from .assets.library import AssetStore
        from .resources_search import asset_root
        try:
            path = asset_root(self.root)
            if not (path / "library.sqlite3").exists():
                self.status.setText("素材库为空。请先在图片素材页导入图片。")
                return
            store = AssetStore.open_readonly(path)
            try:
                assets, _ = store.list_assets(limit=10000)
                rows = [(p["title"], image_reference(store.library_id, p)) for p in assets]
            finally:
                store.close()
            picker = ResourcePicker("关联参考图片", rows, self)
            if picker.exec():
                self.add_resource(picker.value)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.status.setText("图片资料未载入：" + str(exc))

    def add_palette(self):
        from .design_core import PaletteStore, default_library
        try:
            path = self.root / "palettes.json"
            library = PaletteStore.read(path) if path.exists() else default_library()
            picker = ResourcePicker("添加项目配色副本", [(p["name"], palette_copy(p)) for p in library["palettes"]], self)
            if picker.exec():
                self.add_resource(picker.value)
        except (ValueError, OSError) as exc:
            self.status.setText("配色资料未载入：" + str(exc))

    def add_font(self):
        from .fonts.library import read_file
        try:
            families = set(QFontDatabase.families())
            path = self.root / "fonts.json"
            records = read_file(path)["fonts"] if path.exists() else {}
            families.update(records)
            picker = ResourcePicker("添加字体候选", [(name, name) for name in sorted(families, key=str.casefold)], self)
            if picker.exec():
                family = picker.value
                styles = QFontDatabase.styles(family) or ["Regular"]
                style, accepted = QInputDialog.getItem(self, "字体样式", "选择样式", styles, editable=False)
                if accepted:
                    self.add_resource(font_copy(family, style, records.get(family, {}).get("note", "")))
        except (ValueError, OSError) as exc:
            self.status.setText("字体资料未载入：" + str(exc))

    def refresh_resources(self):
        self.resource_list.clear()
        for r in self.resources:
            if r["kind"] == "image":
                title, suffix, image = r["title"], "图片引用", "assets"
            elif r["kind"] == "palette":
                title, suffix, image = r["name"], f"独立配色 · {len(r['colors'])} 色", "palettes"
            else:
                title, suffix, image = r["family"], "字体候选 · " + r["style"], "fonts"
            self.resource_list.addItem(QListWidgetItem(icon(image), title + "\n" + suffix))
        self.resource_selected(-1)

    def selected_resource(self):
        index = self.resource_list.currentRow()
        return self.resources[index] if 0 <= index < len(self.resources) else None

    def resource_selected(self, *_):
        r = self.selected_resource()
        while self.swatch_layout.count():
            item = self.swatch_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.swatches.setVisible(bool(r and r["kind"] == "palette"))
        for widget in (self.inspect_button, self.copy_button, self.remove_button):
            widget.setEnabled(r is not None)
        if not r:
            self.resource_detail.setText("选择资源查看详情。" if self.resources else "暂无关联资源。可添加参考图片、配色副本或字体候选。")
        elif r["kind"] == "palette":
            for color in r["colors"][:12]:
                chip = QPushButton()
                chip.setMinimumSize(20, 32)
                chip.setToolTip(color["name"] + " · " + color["hex"])
                chip.setAccessibleName("复制色号 " + color["hex"])
                chip.setStyleSheet(f"background: {color['hex']}; border: 1px solid #BBC3D1; border-radius: 6px;")
                chip.clicked.connect(lambda checked=False, code=color["hex"]: self.copy_color(code))
                self.swatch_layout.addWidget(chip, 1)
            self.resource_detail.setText("项目独立副本 · " + "  ".join(c["hex"] for c in r["colors"][:12]))
        elif r["kind"] == "font":
            available = r["family"] in QFontDatabase.families() and r["style"] in QFontDatabase.styles(r["family"])
            self.resource_detail.setText(("本机字体与样式可用。" if available else "本机缺少指定字体或样式，候选记录已保留。") + " 不包含字体文件或授权证明。")
        else:
            try:
                asset, _ = resolve_image(self.root, r)
                self.resource_detail.setText("图片可用 · " + asset["title"] + " · 移出项目不会删除原素材。")
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.resource_detail.setText("图片引用不可用：" + str(exc))

    def inspect_resource(self, *_):
        r = self.selected_resource()
        if r is None:
            return
        if r["kind"] == "image":
            try:
                asset, _ = resolve_image(self.root, r)
                self.image_requested.emit(dict(library_id=r["library_id"], asset_id=r["asset_id"], hash=r["hash"], title=asset["title"]))
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.status.setText(str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑项目配色副本" if r["kind"] == "palette" else "字体候选详情")
        dialog.resize(500, 380)
        layout = QVBoxLayout(dialog)
        name = QLineEdit(r.get("name", r.get("family", "")))
        name.setAccessibleName("配色名称" if r["kind"] == "palette" else "字体家族")
        name.setReadOnly(r["kind"] == "font")
        layout.addWidget(name)
        layout.addWidget(label("每行一个颜色，格式为「#HEX 颜色名称」。修改仅影响当前项目。" if r["kind"] == "palette" else "记录字体用途与排版要求；不修改系统字体。", "muted"))
        content = QPlainTextEdit()
        content.setAccessibleName("项目配色内容" if r["kind"] == "palette" else "字体备注")
        content.setPlainText("\n".join(c["hex"] + " " + c["name"] for c in r["colors"]) if r["kind"] == "palette" else r["note"])
        layout.addWidget(content, 1)
        error = label("", "muted")
        layout.addWidget(error)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("应用修改")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        layout.addWidget(actions)
        def apply():
            from .projects import validate
            candidate = deepcopy(r)
            if r["kind"] == "palette":
                candidate["name"] = name.text().strip()
                candidate["colors"] = []
                for line in content.toPlainText().splitlines():
                    if line.strip():
                        parts = line.strip().split(maxsplit=1)
                        candidate["colors"].append(dict(hex=parts[0], name=parts[1] if len(parts) > 1 else ""))
            else:
                candidate["note"] = content.toPlainText()
            try:
                check = self.candidate()
                check["resources"][self.resource_list.currentRow()] = candidate
                candidate = validate(check)["resources"][self.resource_list.currentRow()]
            except (ValueError, TypeError) as exc:
                error.setText(str(exc))
                return
            index = self.resource_list.currentRow()
            self.resources[index] = candidate
            self.refresh_resources()
            self.resource_list.setCurrentRow(index)
            self.mark_dirty()
            dialog.accept()
        actions.accepted.connect(apply)
        actions.rejected.connect(dialog.reject)
        dialog.exec()

    def copy_resource(self):
        r = self.selected_resource()
        if r is None:
            return
        value = "\n".join(c["hex"] for c in r["colors"]) if r["kind"] == "palette" else r.get("family", r.get("title", ""))
        QApplication.clipboard().setText(value)
        self.feedback.emit("资源内容已复制")

    def copy_color(self, code):
        QApplication.clipboard().setText(code)
        self.feedback.emit("色号已复制：" + code)

    def remove_resource(self):
        index = self.resource_list.currentRow()
        if 0 <= index < len(self.resources):
            self.resources.pop(index)
            self.refresh_resources()
            self.mark_dirty()

    def export(self):
        if not self.current or not self.confirm_details():
            return
        output, _ = QFileDialog.getSaveFileName(self, "导出项目说明", "项目说明.md", "Markdown 文档 (*.md)")
        if not output:
            return
        if not Path(output).suffix:
            output += ".md"
            if Path(output).exists():
                self.status.setText("文件已存在，请选择其他导出名称。")
                return
        try:
            export_project(self.current, self.root, output)
            self.status.setText("项目说明已导出：" + output)
            self.feedback.emit("项目说明已导出")
        except (ValueError, OSError) as exc:
            self.status.setText("导出未完成：" + str(exc))
