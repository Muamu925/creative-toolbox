import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from creative_toolbox.workspace import WorkspaceStore, TOOL_BY_ID, search_tools
from creative_toolbox.platforms import load_backend
from creative_toolbox.platforms.unavailable import UnavailableBackend
from creative_toolbox.controller import Controller
from creative_toolbox.storage import Store, Settings
from tests.test_safety import FakeBackend, profile, snapshot

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from creative_toolbox.ui import MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False


class WorkspaceTests(unittest.TestCase):
    def test_search_keywords_case_and_multiple_terms(self):
        self.assertEqual([t.id for t in search_tools("BPM")], ["calculators"])
        self.assertEqual([t.id for t in search_tools("毫米 ppi")], ["calculators"])
        self.assertEqual([t.id for t in search_tools("分组")], ["fonts"])
        self.assertEqual(search_tools("不存在的工具"), [])

    def test_favorites_recent_roundtrip_and_no_document_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workspace.json"
            store = WorkspaceStore(path)
            store.toggle_favorite("fonts")
            store.record_open("fonts")
            store.record_open("palettes")
            store.record_open("fonts")
            loaded = WorkspaceStore(path)
            self.assertNotIn("fonts", loaded.data["favorites"])
            self.assertEqual([r["id"] for r in loaded.data["recent"]], ["fonts", "palettes"])
            self.assertEqual(set(loaded.data), {"schema", "favorites", "recent"})
            self.assertEqual(set(loaded.data["recent"][0]), {"id", "used_at"})

    def test_corrupt_future_and_oversized_file_preserved(self):
        for content in ("{broken", '{"schema": 2}', " " * 64001,
                        '{"schema": 1, "favorites": [], "recent": [{"id":"fonts","used_at":"bad"}]}'):
            with self.subTest(content=content[:40]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "workspace.json"
                path.write_text(content, encoding="utf-8")
                store = WorkspaceStore(path)
                self.assertTrue(store.read_only)
                with self.assertRaises(ValueError):
                    store.toggle_favorite("fonts")
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_failed_atomic_write_preserves_memory_disk_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workspace.json"
            store = WorkspaceStore(path)
            store.record_open("fonts")
            before, raw = deepcopy(store.data), path.read_bytes()
            with patch("creative_toolbox.workspace.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    store.toggle_favorite("fonts")
            self.assertEqual(store.data, before)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_failed_native_loader_returns_inert_adapter(self):
        with patch("creative_toolbox.platforms.create_backend", side_effect=ImportError("private path")):
            backend = load_backend()
        self.assertFalse(backend.available)
        self.assertIn("ImportError", backend.unavailable_reason)
        self.assertNotIn("private path", backend.unavailable_reason)
        self.assertFalse(backend.capture().can_send)
        self.assertIsNone(backend.capture().target)
        controller = Controller(backend, Settings([profile()]))
        controller.automatic = True
        for now in range(30):
            _, decision = controller.tick(now)
            self.assertFalse(decision.due)
        self.assertEqual(controller.requests, 0)
        self.assertFalse(backend.send(snapshot(), None, 0)[0])


@unittest.skipUnless(HAS_QT, "Desktop dependencies required")
class WorkspaceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.windows = []

    def tearDown(self):
        for w in self.windows:
            w.quit_app()
            w.close()
            w.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def window(self, backend=None):
        w = MainWindow(backend or FakeBackend(), Store(self.root, "win32"),
                       Settings([profile()]), start_timer=False)
        self.windows.append(w)
        return w

    def test_start_and_entry_navigation_do_not_load_fonts_or_palettes(self):
        with patch("creative_toolbox.fonts.page.catalog", side_effect=AssertionError("eager font scan")):
            w = self.window()
            self.assertIs(w.pages.currentWidget(), w.entry_pages["home"])
            for route in ("library", "tools", "home", "settings"):
                w.navigate(route)
            self.assertEqual(w.tool_pages, {})
            self.assertFalse((self.root / "palettes.json").exists())
            self.assertFalse((self.root / "fonts.json").exists())

    def test_search_favorite_restart_and_filter_retained(self):
        w = self.window()
        w.navigate("tools")
        directory = w.entry_pages["tools"]
        directory.search.setText("BPM")
        self.assertEqual(directory.visible_tool_ids, ["calculators"])
        w.toggle_tool_favorite("calculators")
        w.open_tool("calculators")
        page = w.pages.currentWidget()
        w.navigate("home")
        w.navigate("tools")
        self.assertEqual(directory.search.text(), "BPM")
        w.open_tool("calculators")
        self.assertIs(w.pages.currentWidget(), page)
        self.assertFalse(w.controller.automatic)
        again = self.window()
        self.assertNotIn("calculators", again.workspace.data["favorites"])
        self.assertEqual(again.workspace.data["recent"][0]["id"], "calculators")

    def test_font_page_reused_and_unsaved_sample_flushed_on_quit(self):
        with patch("creative_toolbox.fonts.page.catalog", return_value={}) as scan:
            w = self.window()
            w.open_tool("fonts")
            page = w.font_page
            page.sample.setPlainText("保存我的新样张")
            w.navigate("home")
            w.open_tool("fonts")
            self.assertIs(w.pages.currentWidget(), page)
            self.assertEqual(scan.call_count, 1)
            w.quit_app()
        saved = json.loads((self.root / "fonts.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["preferences"]["sample"], "保存我的新样张")

    def test_palette_tray_loads_only_palette_and_keeps_same_model(self):
        w = self.window()
        w.open_floating_palette()
        page = w.palette_page
        self.assertEqual(set(w.tool_pages), {"palettes"})
        page.model.toggle_favorite(0)
        w.open_tool("palettes")
        self.assertIs(w.pages.currentWidget(), page)
        self.assertIs(page.floating.model, page.model)
        self.assertFalse(w.controller.automatic)
        w.quit_app()
        self.assertFalse(page.floating.isVisible())

    def test_failed_tool_construction_can_retry_without_losing_home(self):
        w = self.window()
        original = TOOL_BY_ID["calculators"]
        def fail(_):
            raise RuntimeError("failed")
        with patch.dict(TOOL_BY_ID, {"calculators": replace(original, factory=fail)}), patch.object(QMessageBox, "warning"):
            w.open_tool("calculators")
        self.assertNotIn("calculators", w.tool_pages)
        self.assertIs(w.pages.currentWidget(), w.entry_pages["home"])
        self.assertEqual(w.workspace.data["recent"], [])
        w.open_tool("calculators")
        self.assertIs(w.pages.currentWidget(), w.tool_pages["calculators"])

    def test_unavailable_backend_disables_protection_but_tools_work(self):
        w = self.window(UnavailableBackend("win32", "模拟系统能力缺失"))
        self.assertFalse(w.timer.isActive())
        self.assertFalse(w.arm_button.isEnabled())
        self.assertFalse(w.capture_button.isEnabled())
        self.assertFalse(w.tray_pause.isEnabled())
        w.toggle_automatic()
        w.begin_capture()
        self.assertFalse(w.controller.automatic)
        self.assertEqual(w.capture_seconds, 0)
        for tool_id in ("palettes", "calculators", "fonts"):
            w.open_tool(tool_id)
            self.assertIs(w.pages.currentWidget(), w.tool_pages[tool_id])
        w.navigate("protection")
        self.assertIn("模拟系统能力缺失", w.hero_description.text())

    def test_corrupt_workspace_does_not_block_tools_or_overwrite_source(self):
        path = self.root / "workspace.json"
        path.write_text("{broken", encoding="utf-8")
        w = self.window()
        w.open_tool("calculators")
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        self.assertTrue(w.entry_pages["home"].notice.text())

    def test_navigation_leaves_existing_resource_and_rule_files_unchanged(self):
        from creative_toolbox.design_core import PaletteStore
        from creative_toolbox.fonts.library import FontLibrary
        store = Store(self.root, "win32")
        store.save(Settings([profile()]))
        palettes = PaletteStore(self.root / "palettes.json")
        palettes.save(palettes.load())
        fonts = FontLibrary(self.root / "fonts.json")
        fonts.add_group("保留的旧分组")
        paths = [self.root / name for name in ("settings.json", "palettes.json", "fonts.json")]
        before = [p.read_bytes() for p in paths]
        w = self.window()
        for route in ("tools", "library", "home", "protection"):
            w.navigate(route)
        w.toggle_tool_favorite("fonts")
        self.assertEqual([p.read_bytes() for p in paths], before)

    def test_capture_completion_allows_clean_exit(self):
        w = self.window()
        w.begin_capture()
        w.capture_seconds = 1
        with patch.object(w, "add_profile") as add:
            w.capture_countdown()
        self.assertTrue(add.called)
        self.assertIsNone(w.capture_timer)
        w.quit_app()

    def test_failed_favorite_write_does_not_change_autosave_state(self):
        w = self.window()
        w.controller.automatic = True
        before = deepcopy(w.workspace.data)
        with patch.object(w.workspace, "save", side_effect=OSError("read only")):
            w.toggle_tool_favorite("fonts")
        self.assertEqual(w.workspace.data, before)
        self.assertTrue(w.controller.automatic)
        self.assertIn("未保存", w.entry_pages["home"].notice.text())
        w.toggle_tool_favorite("fonts")
        self.assertEqual(w.workspace.warning, "")
        self.assertNotIn("未保存", w.footer.text())


if __name__ == "__main__":
    unittest.main()
