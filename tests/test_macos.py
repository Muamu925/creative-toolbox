import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from creative_toolbox.mac_workspace import CommandPalette, MacHomePage
from creative_toolbox.platforms.macos import MacOSBackend
from creative_toolbox.platforms.unavailable import UnavailableBackend
from creative_toolbox.storage import Store
from creative_toolbox.ui import MainWindow


class MacDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name), "darwin")
        self.window = MainWindow(UnavailableBackend("darwin", "test"), self.store,
                                 self.store.load(), start_timer=False)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.quit_app()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_home_and_search_keep_tools_lazy_and_route_to_real_page(self):
        self.assertIsInstance(self.window.entry_pages["home"], MacHomePage)
        desktop = self.window.mac_desktop
        desktop.show_launcher()
        desktop.launcher.search.setText("bpm")
        self.assertEqual(desktop.launcher.results.count(), 1)
        self.assertEqual(self.window.tool_pages, {})
        QTest.keyClick(desktop.launcher.search, Qt.Key.Key_Return)
        self.assertIs(self.window.pages.currentWidget(), self.window.tool_pages["calculators"])
        self.assertTrue(self.window.tool_nav["calculators"].isChecked())
        self.assertFalse(any(nav.isChecked() for nav in self.window.nav.values()))
        self.assertEqual(self.window.workspace.data["recent"][0]["id"], "calculators")
        self.assertFalse(self.window.controller.automatic)

    def test_launcher_keyboard_navigation_and_empty_result(self):
        palette = self.window.mac_desktop.launcher
        opened = []
        palette.open_requested.connect(opened.append)
        palette.open()
        palette.search.setText("font")
        self.assertEqual(palette.results.count(), 1)
        QTest.keyClick(palette.search, Qt.Key.Key_Down)
        self.assertEqual(palette.results.currentRow(), 0)
        palette.search.setText("no-such-tool")
        QTest.keyClick(palette.search, Qt.Key.Key_Return)
        self.assertEqual(opened, [])
        self.assertTrue(palette.isVisible())
        QTest.keyClick(palette.search, Qt.Key.Key_Escape)
        self.assertFalse(palette.isVisible())

    def test_close_without_tray_then_dock_reopen_keeps_same_page(self):
        self.window.open_tool("calculators")
        page = self.window.pages.currentWidget()
        self.window.tray.hide()
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.quitting)
        self.window.mac_desktop.eventFilter(self.app, QEvent(QEvent.Type.ApplicationActivate))
        self.app.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertIs(self.window.pages.currentWidget(), page)

    def test_native_menu_roles_and_settings_navigation(self):
        actions = self.window.mac_desktop.actions
        self.assertEqual(actions["quit"].menuRole(), QAction.MenuRole.QuitRole)
        self.assertEqual(actions["settings"].menuRole(), QAction.MenuRole.PreferencesRole)
        actions["settings"].trigger()
        self.assertEqual(self.window.pages.currentIndex(), 3)
        self.assertTrue(self.window.nav["settings"].isChecked())
        actions["tools"].trigger()
        self.assertIs(self.window.pages.currentWidget(), self.window.entry_pages["tools"])

    def test_find_and_edit_use_focused_page_input(self):
        self.window.navigate("tools")
        field = self.window.entry_pages["tools"].search
        field.setText("BPM")
        self.window.mac_desktop.focus_search()
        self.app.processEvents()
        self.assertEqual(field.selectedText(), "BPM")
        self.window.mac_desktop.edit("copy")
        self.assertEqual(self.app.clipboard().text(), "BPM")
        self.window.mac_desktop.open_route("library")
        self.app.processEvents()
        self.assertTrue(self.window.resource_search.search.hasFocus())

    def test_geometry_saved_independently_of_user_resources(self):
        self.window.resize(1110, 740)
        self.window.mac_desktop.save_geometry()
        self.assertTrue((self.store.root / "window-state.ini").exists())
        self.assertFalse((self.store.root / "settings.json").exists())
        self.assertFalse((self.store.root / "fonts.json").exists())
        self.assertFalse((self.store.root / "palettes.json").exists())

    def test_backup_guard_blocks_launcher_and_quit(self):
        self.window.backup_busy = True
        self.window.mac_desktop.show_launcher()
        self.assertFalse(self.window.mac_desktop.launcher.isVisible())
        self.window.mac_desktop.actions["quit"].trigger()
        self.assertFalse(self.window.quitting)
        self.window.backup_busy = False


class MacPermissionTests(unittest.TestCase):
    def test_missing_permission_never_queries_or_posts_input(self):
        backend = MacOSBackend.__new__(MacOSBackend)
        backend.token = 0
        backend.q = Mock()
        backend.ax = Mock()
        backend.ax.AXIsProcessTrusted.return_value = False
        backend.q.CGPreflightPostEventAccess.return_value = False
        backend.q.CGPreflightListenEventAccess.return_value = False
        snapshot = backend.capture()
        self.assertFalse(snapshot.can_send)
        self.assertIn("辅助功能", snapshot.permission)
        backend.q.CGEventSourceSecondsSinceLastEventType.assert_not_called()
        backend.q.CGEventSourceKeyState.assert_not_called()
        backend.q.CGEventPostToPid.assert_not_called()
