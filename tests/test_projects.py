import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from creative_toolbox.projects import (ProjectStore, new_project, palette_copy, font_copy,
                                      image_reference, image_projects, resolve_image, export_project, validate)
from creative_toolbox.assets.library import AssetStore
from creative_toolbox.resources_search import search_resources
from creative_toolbox.workspace_backup import export_workspace, restore_workspace
from tests.test_assets import picture


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "workspace"
        self.root.mkdir()
        self.store = ProjectStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def project(self):
        p = new_project("秋季品牌项目")
        p["specs"] = {"canvas": "1920 × 1080 px", "ppi": "144"}
        p["resources"] = [palette_copy(dict(name="品牌色", colors=[dict(name="主色", hex="#245cdb")])),
                          font_copy("Missing Test Font", "Regular", "标题候选")]
        return self.store.save(p)

    def test_opening_and_searching_empty_store_never_creates_data(self):
        self.assertEqual(self.store.list(), [])
        self.assertEqual(search_resources(self.root, "项目"), ([], [], {}))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_only_name_required_and_roundtrip_preserves_specifications(self):
        p = self.project()
        loaded = ProjectStore(self.root).get(p["id"])
        self.assertEqual(loaded, p)
        self.assertEqual(p["resources"][0]["colors"][0]["hex"], "#245CDB")
        self.assertEqual(p["revision"], 1)

    def test_project_copy_has_independent_palette_and_font_records(self):
        original = self.project()
        copy = self.store.duplicate(original["id"], "独立项目")
        self.assertNotEqual(copy["resources"][0]["id"], original["resources"][0]["id"])
        copy["resources"][0]["colors"][0]["hex"] = "#FF0000"
        copy["resources"][1]["note"] = "另一项目正文"
        self.store.save(copy)
        self.assertEqual(self.store.get(original["id"]), original)
        self.assertFalse((self.root / "palettes.json").exists())
        self.assertFalse((self.root / "fonts.json").exists())

    def test_stale_revision_is_rejected_and_never_overwrites(self):
        p = self.project()
        fresh = deepcopy(p)
        fresh["name"] = "已更新"
        saved = self.store.save(fresh)
        p["name"] = "旧编辑覆盖"
        with self.assertRaisesRegex(ValueError, "其他位置更新"):
            self.store.save(p)
        self.assertEqual(self.store.get(saved["id"]), saved)

    def test_archive_and_restore_keep_resources(self):
        p = self.project()
        p["archived"] = True
        p = self.store.save(p)
        self.assertTrue(self.store.get(p["id"])["archived"])
        p["archived"] = False
        self.assertFalse(self.store.save(p)["archived"])
        self.assertEqual(len(self.store.list()), 1)

    def test_unknown_schema_and_corrupt_file_preserved(self):
        self.store.path.write_bytes(b"not a database")
        store = ProjectStore(self.root)
        self.assertTrue(store.read_only)
        with self.assertRaises(ValueError):
            store.save(new_project("项目"))
        self.assertEqual(store.path.read_bytes(), b"not a database")
        store.path.unlink()
        with closing(sqlite3.connect(store.path)) as db:
            db.execute("PRAGMA user_version=99")
            db.commit()
        before = store.path.read_bytes()
        self.assertTrue(ProjectStore(self.root).read_only)
        self.assertEqual(store.path.read_bytes(), before)

    def test_invalid_date_resource_and_spec_preserve_last_saved_project(self):
        p = self.project()
        before = self.store.path.read_bytes()
        for field, value in (("due", "2026-02-30"), ("name", ""), ("scene", "unknown"),
                             ("specs", {"unknown": "value"}), ("revision", True)):
            candidate = deepcopy(p)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                self.store.save(candidate)
        p["resources"].append(deepcopy(p["resources"][0]))
        with self.assertRaises(ValueError):
            self.store.save(p)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_image_reference_tracks_rename_but_detects_trash_and_other_library(self):
        assets = AssetStore(self.root / "assets")
        try:
            key, _ = assets.add_file(picture(self.base / "reference.png"), title="原名称")
            reference = image_reference(assets.library_id, assets.get(key))
            assets.update(key, "新名称", [], "", "", True)
            self.assertEqual(resolve_image(self.root, reference)[0]["title"], "新名称")
            assets.set_deleted(key, True)
            with self.assertRaisesRegex(ValueError, "回收站"):
                resolve_image(self.root, reference)
            assets.set_deleted(key, False)
            wrong = deepcopy(reference)
            wrong["library_id"] = "a" * 32
            with self.assertRaisesRegex(ValueError, "其他素材库"):
                resolve_image(self.root, wrong)
            wrong = deepcopy(reference)
            wrong["hash"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "不一致"):
                resolve_image(self.root, wrong)
        finally:
            assets.close()

    def test_full_backup_restores_project_and_image_identity(self):
        assets = AssetStore(self.root / "assets")
        try:
            key, _ = assets.add_file(picture(self.base / "reference.png"))
            p = self.project()
            p["resources"].append(image_reference(assets.library_id, assets.get(key)))
            p = self.store.save(p)
        finally:
            assets.close()
        archive = self.base / "full.ctbackup"
        export_workspace(self.root, archive)
        restored = restore_workspace(archive, self.base / "restored")
        self.assertEqual(ProjectStore(restored).get(p["id"]), p)
        self.assertTrue(resolve_image(restored, p["resources"][-1])[1].exists())

    def test_corrupt_project_blocks_backup_without_replacing_existing_archive(self):
        self.store.path.write_bytes(b"broken")
        output = self.base / "backup.ctbackup"
        output.write_bytes(b"existing backup")
        with self.assertRaises((ValueError, sqlite3.Error)):
            export_workspace(self.root, output)
        self.assertEqual(output.read_bytes(), b"existing backup")

    def test_saved_image_usage_includes_archived_projects_and_missing_export_status(self):
        assets = AssetStore(self.root / "assets")
        try:
            key, _ = assets.add_file(picture(self.base / "reference.png"))
            p = self.project()
            p["resources"].append(image_reference(assets.library_id, assets.get(key)))
            p["archived"] = True
            p = self.store.save(p)
            self.assertEqual(image_projects(self.root, assets.library_id, key), [p["name"]])
            assets.set_deleted(key, True)
            output = self.base / "missing.md"
            export_project(p, self.root, output)
            self.assertIn("不可用：图片已移入回收站", output.read_text(encoding="utf-8"))
            self.assertEqual(len(self.store.get(p["id"])["resources"]), 3)
        finally:
            assets.close()

    def test_database_open_failure_preserves_last_saved_project(self):
        p = self.project()
        original = self.store.path.read_bytes()
        p["name"] = "未能保存"
        with patch("creative_toolbox.projects.sqlite3.connect", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.Error):
                self.store.save(p)
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_export_is_atomic_and_contains_specifications_and_copy_content(self):
        p = self.project()
        p["delivery"] = "PNG 输出\n保留透明通道"
        output = self.base / "brief.md"
        export_project(p, self.root, output)
        content = output.read_text(encoding="utf-8")
        self.assertIn("1920 × 1080 px", content)
        self.assertIn("画布尺寸", content)
        self.assertIn("#245CDB", content)
        self.assertIn("Missing Test Font", content)
        self.assertIn("不包含图片原件或字体文件", content)
        with patch("creative_toolbox.projects.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                export_project(p, self.root, output)
        self.assertEqual(output.read_text(encoding="utf-8"), content)
        self.assertFalse(list(self.base.glob("*.tmp")))
        with self.assertRaisesRegex(ValueError, "资料目录以外"):
            export_project(p, self.root, self.store.path)

    def test_search_returns_stable_project_identifier_and_partial_failure_warning(self):
        p = self.project()
        rows, warnings, counts = search_resources(self.root, "秋季")
        self.assertEqual(rows[0]["reference"], p["id"])
        self.assertEqual(counts, {"projects": 1})
        self.assertFalse(warnings)
        self.store.path.write_bytes(b"broken")
        self.assertIn("项目暂未搜索", search_resources(self.root, "秋季")[1][0])


class ProjectUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from creative_toolbox.project_ui import ProjectPage
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.page = ProjectPage(self.root)
        self.p = self.page.store.save(new_project("项目 A"))
        self.page.open_project(self.p["id"])

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_edit_save_and_reopen_keeps_spec_and_candidate(self):
        self.page.name.setText("项目 B")
        self.page.spec_fields["canvas"].setText("1080 × 1920 px")
        self.page.add_resource(font_copy("Unavailable Font"))
        self.assertTrue(self.page.dirty)
        self.assertTrue(self.page.save())
        p = ProjectStore(self.root).get(self.p["id"])
        self.assertEqual(p["name"], "项目 B")
        self.assertEqual(p["specs"]["canvas"], "1080 × 1920 px")
        self.assertFalse(self.page.dirty)

    def test_cancel_switch_preserves_draft_then_discard_loads_other_project(self):
        other = self.page.store.save(new_project("其他项目"))
        self.page.name.setText("未保存草稿")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.page.open_project(other["id"]))
        self.assertEqual(self.page.name.text(), "未保存草稿")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.page.open_project(other["id"]))
        self.assertEqual(self.page.current["id"], other["id"])
        self.assertEqual(self.page.store.get(self.p["id"])["name"], "项目 A")

    def test_invalid_save_preserves_draft_and_persisted_record(self):
        self.page.due.setText("2026-99-99")
        self.assertFalse(self.page.save())
        self.assertTrue(self.page.dirty)
        self.assertEqual(self.page.store.get(self.p["id"])["due"], "")
        self.assertIn("未保存", self.page.status.text())

    def test_navigation_search_and_quit_guard(self):
        from creative_toolbox.ui import MainWindow
        from creative_toolbox.storage import Store, Settings
        from creative_toolbox.platforms.unavailable import UnavailableBackend
        w = MainWindow(UnavailableBackend("darwin", "test"), Store(self.root, "darwin"), Settings(), False)
        try:
            self.assertEqual(w.tool_pages, {})
            w.navigate("projects")
            page = w.tool_pages["projects"]
            self.assertTrue(w.nav["projects"].isChecked())
            w.open_resource(dict(kind="projects", reference=self.p["id"]))
            page.name.setText("退出前草稿")
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
                w.quit_app()
            self.assertFalse(w.quitting)
            page.dirty = False
        finally:
            w.quit_app()
            w.close()

    def test_scene_changes_preserve_other_spec_values(self):
        self.page.spec_fields["ppi"].setText("300")
        self.page.scene.setCurrentIndex(self.page.scene.findData("music"))
        self.page.spec_fields["bpm"].setText("120，四分音符")
        self.assertTrue(self.page.save())
        self.page.scene.setCurrentIndex(self.page.scene.findData("design"))
        self.assertEqual(self.page.spec_fields["ppi"].text(), "300")
        self.assertEqual(self.page.form.labelForField(self.page.spec_fields["canvas"]).text(), "画布尺寸")
