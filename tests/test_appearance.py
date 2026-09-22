import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from creative_toolbox.appearance import AppearanceStore


class AppearanceTests(unittest.TestCase):
    def test_roundtrip_separate_from_existing_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = root / 'settings.json'
            rules.write_text('original save rules')
            path = root / 'appearance.json'
            self.assertFalse(AppearanceStore(path).reduced)
            self.assertTrue(AppearanceStore(path).save(True))
            self.assertTrue(AppearanceStore(path).reduced)
            self.assertEqual(rules.read_text(), 'original save rules')

    def test_unreadable_and_future_preferences_are_preserved(self):
        for content in ('broken', '{"schema":2}', '[]', '{"schema":1,"reduced_transparency":1}', 'x'*4097):
            with self.subTest(content=content[:40]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'appearance.json'
                path.write_text(content)
                store = AppearanceStore(path)
                self.assertTrue(store.read_only)
                self.assertFalse(store.save(True))
                self.assertEqual(path.read_text(), content)

    def test_failed_atomic_replace_preserves_last_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'appearance.json'
            store = AppearanceStore(path)
            store.save(False)
            before = path.read_bytes()
            with patch('creative_toolbox.appearance.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.save(True)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(store.reduced)
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])


class AppearanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from creative_toolbox.theme import STYLE
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def make_window(self, root):
        from creative_toolbox.ui import MainWindow
        from creative_toolbox.storage import Store, Settings
        from creative_toolbox.platforms.unavailable import UnavailableBackend
        return MainWindow(UnavailableBackend('win32', 'test'), Store(root, 'win32'), Settings(), False)

    def test_appearance_toggle_updates_shell_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            window = self.make_window(root)
            window.reduce_transparency.setChecked(True)
            for surface in (window.canvas, window.sidebar_material, window.top_material):
                self.assertTrue(surface.reduced)
            self.assertIn('已保存', window.appearance_notice.text())
            window.quit_app()
            reopened = self.make_window(root)
            self.assertTrue(reopened.reduce_transparency.isChecked())
            self.assertTrue(reopened.sidebar_material.reduced)
            reopened.quit_app()

    def test_failed_preference_save_keeps_session_change_and_explains(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = self.make_window(Path(tmp))
            with patch.object(window.appearance, 'save', side_effect=OSError()):
                window.reduce_transparency.setChecked(True)
            self.assertTrue(window.canvas.reduced)
            self.assertIn('未能保存', window.appearance_notice.text())
            window.quit_app()

    def test_navigation_icons_and_app_sizes_are_real_images(self):
        from creative_toolbox.theme import icon, application_icon, RESOURCES
        from PySide6.QtGui import QImage
        for name in ('home','library','tools','settings','help','assets','fonts','palettes','calculators','protection','caret-down','caret-up','check'):
            self.assertFalse(icon(name).pixmap(20, 20).isNull(), name)
        for size in (16,24,32,48,64,128,256,512):
            image = QImage(str(RESOURCES / f'toolbox-{size}.png'))
            self.assertEqual(image.width(), size)
            self.assertEqual(image.height(), size)
        self.assertFalse(application_icon().pixmap(32,32).isNull())

    def test_filter_label_fits_when_focused(self):
        from PySide6.QtWidgets import QCheckBox
        check = QCheckBox('仅收藏')
        check.show()
        check.setFocus()
        self.app.processEvents()
        # Enough room for the full text, a 17 px indicator and an 8 px gap.
        self.assertGreaterEqual(check.sizeHint().width(), check.fontMetrics().horizontalAdvance(check.text()) + 25)
        check.close()

    def test_text_and_primary_action_contrast(self):
        from creative_toolbox.theme import TOKENS
        from creative_toolbox.design_core import contrast_ratio
        for ink, paper in (('ink','surface'),('muted','canvas'),('accent','surface'),('accent','tint')):
            self.assertGreaterEqual(contrast_ratio(TOKENS[ink], TOKENS[paper]), 4.5)