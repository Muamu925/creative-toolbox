import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from creative_toolbox.fonts.library import FontLibrary, empty, validate, read_file, write_file, MAX_BYTES


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fonts.json"
        self.library = FontLibrary(self.path)

    def test_group_membership_is_many_to_many_and_survives_restart(self):
        a, b = self.library.add_group("海报"), self.library.add_group("字幕")
        self.library.membership(["Family [Foundry]"], a)
        self.library.membership(["Family [Foundry]"], b)
        self.library.tag(["Family [Foundry]"], "标题")
        self.library.edit(["Family [Foundry]"], favorite=True, note="用途说明")
        reloaded = FontLibrary(self.path)
        self.assertEqual(reloaded.metadata("Family [Foundry]")["groups"], [a, b])
        reloaded.delete_group(a)
        value = FontLibrary(self.path).metadata("Family [Foundry]")
        self.assertEqual(value["groups"], [b])
        self.assertEqual(value["tags"], ["标题"])
        self.assertTrue(value["favorite"])
        self.assertEqual(value["note"], "用途说明")

    def test_failed_write_changes_neither_memory_nor_disk(self):
        self.library.edit(["A"], note="original")
        before = deepcopy(self.library.data)
        blob = self.path.read_bytes()
        with patch("creative_toolbox.fonts.library.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.library.edit(["A"], note="lost")
        self.assertEqual(self.library.data, before)
        self.assertEqual(self.path.read_bytes(), blob)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_corrupt_source_is_read_only_and_preserved(self):
        self.path.write_text("{broken", encoding="utf-8")
        library = FontLibrary(self.path)
        self.assertTrue(library.read_only)
        with self.assertRaises(ValueError):
            library.add_group("test")
        self.assertEqual(self.path.read_text(), "{broken")

    def test_duplicate_names_and_dangling_group_rejected(self):
        self.library.add_group("Brand")
        with self.assertRaises(ValueError):
            self.library.add_group("brand")
        before = deepcopy(self.library.data)
        with self.assertRaises(ValueError):
            self.library.edit(["A"], groups=["missing"])
        self.assertEqual(before, self.library.data)

    def test_merge_preserves_local_notes_and_handles_group_id_conflict(self):
        gid = self.library.add_group("Local")
        self.library.edit(["A"], note="Local note", groups=[gid], tags=["local"])
        other = FontLibrary()
        other.data["groups"][gid] = "Incoming"
        other.edit(["A"], note="Imported note", groups=[gid], tags=["incoming"], favorite=True)
        conflicts = self.library.merge(other.data)
        self.assertEqual(conflicts, ["A / note"])
        value = self.library.metadata("A")
        self.assertEqual(value["note"], "Local note")
        self.assertEqual(len(value["groups"]), 2)
        self.assertEqual(set(value["tags"]), {"local", "incoming"})
        self.assertEqual(len(self.library.data["groups"]), 2)

    def test_same_backup_merge_idempotent_and_unknown_family_preserved(self):
        gid = self.library.add_group("Keep")
        self.library.edit(["Unavailable [Foundry]"], groups=[gid], favorite=True)
        backup = Path(self.tmp.name) / "backup.json"
        write_file(backup, self.library.data)
        target = FontLibrary()
        target.merge(read_file(backup))
        before = deepcopy(target.data)
        target.merge(read_file(backup))
        self.assertEqual(before, target.data)
        self.assertIn("Unavailable [Foundry]", target.data["fonts"])

    def test_import_does_not_replace_working_preferences(self):
        self.library.change(lambda d: d.update(preferences={"sample": "Local", "size": 32}))
        incoming = empty()
        incoming["preferences"] = {"sample": "Import", "size": 40}
        self.library.merge(incoming)
        self.assertEqual(self.library.data["preferences"], {"sample": "Local", "size": 32})

    def test_import_validation_is_atomic(self):
        before = deepcopy(self.library.data)
        incoming = empty()
        incoming["fonts"] = {"A": {"tags": ["x"] * 51}}
        with self.assertRaises(ValueError):
            self.library.merge(incoming)
        self.assertEqual(before, self.library.data)
        for malformed in [[], {"schema": True}, {"schema": 1, "groups": {}, "fonts": [], "preferences": {}}]:
            with self.assertRaises(ValueError):
                validate(malformed)

    def test_oversized_backup_rejected(self):
        self.path.write_bytes(b" " * (MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            read_file(self.path)


from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMessageBox
from creative_toolbox.fonts.page import FontPage

AVAILABLE = {
    "Alpha": {"styles": ["Regular", "Bold"], "systems": ["Latin"], "mono": False},
    "Beta": {"styles": ["Regular"], "systems": ["Latin", "Simplified Chinese"], "mono": True},
    "Gamma": {"styles": ["Regular"], "systems": ["Latin"], "mono": False},
}


class FontUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.page = FontPage(Path(self.tmp.name) / "fonts.json", deepcopy(AVAILABLE))
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.page.close)

    def choose(self, *names):
        selection = self.page.list.selectionModel()
        selection.clearSelection()
        for row in range(self.page.proxy.rowCount()):
            index = self.page.proxy.index(row, 0)
            if index.data() in names:
                selection.select(index, QItemSelectionModel.SelectionFlag.Select)

    def visible(self):
        return [self.page.proxy.index(r, 0).data() for r in range(self.page.proxy.rowCount())]

    def test_search_alias_tags_and_combined_filters(self):
        self.page.run_change(lambda: self.page.library.edit(["Beta"], alias="字幕", tags=["标题"]))
        self.page.search.setText("字幕 标题")
        self.assertEqual(self.visible(), ["Beta"])
        self.page.mono.setChecked(True)
        self.assertEqual(self.visible(), ["Beta"])
        self.page.search.setText("Gamma")
        self.assertEqual(self.visible(), [])
        self.assertIn("无匹配", self.page.count.text())

    def test_batch_favorite_and_selection_restore(self):
        self.choose("Alpha", "Beta")
        self.page.operations.setCurrentIndex(2)
        self.page.batch_action()
        self.assertEqual(set(self.page.selected()), {"Alpha", "Beta"})
        self.page.populate_groups("favorites")
        self.assertEqual(self.visible(), ["Alpha", "Beta"])
        self.assertTrue(FontLibrary(self.page.library.path).metadata("Beta")["favorite"])

    def test_group_filter_and_remove_preserves_other_group(self):
        a, b = self.page.library.add_group("A"), self.page.library.add_group("B")
        self.page.run_change(lambda: self.page.library.membership(["Alpha"], a))
        self.page.run_change(lambda: self.page.library.membership(["Alpha"], b))
        self.page.populate_groups("group:"+a)
        self.choose("Alpha")
        self.page.operations.setCurrentIndex(1)
        self.page.batch_action()
        self.assertEqual(self.visible(), [])
        self.page.populate_groups("group:"+b)
        self.assertEqual(self.visible(), ["Alpha"])

    def test_missing_fonts_keep_metadata_and_block_comparison(self):
        self.page.run_change(lambda: self.page.library.edit(["Missing"], note="Keep me", favorite=True))
        self.page.populate_groups("missing")
        self.assertEqual(self.visible(), ["Missing"])
        self.page.populate_groups("all")
        self.choose("Missing", "Alpha")
        self.page.compare_selected()
        self.assertEqual(self.page.tabs.currentIndex(), 0)
        self.assertIn("不可用", self.page.status.text())
        self.page.refresh_catalog()
        self.assertEqual(self.page.library.metadata("Missing")["note"], "Keep me")

    def test_compare_real_style_choices_and_sample_sync(self):
        self.choose("Alpha", "Beta", "Gamma")
        self.page.compare_selected()
        self.assertEqual(self.page.compare_count.value(), 3)
        self.assertEqual(self.page.tabs.currentIndex(), 1)
        self.assertEqual(self.page.styles[0].count(), 2)
        self.page.styles[0].setCurrentText("Bold")
        self.page.sample.setPlainText("项目标题 Aa 123")
        self.page.size.setValue(40)
        for preview in self.page.previews:
            self.assertEqual(preview.toPlainText(), "项目标题 Aa 123")
        self.assertIn("min-height:140px", self.page.previews[0].styleSheet())
        self.page.flush_preferences()
        self.assertEqual(FontLibrary(self.page.library.path).data["preferences"]["size"], 40)

    def test_ui_failed_write_leaves_model_unchanged(self):
        self.choose("Alpha")
        with patch("creative_toolbox.fonts.library.os.replace", side_effect=OSError("denied")):
            self.page.operations.setCurrentIndex(2)
            self.page.batch_action()
        self.assertFalse(self.page.library.metadata("Alpha")["favorite"])
        self.assertIn("未保存", self.page.status.text())

    def test_export_then_import_roundtrip(self):
        self.page.run_change(lambda: self.page.library.edit(["Beta"], tags=["UI"], favorite=True))
        backup = Path(self.tmp.name) / "export.json"
        with patch("creative_toolbox.fonts.page.QFileDialog.getSaveFileName", return_value=(str(backup), "JSON")):
            self.page.export_backup()
        target = FontPage(available=deepcopy(AVAILABLE))
        try:
            with patch("creative_toolbox.fonts.page.QFileDialog.getOpenFileName", return_value=(str(backup), "JSON")), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                target.import_backup()
            self.assertTrue(target.library.metadata("Beta")["favorite"])
            self.assertEqual(target.library.metadata("Beta")["tags"], ["UI"])
        finally:
            target.close()

    def test_unsaved_oversized_sample_does_not_export_stale_backup(self):
        self.page.sample.setPlainText("x" * 2001)
        with patch("creative_toolbox.fonts.page.QFileDialog.getSaveFileName") as dialog:
            self.page.export_backup()
        dialog.assert_not_called()
        self.assertIn("未保存", self.page.status.text())
        self.page.sample.setPlainText("Recovered")
        self.assertTrue(self.page.flush_preferences())

    def test_empty_system_catalog_is_reported_without_fake_previews(self):
        page = FontPage(available={})
        try:
            self.assertEqual(page.proxy.rowCount(), 0)
            self.assertIn("无匹配", page.count.text())
            self.assertTrue(all(p.toPlainText() == "字体当前不可用" for p in page.previews))
        finally:
            page.close()

    def test_export_suffix_does_not_silently_overwrite_existing_backup(self):
        existing = Path(self.tmp.name) / "backup.json"
        existing.write_text("original backup", encoding="utf-8")
        with patch("creative_toolbox.fonts.page.QFileDialog.getSaveFileName", return_value=(str(existing.with_suffix("")), "JSON")), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.page.export_backup()
        self.assertEqual(existing.read_text(), "original backup")
