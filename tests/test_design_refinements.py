import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication, QPushButton
from creative_toolbox.design_ui import CalculatorPage, PalettePage
from creative_toolbox.fonts.page import FontPage


class DesignRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_palette_edit_cancel_and_export_actions(self):
        with tempfile.TemporaryDirectory() as temp:
            page = PalettePage(Path(temp) / 'palettes.json')
            self.assertFalse(page.cancel_button.isEnabled())
            page.edit_color(0)
            self.assertTrue(page.cancel_button.isEnabled())
            page.cancel_button.click()
            self.assertIsNone(page.edit_index)
            self.assertFalse(page.cancel_button.isEnabled())
            menus = [b.menu() for b in page.findChildren(QPushButton) if b.menu()]
            self.assertEqual(len(menus), 1)
            self.assertEqual([a.text() for a in menus[0].actions()],
                             ['导入 JSON', '导出 JSON', '导出 PNG', '复制 CSS'])
            page.deleteLater()
            self.app.processEvents()

    def test_calculator_units_follow_direction_and_keep_values(self):
        page = CalculatorPage()
        self.assertEqual(page.print_width.suffix(), ' mm')
        page.print_direction.setCurrentIndex(1)
        self.assertEqual(page.print_width.suffix(), ' px')
        self.assertEqual(page.print_height.suffix(), ' px')
        self.assertEqual(page.print_width.value(), 210)
        self.assertTrue(page.print_result.text().endswith('mm'))
        page.deleteLater()

    def test_font_actions_follow_selection(self):
        available = {name: {'styles': ['Regular'], 'systems': [], 'mono': False}
                     for name in ('Alpha', 'Beta', 'Gamma')}
        with tempfile.TemporaryDirectory() as temp:
            page = FontPage(Path(temp) / 'fonts.json', available=available)
            self.assertFalse(page.batch_button.isEnabled())
            self.assertFalse(page.details_button.isEnabled())
            self.assertFalse(page.compare_button.isEnabled())
            selection = page.list.selectionModel()
            selection.select(page.proxy.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
            self.assertTrue(page.batch_button.isEnabled())
            self.assertTrue(page.details_button.isEnabled())
            selection.select(page.proxy.index(1, 0), QItemSelectionModel.SelectionFlag.Select)
            self.assertFalse(page.details_button.isEnabled())
            self.assertTrue(page.compare_button.isEnabled())
            selection.clearSelection()
            self.assertFalse(page.compare_button.isEnabled())
            page.deleteLater()
            self.app.processEvents()
