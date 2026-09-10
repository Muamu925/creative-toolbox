import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication
    from creative_toolbox.ui import MainWindow, ProfileDialog, STYLE
    HAS_QT = True
except ImportError:
    HAS_QT = False

from creative_toolbox.storage import Store, Settings
from tests.test_safety import FakeBackend, profile


@unittest.skipUnless(HAS_QT, "Install desktop dependencies to exercise UI")
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def test_rule_edit_validation_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp), "win32")
            window = MainWindow(FakeBackend(), store, Settings([profile()]), start_timer=False)
            try:
                window.show()
                self.app.processEvents()
                self.assertEqual(window.profile_table.rowCount(), 1)
                window.flip_profile()
                self.assertFalse(store.load().profiles[0].enabled)
                window.global_style.setCurrentIndex(window.global_style.findData("custom"))
                window.global_custom.setText("Ctrl+Shift+S")
                window.save_preferences()
                self.assertEqual(store.load().custom, "Ctrl+Shift+S")
                window.switch_page(2)
                self.assertEqual(window.pages.currentIndex(), 2)
                self.assertGreater(window.event_table.rowCount(), 0)
                self.assertFalse(window.controller.automatic)
            finally:
                window.quitting = True
                window.tray.hide()
                window.close()

    def test_dialog_rejects_invalid_shortcut_then_accepts_override(self):
        dialog = ProfileDialog("win32", profile())
        dialog.style.setCurrentIndex(dialog.style.findData("custom"))
        dialog.custom.setText("S")
        dialog.accept_profile()
        self.assertIn("组合键", dialog.error.text())
        dialog.custom.setText("Ctrl+Alt+S")
        dialog.accept_profile()
        self.assertEqual(dialog.result_profile.custom, "Ctrl+Alt+S")
        self.assertEqual(dialog.result(), 1)


if __name__ == "__main__":
    unittest.main()
