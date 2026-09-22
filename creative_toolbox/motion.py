"""Short, interruptible feedback animations. No animation runs while idle."""
from PySide6.QtCore import Qt, QEvent, QObject, QPropertyAnimation, QEasingCurve, QTimer, QAbstractAnimation
from PySide6.QtWidgets import QStackedWidget, QLabel, QFrame, QVBoxLayout, QGraphicsOpacityEffect


class MotionStack(QStackedWidget):
    """Show the destination immediately while the outgoing snapshot fades away."""
    def __init__(self, reduced=False, parent=None):
        super().__init__(parent)
        self.reduced_motion = reduced
        self.overlay = QLabel(self)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.setScaledContents(True)
        self.overlay.hide()
        self.effect = QGraphicsOpacityEffect(self.overlay)
        self.overlay.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b'opacity', self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self.finish_transition)

    def finish_transition(self):
        self.animation.stop()
        self.overlay.hide()
        self.overlay.clear()

    def set_reduced_motion(self, reduced):
        self.reduced_motion = reduced
        if reduced:
            self.finish_transition()

    def setCurrentWidget(self, widget):
        self.setCurrentIndex(self.indexOf(widget))

    def setCurrentIndex(self, index):
        if index < 0 or index >= self.count() or index == self.currentIndex():
            return
        self.finish_transition()
        animate = self.isVisible() and not self.reduced_motion and self.currentWidget() is not None
        previous = None
        if animate:
            parent = self.parentWidget()
            previous = parent.grab(self.geometry()) if parent is not None else self.grab()
        super().setCurrentIndex(index)
        if previous is not None and not previous.isNull():
            self.overlay.setPixmap(previous)
            self.overlay.setGeometry(self.rect())
            self.effect.setOpacity(1.0)
            self.overlay.show()
            self.overlay.raise_()
            self.animation.setStartValue(1.0)
            self.animation.setEndValue(0.0)
            self.animation.start()

    def resizeEvent(self, event):
        self.finish_transition()
        super().resizeEvent(event)

    def hideEvent(self, event):
        self.finish_transition()
        super().hideEvent(event)


class NavigationMotion(QObject):
    def __init__(self, sidebar, reduced=False):
        super().__init__(sidebar)
        self.sidebar, self.target = sidebar, None
        self.reduced_motion = reduced
        self.marker = QFrame(sidebar)
        self.marker.setObjectName('navSelection')
        self.marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.marker.hide()
        self.animation = QPropertyAnimation(self.marker, b'geometry', self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.sync_geometry)
        sidebar.installEventFilter(self)

    def select(self, button):
        self.target = button
        target = button.geometry()
        previous = self.marker.geometry()
        animate = self.marker.isVisible() and self.sidebar.isVisible() and not self.reduced_motion
        # Long jumps between main navigation and utilities should not sweep across the sidebar.
        animate = animate and abs(previous.y() - target.y()) < 220
        self.animation.stop()
        self.marker.show()
        self.marker.lower()
        if animate and previous != target:
            self.animation.setStartValue(previous)
            self.animation.setEndValue(target)
            self.animation.start()
        else:
            self.marker.setGeometry(target)

    def sync_geometry(self):
        if self.target is None:
            return
        target = self.target.geometry()
        if self.animation.state() == QAbstractAnimation.State.Running and self.animation.endValue() == target:
            return
        self.animation.stop()
        self.marker.setGeometry(target)

    def set_reduced_motion(self, reduced):
        self.reduced_motion = reduced
        if reduced:
            self.animation.stop()
            self.sync_geometry()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self.layout_timer.start(0)
        return False

    def stop(self):
        self.animation.stop()
        self.layout_timer.stop()


class FeedbackToast(QFrame):
    """One non-blocking, replaceable result message; underlying status stays readable."""
    def __init__(self, parent, reduced=False):
        super().__init__(parent)
        self.reduced_motion = reduced
        self.setObjectName('feedbackToast')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setAccessibleName('操作结果')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(self.message)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b'opacity', self)
        self.animation.setDuration(130)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.animation.finished.connect(self.animation_finished)
        parent.installEventFilter(self)
        self.hide()

    def place(self):
        width = min(380, max(160, self.message.fontMetrics().horizontalAdvance(self.message.text()) + 34),
                    max(160, self.parentWidget().width() - 48))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(self.parentWidget().width() - self.width() - 24,
                  max(12, self.parentWidget().height() - self.height() - 48))

    def show_message(self, message):
        self.animation.stop()
        self.timer.stop()
        self.message.setText(message)
        self.place()
        self.show()
        self.raise_()
        self.effect.setOpacity(1.0 if self.reduced_motion else .25)
        if not self.reduced_motion:
            self.animation.setStartValue(.25)
            self.animation.setEndValue(1.0)
            self.animation.start()
        self.timer.start(2600)

    def dismiss(self):
        self.timer.stop()
        self.animation.stop()
        if self.reduced_motion:
            self.hide()
        else:
            self.animation.setStartValue(self.effect.opacity())
            self.animation.setEndValue(0.0)
            self.animation.start()

    def animation_finished(self):
        if self.effect.opacity() <= .01:
            self.hide()

    def set_reduced_motion(self, reduced):
        self.reduced_motion = reduced
        if reduced:
            fading_out = self.animation.state() == QAbstractAnimation.State.Running and self.animation.endValue() == 0.0
            self.animation.stop()
            self.effect.setOpacity(1.0)
            if fading_out:
                self.hide()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self.place()
        return False

    def stop(self):
        self.timer.stop()
        self.animation.stop()
        self.hide()