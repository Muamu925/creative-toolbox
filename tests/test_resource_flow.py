import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import sqlite3
import tempfile
import time
import unittest
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from creative_toolbox.assets.library import AssetStore
from creative_toolbox.assets.page import AssetPage
from creative_toolbox.design_core import PaletteStore, validate_library
from creative_toolbox.palette_model import PaletteModel
from creative_toolbox.help_ui import HelpPage
from creative_toolbox.ui import MainWindow
from creative_toolbox.storage import Store, Settings
from tests.test_assets import picture
from tests.test_safety import FakeBackend


class ResourceFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = picture(self.root / "reference.png")
        self.store = AssetStore(self.root / "assets")
        self.asset, _ = self.store.add_file(self.image)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def source(self):
        return dict(library_id=self.store.library_id, asset_id=self.asset,
                    hash=self.store.get(self.asset)["hash"], title="音乐节参考")

    def test_collections_many_to_many_filter_rename_and_remove_keeps_image(self):
        a = self.store.save_collection("海报")
        b = self.store.save_collection("音乐节")
        self.store.set_collections(self.asset, [a, b, a])
        self.assertEqual(set(self.store.asset_collections(self.asset)), {a, b})
        self.assertEqual(self.store.list_assets(collection=a)[1], 1)
        self.store.save_collection("秋季活动", a)
        self.store.delete_collection(a)
        self.assertEqual(self.store.asset_collections(self.asset), [b])
        self.assertTrue(self.store.path_for(self.asset).exists())
        self.store.set_deleted(self.asset, True)
        self.assertEqual(self.store.list_assets(collection=b)[1], 0)
        self.assertEqual(self.store.list_assets(scope="trash", collection=b)[1], 1)
        self.assertEqual(self.store.collections()[0]["count"], 0)

    def test_collection_validation_and_transaction_rollback(self):
        a = self.store.save_collection("Poster")
        self.store.set_collections(self.asset, [a])
        for name in ("  ", "a" * 81, "poster"):
            with self.assertRaises(ValueError):
                self.store.save_collection(name)
        with self.assertRaises(ValueError):
            self.store.set_collections(self.asset, ["missing"])
        self.assertEqual(self.store.asset_collections(self.asset), [a])
        self.store.db.execute("CREATE TRIGGER fail_membership BEFORE INSERT ON collection_assets BEGIN SELECT RAISE(ABORT,'full'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set_collections(self.asset, [a])
        self.assertEqual(self.store.asset_collections(self.asset), [a])

    def test_v1_upgrade_preserves_identity_original_and_preupgrade_backup(self):
        identity = self.store.library_id
        root = self.store.root
        self.store.db.executescript("DROP TABLE collection_assets; DROP TABLE collections; PRAGMA user_version=1;")
        self.store.close()
        self.store = AssetStore(root)
        self.assertEqual(self.store.library_id, identity)
        self.assertEqual(self.store.db.execute("PRAGMA user_version").fetchone()[0], 2)
        with closing(sqlite3.connect(root / "before-collections.sqlite3")) as previous:
            self.assertEqual(previous.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(previous.execute("SELECT id FROM assets").fetchone()[0], self.asset)
        self.assertTrue(self.store.path_for(self.asset).exists())

    def test_collection_and_trash_roundtrip_backup(self):
        group = self.store.save_collection("主题参考")
        self.store.set_collections(self.asset, [group])
        self.store.set_deleted(self.asset, True)
        path = self.root / "backup.zip"
        self.store.export_backup(path)
        restored = AssetStore(AssetStore.restore_backup(path, self.root / "restored"))
        try:
            self.assertEqual(restored.library_id, self.store.library_id)
            self.assertEqual(restored.asset_collections(self.asset), [group])
            self.assertEqual(restored.list_assets(scope="trash", collection=group)[1], 1)
        finally:
            restored.close()

    def test_v1_archive_restores_and_upgrades(self):
        self.store.db.executescript("DROP TABLE collection_assets; DROP TABLE collections; PRAGMA user_version=1;")
        archive = self.root / "legacy.zip"
        self.store.export_backup(archive)
        restored = AssetStore(AssetStore.restore_backup(archive, self.root / "legacy-restored"))
        try:
            self.assertEqual(restored.get(self.asset)["title"], "reference")
            self.assertEqual(restored.collections(), [])
            self.assertEqual(restored.db.execute("PRAGMA user_version").fetchone()[0], 2)
        finally:
            restored.close()

    def test_database_export_limit_preserves_previous_backup(self):
        backup = self.root / "old.zip"
        backup.write_bytes(b"previous backup")
        with patch("creative_toolbox.assets.library.MAX_DATABASE_BYTES", 1):
            with self.assertRaises(ValueError):
                self.store.export_backup(backup)
        self.assertEqual(backup.read_bytes(), b"previous backup")

    def test_palette_source_survives_rename_reorder_export_restart_and_undo(self):
        path = self.root / "palettes.json"
        model = PaletteModel(path)
        self.assertTrue(model.add_from_asset("自然", ["#355E46"], self.source()))
        candidate = deepcopy(model.library)
        candidate["palettes"][-1]["name"] = "新名称"
        candidate["palettes"].reverse()
        self.assertTrue(model.commit(candidate, 0))
        self.assertEqual(model.source_palettes(self.store.library_id, self.asset), [(0, "新名称")])
        output = self.root / "export.json"
        PaletteStore.write(output, model.library)
        self.assertEqual(PaletteStore.read(output)["palettes"][0]["source_asset"], self.source())
        reloaded = PaletteModel(path)
        self.assertEqual(reloaded.source_palettes(self.store.library_id, self.asset), [(0, "新名称")])
        self.assertTrue(model.undo())
        self.assertEqual(model.source_palettes(self.store.library_id, self.asset), [(1, "自然")])
        self.assertTrue(model.undo())
        self.assertEqual(model.source_palettes(self.store.library_id, self.asset), [])

    def test_bad_provenance_and_failed_save_preserve_palette(self):
        model = PaletteModel(self.root / "palettes.json")
        before = deepcopy(model.library)
        with patch.object(model.store, "save", side_effect=OSError("full")):
            self.assertFalse(model.add_from_asset("候选", ["#123456"], self.source()))
        self.assertEqual(model.library, before)
        candidate = deepcopy(before)
        candidate["schema"] = 2
        candidate["palettes"][0]["source_asset"] = dict(self.source(), asset_id="../outside")
        with self.assertRaises(ValueError):
            validate_library(candidate)


class ResourceInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.window = MainWindow(FakeBackend(), Store(self.root, "win32"), Settings(), start_timer=False)

    def tearDown(self):
        assets = self.window.tool_pages.get("assets")
        if assets:
            if assets.worker:
                assets.worker.cancel.set()
                assets.worker.wait(10000)
                self.app.processEvents()
            assets.dirty = False
        self.window.quit_app()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def page(self):
        self.window.open_tool("assets")
        page = self.window.tool_pages["assets"]
        source = picture(self.root / "sample.png")
        asset, _ = page.store.add_file(source)
        page.refresh(selected=asset)
        return page, asset

    def wait(self, page):
        deadline = time.monotonic() + 10
        while page.worker and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(page.worker)

    def test_context_help_is_lazy_searchable_and_opens_correct_tool(self):
        self.assertIsNone(self.window.help_page)
        self.assertEqual(self.window.tool_pages, {})
        self.window.open_help("backup")
        help_page = self.window.help_page
        self.assertEqual(self.window.tool_pages, {})
        self.assertIn("备份", help_page.article.toPlainText())
        help_page.search.setText("xxxxxxxx-no-match")
        self.assertEqual(help_page.topics.count(), 0)
        self.assertFalse(help_page.open_button.isEnabled())
        help_page.show_topic("calculators")
        help_page.open_button.click()
        self.assertEqual(set(self.window.tool_pages), {"calculators"})
        self.window.help_shortcut.activated.emit()
        self.assertEqual(help_page.current_topic.id, "calculators")
        self.assertIs(self.window.pages.currentWidget(), help_page)

    def test_help_remains_available_when_protection_unavailable(self):
        self.window.protection_available = False
        self.window.open_help("protection")
        self.assertIn("不会发送", self.window.help_page.article.toPlainText())
        self.assertFalse(self.window.controller.automatic)

    def test_collection_import_and_reviewed_filter_refresh(self):
        page, asset = self.page()
        group = page.store.save_collection("活动")
        page.reload_collections(group)
        page.filter_changed()
        self.assertEqual(page.list.count(), 0)
        page.start_job("import", [str(self.root / "sample.png")])
        self.wait(page)
        self.assertEqual(page.list.count(), 1)
        self.assertEqual(page.store.asset_collections(page.current_id), [group])
        page.scope.setCurrentIndex(page.scope.findData("inbox"))
        page.reviewed.setChecked(True)
        page.save_button.click()
        self.assertEqual(page.list.count(), 0)

    def test_unsaved_collection_switch_cancel_restores_filter(self):
        page, asset = self.page()
        group = page.store.save_collection("活动")
        page.reload_collections()
        page.title.setText("尚未保存")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            page.collection.setCurrentIndex(page.collection.findData(group))
        self.assertIsNone(page.collection.currentData())
        self.assertEqual(page.title.text(), "尚未保存")
        self.assertEqual(page.current_id, asset)

    def test_extract_preview_save_uses_shared_model_and_roundtrip_source(self):
        page, asset = self.page()
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            page.extract_palette()
            self.wait(page)
        palette = self.window.palette_page
        self.assertIs(page.palette_model(), palette.model)
        self.assertIs(self.window.pages.currentWidget(), palette)
        self.assertEqual(palette.current()["source_asset"]["asset_id"], asset)
        palette.source_button.click()
        self.assertIs(self.window.pages.currentWidget(), page)
        self.assertEqual(page.current_id, asset)
        page.open_linked_palette()
        self.assertIs(self.window.pages.currentWidget(), palette)

    def test_cancel_preview_creates_no_palette(self):
        page, asset = self.page()
        model = page.palette_model()
        before = deepcopy(model.library)
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            page.extract_palette()
            self.wait(page)
        self.assertEqual(model.library, before)
        self.assertIn("已取消", page.status.text())

    def test_failed_palette_save_keeps_image_and_reports_failure(self):
        page, asset = self.page()
        model = page.palette_model()
        before = deepcopy(model.library)
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted), patch.object(model.store, "save", side_effect=OSError("full")):
            page.extract_palette()
            self.wait(page)
        self.assertEqual(model.library, before)
        self.assertTrue(page.store.path_for(asset).exists())
        self.assertIn("未保存", page.status.text())

    def test_source_jump_restores_trash_and_refuses_other_library(self):
        page, asset = self.page()
        record = page.store.get(asset)
        source = dict(library_id=page.store.library_id, asset_id=asset, hash=record["hash"], title=record["title"])
        page.store.set_deleted(asset, True)
        self.assertTrue(page.show_source(source))
        self.assertEqual(page.scope.currentData(), "trash")
        self.assertEqual(page.current_id, asset)
        self.window.open_tool("palettes")
        self.window.open_asset_source(dict(source, library_id="a" * 32))
        self.assertIs(self.window.pages.currentWidget(), self.window.palette_page)
        self.assertIn("另一个素材库", self.window.palette_page.status.text())


if __name__ == "__main__":
    unittest.main()
