import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton
from creative_toolbox.motion import MotionStack, NavigationMotion, FeedbackToast
from creative_toolbox.appearance import AppearanceStore
from creative_toolbox.theme import STYLE


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def stack(self):
        stack = MotionStack()
        stack.resize(600,400)
        for _ in range(3): stack.addWidget(QWidget())
        stack.show()
        self.app.processEvents()
        self.addCleanup(stack.close)
        return stack

    def test_rapid_navigation_finishes_on_latest_page(self):
        stack = self.stack()
        stack.setCurrentIndex(1)
        self.assertEqual(stack.animation.state(), QAbstractAnimation.State.Running)
        stack.setCurrentIndex(2)
        self.assertEqual(stack.currentIndex(), 2)
        self.assertTrue(stack.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        QTest.qWait(220)
        self.assertEqual(stack.currentIndex(), 2)
        self.assertFalse(stack.overlay.isVisible())
        self.assertEqual(stack.animation.state(), QAbstractAnimation.State.Stopped)

    def test_reduced_motion_cancels_current_and_future_transitions(self):
        stack = self.stack()
        stack.setCurrentIndex(1)
        stack.set_reduced_motion(True)
        self.assertFalse(stack.overlay.isVisible())
        stack.setCurrentIndex(2)
        self.assertEqual(stack.currentIndex(), 2)
        self.assertEqual(stack.animation.state(), QAbstractAnimation.State.Stopped)

    def test_resize_clears_outdated_snapshot(self):
        stack = self.stack()
        stack.setCurrentIndex(1)
        stack.resize(480,300)
        self.app.processEvents()
        self.assertFalse(stack.overlay.isVisible())
        self.assertEqual(stack.currentIndex(), 1)

    def test_navigation_marker_tracks_latest_target_and_resize(self):
        sidebar = QWidget(); sidebar.resize(190,220)
        layout = QVBoxLayout(sidebar)
        buttons = [QPushButton(name) for name in ('首页','资源库','工具')]
        for button in buttons: layout.addWidget(button)
        motion = NavigationMotion(sidebar)
        sidebar.show();self.app.processEvents()
        motion.select(buttons[0]);motion.select(buttons[1]);motion.select(buttons[2])
        QTest.qWait(210)
        self.assertEqual(motion.marker.geometry(), buttons[2].geometry())
        sidebar.resize(220,280);self.app.processEvents();self.app.processEvents()
        self.assertEqual(motion.marker.geometry(), buttons[2].geometry())
        motion.stop();sidebar.close()

    def test_toast_replaces_message_without_taking_focus(self):
        parent = QWidget();parent.resize(600,400)
        editor = QLineEdit(parent)
        parent.show();parent.activateWindow();editor.setFocus();self.app.processEvents()
        focus = self.app.focusWidget()
        toast = FeedbackToast(parent)
        toast.show_message('已复制颜色');toast.show_message('已复制尺寸')
        self.assertEqual(toast.message.text(), '已复制尺寸')
        self.assertIs(self.app.focusWidget(), focus)
        self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        toast.dismiss();QTest.qWait(180)
        self.assertFalse(toast.isVisible())
        self.assertFalse(toast.timer.isActive())
        parent.close()

    def test_reduced_toast_still_reports_result_without_animation(self):
        parent=QWidget();parent.resize(500,400);parent.show()
        toast=FeedbackToast(parent, reduced=True)
        toast.show_message('已保存')
        self.assertTrue(toast.isVisible())
        self.assertEqual(toast.animation.state(), QAbstractAnimation.State.Stopped)
        toast.dismiss();self.assertFalse(toast.isVisible());parent.close()

    def test_legacy_appearance_upgrades_optional_motion_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'appearance.json'
            path.write_text(json.dumps({'schema':1,'reduced_transparency':True}))
            store=AppearanceStore(path)
            self.assertTrue(store.reduced)
            self.assertFalse(store.reduced_motion)
            store.save(True,True)
            loaded=AppearanceStore(path)
            self.assertTrue(loaded.reduced_motion)
            loaded.save(False)
            self.assertTrue(AppearanceStore(path).reduced_motion)

    def test_invalid_motion_data_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'appearance.json'
            raw='{"schema":1,"reduced_transparency":false,"reduced_motion":"no"}'
            path.write_text(raw)
            store=AppearanceStore(path)
            self.assertTrue(store.read_only)
            self.assertFalse(store.save(False,True))
            self.assertEqual(path.read_text(),raw)

    def test_calculation_copy_provides_actual_result_and_feedback(self):
        from creative_toolbox.design_ui import CalculatorPage
        page=CalculatorPage();messages=[];page.feedback.connect(messages.append)
        page.copy_result(page.print_result.text())
        self.assertEqual(self.app.clipboard().text(),page.print_result.text())
        self.assertEqual(messages,['已复制结果'])
        self.assertEqual(page.copy_status.text(),'已复制结果')
        page.close()

    def test_palette_save_failure_does_not_emit_success_feedback(self):
        from creative_toolbox.design_ui import PalettePage
        with tempfile.TemporaryDirectory() as tmp:
            page=PalettePage(Path(tmp)/'palettes.json');messages=[];page.feedback.connect(messages.append)
            with patch.object(page.model.store,'save',side_effect=OSError('disk full')):
                self.assertFalse(page.model.toggle_favorite(0))
            self.assertFalse(messages)
            self.assertIn('未保存',page.status.text())
            self.assertTrue(page.model.toggle_favorite(0))
            self.assertEqual(len(messages),1)
            page.close()