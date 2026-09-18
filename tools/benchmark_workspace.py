"""Measure first render and first font opening in isolated data (never sends keys).

Run: python -m tools.benchmark_workspace
Use --offscreen only for CI diagnostics; native and offscreen numbers differ.
"""
import argparse
import json
import os
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--offscreen", action="store_true")
args = parser.parse_args()
if args.offscreen:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
else:
    os.environ.pop("QT_QPA_PLATFORM", None)

start = time.perf_counter()
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from creative_toolbox.core import Snapshot


class ReadOnlyBackend:
    platform = "win32" if os.name == "nt" else "darwin"
    label = "启动基准 / 不发送按键"
    def capture(self):
        return Snapshot(None, 0, 0, can_send=False)
    def send(self, *_):
        raise AssertionError("Benchmark must never send keys")


app = QApplication([])
app.setStyleSheet(STYLE)
loaded = time.perf_counter()
with tempfile.TemporaryDirectory() as tmp:
    window = MainWindow(ReadOnlyBackend(), Store(Path(tmp), ReadOnlyBackend.platform),
                        Settings(), start_timer=False)
    built = time.perf_counter()
    window.show()
    app.processEvents()
    shown = time.perf_counter()
    initial_tools = list(window.tool_pages)
    window.open_tool("fonts")
    app.processEvents()
    font_shown = time.perf_counter()
    print(json.dumps({
        "platform": ReadOnlyBackend.platform, "offscreen": args.offscreen,
        "import_and_qt_ms": round((loaded-start)*1000, 1),
        "window_ms": round((built-loaded)*1000, 1),
        "first_render_ms": round((shown-start)*1000, 1),
        "first_fonts_ms": round((font_shown-shown)*1000, 1),
        "startup_loaded_tools": initial_tools,
        "font_families": len(window.font_page.model.available),
    }), flush=True)
    window.quit_app()
    window.close()
