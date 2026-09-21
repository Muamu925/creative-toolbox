import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import Qt, QMimeData, QUrl
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QMessageBox

from creative_toolbox.assets.library import AssetStore, Cancelled
from creative_toolbox.assets.jobs import AssetJob
from creative_toolbox.assets.page import AssetPage
from creative_toolbox.ui import MainWindow
from creative_toolbox.storage import Store, Settings
from tests.test_safety import FakeBackend


def picture(path, color="#53775e"):
    image = QImage(120, 80, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return path


class AssetStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = picture(self.root / "source.png")
        self.store = AssetStore(self.root / "assets")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_managed_copy_independent_from_source_and_survives_restart(self):
        asset_id, duplicate = self.store.add_file(self.source)
        self.assertFalse(duplicate)
        self.source.unlink()
        self.assertTrue(self.store.path_for(asset_id).exists())
        self.store.close()
        self.store = AssetStore(self.root / "assets")
        self.assertEqual(self.store.get(asset_id)["width"], 120)
        self.assertTrue(self.store.path_for(asset_id, True).exists())

    def test_repeated_capture_retains_separate_metadata_and_one_blob(self):
        first, _ = self.store.add_file(self.source)
        second, duplicate = self.store.add_file(self.source)
        self.assertTrue(duplicate)
        self.assertNotEqual(first, second)
        self.store.update(first, "海报", ["绿色", "海报"], "作者 A", "构图参考", True)
        self.store.update(second, "视频封面", ["片头"], "作者 B", "", False)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM blobs").fetchone()[0], 1)
        self.assertEqual(len(list((self.store.root / "originals").iterdir())), 1)
        self.assertEqual(self.store.get(first)["source"], "作者 A")
        self.assertEqual(self.store.get(second)["source"], "作者 B")

    def test_literal_unicode_search_inbox_and_trash(self):
        asset_id, _ = self.store.add_file(self.source)
        self.store.update(asset_id, "自然海报 50%", ["Grün", "配色"], "例子", "备注", False)
        self.assertEqual(self.store.list_assets("GRÜN 50%")[1], 1)
        self.assertEqual(self.store.list_assets("_")[1], 0)
        self.assertEqual(self.store.list_assets(scope="inbox")[1], 1)
        self.store.set_deleted(asset_id, True)
        self.assertEqual(self.store.list_assets()[1], 0)
        self.assertEqual(self.store.list_assets(scope="trash")[1], 1)
        self.store.set_deleted(asset_id, False)
        self.assertEqual(self.store.list_assets()[1], 1)
        self.assertTrue(self.store.path_for(asset_id).exists())

    def test_invalid_edit_and_failed_commit_preserve_record(self):
        asset_id, _ = self.store.add_file(self.source)
        before = self.store.get(asset_id)
        with self.assertRaises(ValueError):
            self.store.update(asset_id, "", [], "", "", False)
        self.store.db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON assets BEGIN SELECT RAISE(ABORT,'disk error'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.update(asset_id, "changed", [], "", "", True)
        self.assertEqual(self.store.get(asset_id), before)

    def test_invalid_image_and_cancel_leave_no_visible_records(self):
        broken = self.root / "broken.png"
        broken.write_bytes(b"invalid")
        for path in (broken, self.root):
            with self.assertRaises(ValueError):
                self.store.add_file(path)
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.store.add_file(self.source, cancel)
        self.assertEqual(self.store.counts()["total"], 0)
        self.assertEqual(list((self.store.root / "staging").iterdir()), [])

    def test_failed_index_insert_can_be_retried_without_losing_original(self):
        self.store.db.execute("CREATE TRIGGER reject_asset BEFORE INSERT ON assets BEGIN SELECT RAISE(ABORT,'no space'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.add_file(self.source)
        self.assertEqual(self.store.list_assets()[1], 0)
        self.assertEqual(len(list((self.store.root / "originals").iterdir())), 1)
        self.store.db.execute("DROP TRIGGER reject_asset")
        asset_id, _ = self.store.add_file(self.source)
        self.assertTrue(self.store.path_for(asset_id).exists())

    def test_future_database_is_not_modified(self):
        self.store.close()
        path = self.root / "assets" / "library.sqlite3"
        db = sqlite3.connect(path)
        db.execute("PRAGMA user_version=999")
        db.close()
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            AssetStore(path.parent)
        self.assertEqual(path.read_bytes(), before)

    def test_backup_restores_metadata_ids_and_originals(self):
        first, _ = self.store.add_file(self.source)
        second, _ = self.store.add_file(self.source)
        self.store.update(first, "项目海报", ["自然"], "https://example.test/a", "备注", True)
        self.store.set_deleted(second, True)
        output = self.root / "backup.zip"
        self.store.export_backup(output)
        destination = self.root / "restored"
        AssetStore.restore_backup(output, destination)
        restored = AssetStore(destination)
        try:
            self.assertEqual(restored.library_id, self.store.library_id)
            self.assertEqual(restored.get(first), self.store.get(first))
            self.assertEqual(restored.get(second)["deleted"], 1)
            self.assertEqual(restored.path_for(first).read_bytes(), self.source.read_bytes())
            self.assertTrue(restored.path_for(first, True).exists())
        finally:
            restored.close()

    def test_backup_cancellation_preserves_existing_output(self):
        self.store.add_file(self.source)
        output = self.root / "backup.zip"
        output.write_bytes(b"old backup")
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.store.export_backup(output, cancel)
        self.assertEqual(output.read_bytes(), b"old backup")

    def test_backup_cannot_overwrite_active_database(self):
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.export_backup(self.store.path)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_tampered_or_traversal_backup_never_activates(self):
        asset_id, _ = self.store.add_file(self.source)
        valid = self.root / "valid.zip"
        self.store.export_backup(valid)
        with zipfile.ZipFile(valid) as archive:
            content = {name: archive.read(name) for name in archive.namelist()}
        original = next(name for name in content if name.startswith("originals/"))
        content[original] = b"tampered"
        altered = self.root / "altered.zip"
        with zipfile.ZipFile(altered, "w") as archive:
            for name, data in content.items():
                archive.writestr(name, data)
        target = self.root / "invalid-restored"
        with self.assertRaises(ValueError):
            AssetStore.restore_backup(altered, target)
        self.assertFalse(target.exists())
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"schema": 1, "files": [
                {"path": "../outside.png", "size": 1, "sha256": "wrong"}]}))
            archive.writestr("../outside.png", b"x")
        with self.assertRaises(ValueError):
            AssetStore.restore_backup(malicious, target)
        self.assertFalse((self.root / "outside.png").exists())
        self.assertEqual(self.store.get(asset_id)["title"], "source")

    def test_missing_original_backup_fails_and_preserves_old_backup(self):
        asset_id, _ = self.store.add_file(self.source)
        self.store.path_for(asset_id).unlink()
        output = self.root / "backup.zip"
        output.write_bytes(b"old backup")
        with self.assertRaises((OSError, ValueError)):
            self.store.export_backup(output)
        self.assertEqual(output.read_bytes(), b"old backup")

    def test_interrupted_tasks_marked_without_reimporting(self):
        asset_id, _ = self.store.add_file(self.source)
        task = self.store.start_task("import", 3)
        self.assertEqual(self.store.recover_tasks(), 1)
        self.assertEqual(self.store.db.execute("SELECT state FROM tasks WHERE id=?", (task,)).fetchone()[0], "interrupted")
        self.assertTrue(self.store.path_for(asset_id).exists())
        self.assertEqual(self.store.recover_tasks(), 0)

    def test_restore_cancel_and_existing_directory_are_non_destructive(self):
        self.store.add_file(self.source)
        output = self.root / "backup.zip"
        self.store.export_backup(output)
        cancel = Event()
        cancel.set()
        destination = self.root / "cancelled"
        with self.assertRaises(Cancelled):
            AssetStore.restore_backup(output, destination, cancel)
        self.assertFalse(destination.exists())
        with self.assertRaises(ValueError):
            AssetStore.restore_backup(output, self.store.root)


class AssetUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = picture(self.root / "reference.png")
        self.page = AssetPage(self.root / "data")

    def tearDown(self):
        if self.page.worker:
            self.page.worker.cancel.set()
            self.page.worker.wait(10000)
            self.app.processEvents()
        self.page.shutdown()
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def wait_job(self):
        deadline = time.monotonic() + 12
        while self.page.worker and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(self.page.worker)
        self.app.processEvents()

    def import_one(self):
        self.page.start_job("import", [str(self.source)])
        self.wait_job()
        self.assertEqual(self.page.store.counts()["active"], 1)
        return self.page.current_id

    def test_background_import_metadata_search_and_trash_restore(self):
        asset_id = self.import_one()
        self.page.title.setText("森林参考")
        self.page.tags.setText("海报，自然")
        self.page.source.setText("作者提供")
        self.page.reviewed.setChecked(True)
        self.assertTrue(self.page.save_details())
        self.assertEqual(self.page.store.get(asset_id)["tags"], ["海报", "自然"])
        self.page.search.setText("海报")
        self.page.filter_changed()
        self.assertEqual(self.page.list.count(), 1)
        self.page.toggle_trash()
        self.assertEqual(self.page.list.count(), 0)
        self.page.scope.setCurrentIndex(self.page.scope.findData("trash"))
        self.assertEqual(self.page.list.count(), 1)
        self.page.list.setCurrentRow(0)
        self.page.toggle_trash()
        self.assertEqual(self.page.store.get(asset_id)["deleted"], 0)

    def test_failed_item_does_not_block_valid_item_and_failure_is_visible(self):
        broken = self.root / "broken.jpg"
        broken.write_bytes(b"no")
        self.page.start_job("import", [str(broken), str(self.source)])
        self.wait_job()
        self.assertEqual(self.page.store.counts()["active"], 1)
        self.assertIn("broken.jpg", self.page.errors.toPlainText())
        self.assertIn("失败 1", self.page.status.text())

    def test_clipboard_is_only_read_on_explicit_action(self):
        image = QImage(str(self.source))
        with patch.object(QApplication, "clipboard") as clipboard:
            clipboard.return_value.image.return_value = image
            self.assertEqual(clipboard.call_count, 0)
            self.page.paste_image()
        self.wait_job()
        row = self.page.store.get(self.page.current_id)
        self.assertEqual(row["origin"], "剪贴板")
        self.assertEqual(row["title"], "剪贴板图片")

    def test_unsaved_filter_cancel_preserves_draft_and_view(self):
        self.import_one()
        self.page.title.setText("未保存的名称")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.page.search.setText("不存在")
            self.page.filter_changed()
        self.assertEqual(self.page.search.text(), "")
        self.assertEqual(self.page.title.text(), "未保存的名称")
        self.assertEqual(self.page.list.count(), 1)
        self.assertTrue(self.page.dirty)
        self.page.dirty = False

    def test_restore_switch_persists_and_old_library_remains(self):
        asset_id = self.import_one()
        old = self.page.store.root
        backup = self.root / "backup.zip"
        self.page.start_job("backup", backup)
        self.wait_job()
        destination = self.page.data_root / ("assets-restored-" + "a" * 32)
        self.page.start_job("restore", (backup, destination))
        self.wait_job()
        self.assertEqual(self.page.store.root, destination)
        self.assertTrue((old / "library.sqlite3").exists())
        self.assertEqual(self.page.store.get(asset_id)["title"], "reference")
        reloaded = AssetPage(self.page.data_root)
        try:
            self.assertEqual(reloaded.store.root, destination)
            self.assertEqual(reloaded.store.get(asset_id)["title"], "reference")
        finally:
            reloaded.shutdown()
            reloaded.deleteLater()

    def test_reference_reuses_managed_preview_after_source_removed(self):
        self.import_one()
        self.source.unlink()
        self.page.open_reference()
        self.assertTrue(self.page.reference.isVisible())
        self.assertTrue(self.page.reference.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.page.reference.move(100000, 100000)
        self.page.reference.ensure_visible()
        self.assertLess(self.page.reference.x(), 100000)

    def test_host_lazy_load_and_quit_cancel_preserve_other_tools(self):
        window = MainWindow(FakeBackend(), Store(self.root / "host", "win32"), Settings(), start_timer=False)
        try:
            self.assertNotIn("assets", window.tool_pages)
            window.open_tool("assets")
            assets = window.tool_pages["assets"]
            window.open_tool("calculators")
            self.assertFalse(window.controller.automatic)
            self.assertIsNot(window.pages.currentWidget(), assets)
            with patch.object(assets, "can_exit", return_value=False):
                window.quit_app()
            self.assertFalse(window.quitting)
            window.quit_app()
            self.assertTrue(window.quitting)
        finally:
            window.tray.hide()
            window.close()
            window.deleteLater()

    def test_cancelled_import_has_no_new_records(self):
        job = AssetJob(self.page.store.root, "import", [str(self.source)])
        job.cancel.set()
        job.start()
        self.assertTrue(job.wait(10000))
        self.assertEqual(job.result["state"], "cancelled")
        self.assertEqual(self.page.store.counts()["active"], 0)
        job.deleteLater()


if __name__ == "__main__":
    unittest.main()
