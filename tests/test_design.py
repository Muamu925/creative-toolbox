import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from creative_toolbox.design_core import (
    PaletteStore, contrast_ratio, css_palette, default_library, format_color,
    harmony, normalize_hex, note_ms, print_mm, print_pixels, scaled_height,
    validate_library,
)


class DesignCoreTests(unittest.TestCase):
    def test_formats_and_invalid_input(self):
        self.assertEqual(normalize_hex(' #abc '), '#AABBCC')
        self.assertEqual(format_color('#ff0000', 'RGB'), 'rgb(255, 0, 0)')
        self.assertEqual(format_color('#ff0000', 'HSL'), 'hsl(0, 100%, 50%)')
        for value in ('#1234', 'red', '#GG0000', '', None, '##abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_hex(value)

    def test_wcag_reference_values(self):
        self.assertEqual(contrast_ratio('#000', '#fff'), 21)
        self.assertEqual(contrast_ratio('#fff', '#fff'), 1)
        self.assertAlmostEqual(contrast_ratio('#777', '#fff'), 4.478089, places=5)
        self.assertLess(contrast_ratio('#777', '#fff'), 4.5)
        self.assertGreater(contrast_ratio('#767676', '#fff'), 4.5)

    def test_color_harmony(self):
        self.assertEqual(harmony('#FF0000', '互补色'), ['#FF0000', '#00FFFF'])
        self.assertEqual(set(harmony('#FF0000', '三等分')), {'#FF0000', '#00FF00', '#0000FF'})
        self.assertEqual(harmony('#FFFFFF', '邻近色'), ['#FFFFFF'])

    def test_size_and_music_examples(self):
        self.assertEqual((print_pixels(210, 300), print_pixels(297, 300)), (2480, 3508))
        self.assertEqual(print_mm(300, 300), 25.4)
        self.assertEqual(scaled_height(1920, 1080, 1280), 720)
        self.assertEqual(note_ms(120, 4), 500)
        self.assertEqual(note_ms(120, 8, '附点'), 375)
        self.assertAlmostEqual(note_ms(120, 8, '三连音'), 166.6666667)
        for v in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                note_ms(v, 4)

    def test_atomic_roundtrip_and_failed_write_preserves_old_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PaletteStore(Path(tmp) / 'palettes.json')
            library = store.load()
            store.save(library)
            previous = store.path.read_bytes()
            library['palettes'][0]['name'] = '中文品牌'
            with patch('creative_toolbox.design_core.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    store.save(library)
            self.assertEqual(store.path.read_bytes(), previous)
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])
            store.save(library)
            self.assertEqual(PaletteStore(store.path).load()['palettes'][0]['name'], '中文品牌')

    def test_corrupt_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'palettes.json'
            path.write_text('{bad', encoding='utf-8')
            store = PaletteStore(path)
            store.load()
            self.assertTrue(store.warning)
            with self.assertRaises(ValueError):
                store.save(default_library())
            self.assertEqual(path.read_text(), '{bad')

    def test_import_limits_and_css_labels(self):
        for raw in ([], {'schema': 2}, {'schema': 1, 'palettes': []}, {'schema': 1, 'palettes': [None]}):
            with self.assertRaises(ValueError):
                validate_library(raw)
        library = default_library()
        library['palettes'][0]['colors'] *= 21
        with self.assertRaises(ValueError):
            validate_library(library)
        value = css_palette({'colors': [{'hex': '#abc', 'name': '*/ invalid name'}]})
        self.assertEqual(value, ':root {\n  --color-1: #AABBCC;\n}\n')


try:
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtGui import QColor, QImage
    from creative_toolbox.design_ui import PalettePage, CalculatorPage, FontPage, image_colors
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'Requires desktop dependencies')
class DesignUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_palette_edit_copy_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = PalettePage(Path(tmp) / 'palettes.json')
            page.name.setText('品牌红')
            page.code.setText('#f00')
            page.save_color()
            page.edit_color(5)
            page.code.setText('#00f')
            page.save_color()
            page.format.setCurrentText('RGB')
            card = page.grid.itemAtPosition(1, 2).widget()
            card.findChildren(QPushButton)[0].click()
            self.assertEqual(QApplication.clipboard().text(), 'rgb(0, 0, 255)')
            reloaded = PalettePage(Path(tmp) / 'palettes.json')
            self.assertEqual(reloaded.current()['colors'][5], {'name': '品牌红', 'hex': '#0000FF'})
            page.remove_color(5)
            self.assertEqual(len(page.current()['colors']), 5)
            page.close()
            reloaded.close()

    def test_failed_save_and_invalid_color_do_not_change_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = PalettePage(Path(tmp) / 'palettes.json')
            before = json.dumps(page.library)
            page.code.setText('invalid')
            page.save_color()
            self.assertEqual(json.dumps(page.library), before)
            page.code.setText('#123456')
            with patch.object(page.store, 'save', side_effect=OSError('disk error')):
                page.save_color()
            self.assertEqual(json.dumps(page.library), before)
            self.assertIn('未保存', page.status.text())
            page.close()

    def test_image_palette_and_transparency(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'image.png')
            image = QImage(16, 16, QImage.Format.Format_ARGB32)
            image.fill(QColor('#AABBCC'))
            image.save(path)
            self.assertEqual(image_colors(path), ['#AABBCC'])
            image.fill(QColor(0, 0, 0, 0))
            image.save(path)
            with self.assertRaises(ValueError):
                image_colors(path)
            with self.assertRaises(ValueError):
                image_colors(str(Path(tmp) / 'missing.png'))

    def test_calculator_updates_and_font_sample_sync(self):
        page = CalculatorPage()
        self.assertEqual(page.print_result.text(), '2480 × 3508 px')
        page.target_width.setValue(640)
        self.assertEqual(page.ratio_result.text(), '640 × 360 px')
        page.bpm.setValue(60)
        self.assertIn('1000.00 ms', page.tempo_result.text())
        font = FontPage()
        font.sample.setPlainText('测试 Aa 123')
        font.size.setValue(40)
        for preview in font.previews:
            self.assertEqual(preview.toPlainText(), '测试 Aa 123')
            self.assertIn('40pt', preview.styleSheet())
        page.close()
        font.close()


if __name__ == '__main__':
    unittest.main()
