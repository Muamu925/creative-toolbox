"""Project workflow smoke with isolated sample data and an inert backend."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from creative_toolbox.assets.library import AssetStore
from creative_toolbox.design_core import default_library
from creative_toolbox.projects import ProjectStore, new_project, palette_copy, font_copy, image_reference, export_project
from creative_toolbox.platforms.unavailable import UnavailableBackend
from creative_toolbox.storage import Store
from creative_toolbox.ui import MainWindow, STYLE

app = QApplication([])
app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
app.setStyleSheet(STYLE)
temporary = tempfile.TemporaryDirectory(prefix="creative-toolbox-project-")
root = Path(temporary.name)
projects = ProjectStore(root)
p = new_project("品牌视觉设计 · 示例")
p.update(client="示例客户", due="2026-11-15", specs={"canvas": "1920 × 1080 px", "ppi": "144", "color": "sRGB"},
         delivery="提供 PNG 预览与可编辑源文件。\n按用途分别整理社交媒体与演示资料。",
         notes="独立演示资料，仅用于界面与导出验证。")
assets = AssetStore(root / "assets")
key, _ = assets.add_file(ROOT / "assets" / "toolbox.png", title="工具箱标识 · 示例参考")
p["resources"] = [image_reference(assets.library_id, assets.get(key)),
                  palette_copy(default_library()["palettes"][0]),
                  font_copy("PingFang SC", "Regular", "中文标题与正文候选")]
assets.close()
p = projects.save(p)
other = new_project("宣传视频 · 示例", "video")
other["specs"] = {"canvas": "3840 × 2160 px", "fps": "25 fps", "duration": "60 秒"}
projects.save(other)
store = Store(root, "darwin")
w = MainWindow(UnavailableBackend("darwin", "独立演示资料，创作保护未启用"), store, store.load(), False)
w.reduce_motion.setChecked(True)
w.navigate("projects")
page = w.tool_pages["projects"]
page.open_project(p["id"])
output = ROOT / "artifacts" / "projects-review"
output.mkdir(parents=True, exist_ok=True)
errors = []


def check():
    try:
        for width, height in ((1180, 800), (1020, 720)):
            w.resize(width, height)
            for tab, name in ((0, "specifications"), (1, "resources")):
                page.tabs.setCurrentIndex(tab)
                if tab:
                    page.resource_list.setCurrentRow(1)
                app.processEvents()
                w.grab().save(str(output / f"{name}-{width}.png"))
        export_project(page.current, root, output / "项目说明示例.md")
        assert "#355E46" in (output / "项目说明示例.md").read_text()
        assert page.store.get(p["id"])["resources"] == p["resources"]
        print("Project specifications, references, independent copies and export verified.", flush=True)
    except Exception as exc:
        errors.append(str(exc))
    finally:
        w.quit_app()


w.show()
QTimer.singleShot(400, check)
app.exec()
temporary.cleanup()
if errors:
    raise SystemExit("; ".join(errors))
