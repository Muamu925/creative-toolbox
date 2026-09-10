"""Send one real Ctrl+S exclusively to our temporary test process, never user apps."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def receiver(marker: Path):
    from PySide6.QtCore import QTimer, Qt, QObject, QEvent
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QLineEdit
    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("Creative Toolbox — isolated save test")
    window.resize(440, 160)
    window.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout = QVBoxLayout(window)
    text = QLabel("Temporary test window. Only this window may receive the test shortcut.")
    text.setWordWrap(True)
    layout.addWidget(text)
    editor = QLineEdit("Temporary draft — Ctrl+S writes only the test marker")
    layout.addWidget(editor)

    def save():
        marker.write_text("SAVED: temporary test document\n", encoding="utf-8")
        QTimer.singleShot(300, app.quit)

    shortcut = QShortcut(QKeySequence("Ctrl+S"), window)
    shortcut.activated.connect(save)
    class Recorder(QObject):
        def eventFilter(self, obj, event):
            if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.Shortcut):
                with marker.with_suffix(".events.txt").open("a", encoding="utf-8") as stream:
                    stream.write(f"type={event.type()} key={event.key() if hasattr(event, 'key') else ''} modifiers={event.modifiers() if hasattr(event, 'modifiers') else ''}\n")
            return False
    recorder = Recorder()
    app.installEventFilter(recorder)
    window.show()
    window.activateWindow()
    window.setFocus()
    marker.with_suffix(".ready.json").write_text(json.dumps({"pid": os.getpid(), "window": int(window.winId())}), encoding="utf-8")
    # Foreground request is limited to our test window, never a user's editor.
    import ctypes
    focus = ctypes.windll.user32.SetForegroundWindow
    focus.argtypes = [ctypes.c_void_p]
    focus.restype = ctypes.c_int
    def activate():
        focus(int(window.winId()))
        window.activateWindow()
        editor.setFocus()
    QTimer.singleShot(200, activate)
    QTimer.singleShot(18000, app.quit)
    return app.exec()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--receiver":
        return receiver(Path(sys.argv[2]))
    if sys.platform != "win32":
        print("Windows-only native integration check")
        return 2
    from creative_toolbox.core import Shortcut
    from creative_toolbox.platforms.windows import WindowsBackend
    folder = ROOT / ".runtime" / "native-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "saved-test-document.txt"
    marker.unlink(missing_ok=True)
    ready = marker.with_suffix(".ready.json")
    ready.unlink(missing_ok=True)
    marker.with_suffix(".events.txt").unlink(missing_ok=True)
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--receiver", str(marker)],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    backend = WindowsBackend()
    deadline = time.monotonic() + 16
    stable_since, target_key = None, None
    last_reason = "receiver not ready"
    try:
        while time.monotonic() < deadline:
            snap = backend.capture()
            receiver_pid = json.loads(ready.read_text(encoding="utf-8"))["pid"] if ready.exists() else None
            last_reason = f"receiver={receiver_pid}, foreground={snap.target.pid if snap.target else None}, blocked={snap.blocked}, pressed={snap.pressed}, idle={snap.idle:.1f}"
            if snap.target and snap.target.pid == receiver_pid:
                if snap.target.key != target_key:
                    stable_since, target_key = time.monotonic(), snap.target.key
                if not snap.pressed and not snap.blocked and snap.idle >= 2 and time.monotonic() - stable_since >= 1:
                    ok, message = backend.send(snap, Shortcut.parse("Ctrl+S"), 2)
                    print(f"Native dispatch to isolated receiver: {ok}; {message}", flush=True)
                    time.sleep(0.2)
                    after = backend.capture()
                    print(f"After dispatch: receiver={receiver_pid}, foreground={after.target.pid if after.target else None}, input_changed={after.input_token != snap.input_token}", flush=True)
                    if not ok:
                        return 1
                    for _ in range(20):
                        if marker.exists():
                            print("PASS: receiver handled Ctrl+S and wrote the temporary document", flush=True)
                            return 0
                        time.sleep(0.1)
                    print("FAIL: no receiver acknowledgment", flush=True)
                    return 1
            else:
                stable_since, target_key = None, None
            time.sleep(0.2)
        print("BLOCKED: receiver never became an idle, eligible foreground window; no keys sent. " + last_reason, flush=True)
        return 2
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
