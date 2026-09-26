"""Resource search and modal backup UI, using the shared design language."""
from pathlib import Path
from threading import Event
import uuid
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QFileDialog, QMessageBox,
    QDialog, QProgressBar)
from .resources_search import search_resources
from .workspace_backup import export_workspace, restore_workspace, activate_workspace
from .assets.library import Cancelled


class SearchJob(QThread):
    def __init__(self, root, query, kind, parent):
        super().__init__(parent)
        self.root, self.query, self.kind = root, query, kind
        self.result = ([], [], {})
    def run(self):
        self.result = search_resources(self.root, self.query, self.kind)


class ResourceSearch(QWidget):
    open_requested = Signal(object)
    backup_requested = Signal(bool)
    query_active = Signal(bool)
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root, self.worker = root, None
        self.revision = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索图片、色板、字体整理记录')
        self.search.setAccessibleName('搜索个人资料')
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(300)
        row.addWidget(self.search, 1)
        self.kind = QComboBox()
        self.kind.setAccessibleName('资源类型')
        for title, key in [('全部资料', 'all'), ('图片', 'assets'), ('色板', 'palettes'), ('字体', 'fonts')]:
            self.kind.addItem(title, key)
        row.addWidget(self.kind)
        layout.addLayout(row)
        actions = QHBoxLayout()
        for title, restore in [('完整备份', False), ('恢复备份', True)]:
            action = QPushButton(title)
            action.clicked.connect(lambda checked=False, r=restore: self.backup_requested.emit(r))
            actions.addWidget(action)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QLabel('输入关键词查找已保存的资料；字体按名称、分组、标签和备注搜索。')
        self.status.setObjectName('muted')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QListWidget()
        self.results.setAccessibleName('资源搜索结果，双击或按回车打开')
        self.results.setMinimumHeight(180)
        self.results.hide()
        self.results.itemActivated.connect(lambda item: self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.results, 1)
        self.open_button = QPushButton('打开选中资料')
        self.open_button.clicked.connect(self.open_current)
        self.open_button.hide()
        layout.addWidget(self.open_button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(220)
        self.timer.timeout.connect(self.start_search)
        self.search.textChanged.connect(self.refresh)
        self.kind.currentIndexChanged.connect(self.refresh)

    def open_current(self):
        if self.results.currentItem():
            self.open_requested.emit(self.results.currentItem().data(Qt.ItemDataRole.UserRole))

    def refresh(self, *_):
        self.revision += 1
        self.results.clear()
        visible = bool(self.search.text().strip())
        self.query_active.emit(visible)
        self.results.setVisible(visible)
        self.open_button.setVisible(visible)
        self.open_button.setEnabled(False)
        self.status.setText('正在查找…' if visible else '输入关键词查找已保存的资料；字体按名称、分组、标签和备注搜索。')
        self.timer.start()

    def start_search(self):
        if self.worker or not self.search.text().strip():
            return
        self.worker = SearchJob(self.root, self.search.text(), self.kind.currentData(), self)
        self.worker.revision = self.revision
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        worker, self.worker = self.worker, None
        if worker.revision != self.revision:
            worker.deleteLater()
            self.start_search()
            return
        results, warnings, counts = worker.result
        worker.deleteLater()
        titles = {'assets': '图片', 'palettes': '色板', 'fonts': '字体'}
        for result in results:
            detail = ' '.join(result['details'].split())[:100]
            item = QListWidgetItem(f"{titles[result['kind']]} · {result['title']}\n{detail or '已保存的资料'}")
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.results.addItem(item)
        total = sum(counts.values())
        message = f'找到 {total} 条资料' if total else '没有找到，试试名称、标签或色号。'
        if total > len(results):
            message += ' · 每类显示前 100 条，请缩小搜索范围'
        self.status.setText(message + ('\n' + '\n'.join(warnings) if warnings else ''))
        if results:
            self.results.setCurrentRow(0)
        self.open_button.setEnabled(bool(results))

    def shutdown(self):
        self.timer.stop()
        if self.worker:
            self.worker.wait()


class BackupJob(QThread):
    progress = Signal(int, int)
    def __init__(self, root, archive, destination=None, parent=None):
        super().__init__(parent)
        self.root, self.archive, self.destination = root, archive, destination
        self.cancel = Event()
        self.error, self.success = '', False
    def run(self):
        try:
            if self.destination:
                restore_workspace(self.archive, self.destination, self.cancel, self.progress.emit)
            else:
                export_workspace(self.root, self.archive, self.cancel, self.progress.emit)
            self.success = True
        except Cancelled:
            self.error = '已取消，现有资料保持不变。'
        except Exception as exc:
            self.error = '未完成：' + str(exc)


class BackupProgress(QDialog):
    def __init__(self, job, parent):
        super().__init__(parent)
        self.job = job
        self.setWindowTitle('恢复完整备份' if job.destination else '创建完整备份')
        self.setMinimumWidth(420)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        layout = QVBoxLayout(self)
        self.status = QLabel('正在校验并处理资料，请稍候…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.cancel_button = QPushButton('取消')
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        job.progress.connect(self.progress)
        job.finished.connect(self.accept)
    def progress(self, done, total):
        self.status.setText(f'正在处理图片资料 · {done} / {total}')
    def reject(self):
        if self.job.isRunning():
            self.job.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('正在取消，请稍候…')
        else:
            super().reject()


def run_backup(window, restore=False):
    if getattr(window, 'backup_busy', False):
        return
    assets = window.tool_pages.get('assets')
    if assets and assets.worker:
        QMessageBox.information(window, '素材正在处理', '请等待当前素材任务结束，再备份或恢复。')
        return
    if assets and not assets.confirm_details():
        return
    fonts = window.tool_pages.get('fonts')
    if fonts and not restore and not fonts.flush_preferences():
        QMessageBox.warning(window, '字体设置未保存', '请先处理字体页的保存问题，再创建完整备份。')
        return
    if restore:
        archive, _ = QFileDialog.getOpenFileName(window, '选择完整备份', '', '工具箱完整备份 (*.ctbackup)')
    else:
        archive, _ = QFileDialog.getSaveFileName(window, '保存完整备份', 'CreativeToolbox.ctbackup', '工具箱完整备份 (*.ctbackup)')
    if not archive:
        return
    base = getattr(window, 'launch_root', window.store.root)
    destination = Path(base) / ('workspace-restored-' + uuid.uuid4().hex) if restore else None
    if not restore and not Path(archive).suffix:
        archive += '.ctbackup'
        if Path(archive).exists():
            QMessageBox.warning(window, '文件已存在', '请选择另一个备份名称。')
            return
    if QMessageBox.question(window, '恢复资料' if restore else '备份已保存的资料',
        '备份将在新目录中恢复并校验，完成后可切换使用。现有资料会保留。' if restore else
        '包含图片原件、集合、色板、字体整理和已保存设置；不含系统字体文件、未保存编辑及活动日志。处理期间暂停编辑。',
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Ok) != QMessageBox.StandardButton.Ok:
        return
    window.backup_busy = True
    window.disarm()
    palette = window.tool_pages.get('palettes')
    if palette:
        palette.close_floating()
    job = BackupJob(window.store.root, Path(archive), destination, window)
    dialog = BackupProgress(job, window)
    job.start()
    dialog.exec()
    job.wait()
    window.backup_busy = False
    success, error = job.success, job.error
    job.deleteLater()
    dialog.deleteLater()
    if not success:
        QMessageBox.warning(window, '备份未完成' if not restore else '恢复未完成', error)
        return
    if not restore:
        window.feedback_toast.show_message('完整备份已保存')
        return
    answer = QMessageBox.question(window, '恢复完成',
        '资料已校验并恢复到新目录。切换后将退出工具箱，请重新打开；原资料仍然保留。\n\n现在切换？',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
    if answer == QMessageBox.StandardButton.Yes:
        try:
            activate_workspace(base, destination)
        except Exception as exc:
            QMessageBox.warning(window, '暂未切换', str(exc))
            return
        window.quit_app()
    else:
        QMessageBox.information(window, '恢复副本已保留', str(destination))
