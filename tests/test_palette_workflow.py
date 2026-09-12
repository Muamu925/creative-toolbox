import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from creative_toolbox.design_core import PaletteStore, default_library, format_color, validate_library
from creative_toolbox.design_ui import PalettePage
from creative_toolbox.palette_model import PaletteModel
from creative_toolbox.palette_widgets import export_palette_png, palette_image
from creative_toolbox.storage import Store, Settings
from creative_toolbox.ui import MainWindow
from tests.test_safety import FakeBackend


class PaletteWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_formats_are_ready_to_paste(self):
        self.assertEqual(format_color('#aBc', 'HEX（无 #）'), 'AABBCC')
        self.assertEqual(format_color('#aBc', 'hex（小写）'), '#aabbcc')
        self.assertEqual(format_color('#355e46', 'RGB 数值'), '53, 94, 70')

    def test_legacy_library_and_preferences_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'palettes.json'
            PaletteStore.write(path, default_library())
            model = PaletteModel(path)
            self.assertEqual(model.copy_format, 'HEX')
            candidate = deepcopy(model.library)
            candidate['palettes'].append({'name': '项目 B', 'colors': [{'name': '主色', 'hex': '#ABCDEF'}]})
            self.assertTrue(model.commit(candidate, 1))
            self.assertTrue(model.set_preferences(style='HEX（无 #）'))
            self.assertTrue(model.toggle_favorite(0))
            loaded = PaletteModel(path)
            self.assertEqual(loaded.selected, 1)
            self.assertEqual(loaded.copy_text(0), 'ABCDEF')
            self.assertTrue(loaded.palette['colors'][0]['favorite'])
            self.assertEqual(loaded.history, [])

    def test_oversized_library_cannot_replace_reloadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'palettes.json'
            PaletteStore.write(path, default_library())
            original = path.read_bytes()
            color = {'name': '色' * 80, 'hex': '#123456'}
            data = {'schema': 1, 'palettes': [{'name': '大色板', 'colors': [color] * 100}] * 100}
            with self.assertRaises(ValueError):
                PaletteStore.write(path, data)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(PaletteStore(path).load(), default_library())

    def test_invalid_new_fields_rejected(self):
        data = default_library()
        data['palettes'][0]['colors'][0]['favorite'] = 'true'
        with self.assertRaises(ValueError):
            validate_library(data)
        data = default_library()
        for prefs in ({'selected': 10}, {'selected': True}, {'format': 'not-a-format'}, []):
            data['preferences'] = prefs
            with self.assertRaises(ValueError):
                validate_library(data)

    def test_move_undo_and_failed_undo_preserve_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = PaletteModel(Path(tmp) / 'palettes.json')
            original = deepcopy(model.palette['colors'])
            model.move(0, 1)
            self.assertEqual(model.palette['colors'][1], original[0])
            model.set_preferences(style='RGB 数值')
            before = deepcopy(model.library)
            with patch.object(model.store, 'save', side_effect=OSError('disk full')):
                self.assertFalse(model.undo())
            self.assertEqual(model.library, before)
            self.assertEqual(len(model.history), 1)
            self.assertTrue(model.undo())
            self.assertEqual(model.palette['colors'], original)
            self.assertEqual(model.copy_format, 'RGB 数值')
            self.assertFalse(model.move(0, -1))
            self.assertFalse(model.undo())

    def test_shared_window_edit_filter_copy_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = PalettePage(Path(tmp) / 'palettes.json')
            try:
                page.show()
                page.open_floating()
                floating = page.floating
                self.app.processEvents()
                floating.format.setCurrentText('HEX（无 #）')
                self.assertEqual(page.format.currentText(), 'HEX（无 #）')
                page.model.toggle_favorite(0)
                page.edit_color(0)
                page.code.setText('#123456')
                page.name.setText('新主色')
                page.save_color()
                self.assertTrue(page.current()['colors'][0]['favorite'])
                self.assertEqual(floating.swatches[0].text(), '123456')
                floating.swatches[0].click()
                self.assertEqual(QApplication.clipboard().text(), '123456')
                floating.favorites.setChecked(True)
                self.assertEqual(len(floating.swatches), 1)
                page.remove_color(0)
                self.assertEqual(len(floating.swatches), 0)
                page.undo_button.click()
                self.assertEqual(len(floating.swatches), 1)
                self.assertEqual(floating.swatches[0].text(), '123456')
                page.add_palette('另一个项目', [])
                self.assertEqual(floating.palettes.currentIndex(), 1)
                floating.palettes.setCurrentIndex(0)
                self.assertEqual(page.palettes.currentIndex(), 0)
                page.hide()
                self.assertTrue(floating.isVisible())
                floating.close()
                page.open_floating()
                self.assertIs(floating, page.floating)
                self.assertTrue(floating.isVisible())
            finally:
                page.close()

    def test_filter_move_and_preferences_dont_reset_unsaved_editor(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = PalettePage(Path(tmp) / 'palettes.json')
            try:
                page.name.setText('未保存颜色')
                page.format.setCurrentText('RGB')
                self.assertEqual(page.name.text(), '未保存颜色')
                page.favorites_only.setChecked(True)
                self.assertIn('收藏', page.grid.itemAtPosition(0, 0).widget().text())
                page.model.toggle_favorite(3)
                self.assertEqual(page.grid.count(), 1)
                page.copy_palette()
                self.assertEqual(len(QApplication.clipboard().text().splitlines()), 5)
            finally:
                page.close()

    def test_float_pin_collapse_and_offscreen_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = PalettePage(Path(tmp) / 'palettes.json')
            try:
                page.open_floating()
                floating = page.floating
                self.app.processEvents()
                self.assertTrue(floating.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
                floating.pin.setChecked(False)
                self.assertFalse(floating.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
                floating.toggle_collapsed()
                self.assertTrue(floating.area.isHidden())
                floating.toggle_collapsed()
                self.assertFalse(floating.area.isHidden())
                floating.move(100000, 100000)
                floating.keep_on_screen()
                self.assertTrue(QApplication.primaryScreen().availableGeometry().contains(floating.frameGeometry().topLeft()))
            finally:
                page.close()

    def test_palette_operations_do_not_arm_or_change_auto_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = MainWindow(FakeBackend(), Store(Path(tmp), 'win32'), Settings(), start_timer=False)
            try:
                main.palette_page.open_floating()
                main.palette_page.model.toggle_favorite(0)
                main.palette_page.model.move(0, 1)
                self.assertFalse(main.controller.automatic)
                self.assertFalse((Path(tmp) / 'settings.json').exists())
                with patch.object(QApplication.instance(), 'quit'):
                    main.quit_app()
                self.assertFalse(main.palette_page.floating.isVisible())
            finally:
                main.quitting = True
                main.tray.hide()
                main.close()

    def test_png_export_exact_colors_names_and_empty_preserves_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            palette = {'name': '项目色卡', 'colors': [{'name': '主色', 'hex': '#123456'}]}
            path = Path(tmp) / 'colors.png'
            export_palette_png(palette, path)
            image = QImage(str(path))
            self.assertFalse(image.isNull())
            self.assertEqual(image.width(), 1200)
            self.assertEqual(image.text('Title'), '项目色卡')
            self.assertEqual(image.text('Colors'), '主色\t#123456')
            self.assertTrue(image.colorSpace().isValid())
            # A vertical scan must contain the saved sRGB swatch, not a screen sample.
            self.assertIn(QColor('#123456').rgba(), {image.pixel(100, y) for y in range(image.height())})
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                export_palette_png({'name': '空', 'colors': []}, path)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(OSError):
                export_palette_png(palette, Path(tmp) / 'missing' / 'colors.png')

    def test_long_names_and_full_palette_export_are_bounded(self):
        palette = {'name': '长标题' * 26, 'colors': [{'name': '中文名称' * 20, 'hex': '#123456'}] * 100}
        image = palette_image(palette)
        self.assertLess(image.width() * image.height(), 20_000_000)
        self.assertEqual(len(image.text('Colors').splitlines()), 100)
        self.assertGreater(image.height(), 1000)


if __name__ == '__main__':
    unittest.main()
