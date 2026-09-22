"""Capture collection, linked palette and offline help flows with isolated sample data."""
import os
os.environ.pop("QT_QPA_PLATFORM", None)
import tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from creative_toolbox.image_processing import image_colors
from tools.capture_assets import sample, DemoBackend

OUT = Path("assets/demo")
ART = Path("artifacts/resource-review")
OUT.mkdir(parents=True, exist_ok=True)
ART.mkdir(parents=True, exist_ok=True)


def main():
    app = QApplication([])
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Microsoft YaHei UI" if os.name == "nt" else "PingFang SC", 10))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        window = MainWindow(DemoBackend(), Store(root / "data", DemoBackend.platform), Settings(), start_timer=False)
        window.open_tool("assets")
        page = window.tool_pages["assets"]
        group = page.store.save_collection("秋日音乐节 · 海报")
        other = page.store.save_collection("自然色调")
        ids = []
        for index, (name, bg, accent, word) in enumerate([
            ("主视觉 · 森林与留白", "#d7dfce", "#748e68", "AUTUMN"),
            ("封面 · 暖色方向", "#eadfc5", "#b48768", "NATURE"),
            ("片头 · 节奏构图", "#e9d7d2", "#c88470", "RHYTHM"),
        ]):
            path = root / f"sample-{index}.png"
            sample(path, bg, accent, word, index == 0)
            identifier, _ = page.store.add_file(path)
            page.store.update(identifier, name, ["海报", "自然"], "程序绘制示例 · 非外部作品", "观察色彩比例与标题留白。", index == 0)
            page.store.set_collections(identifier, [group, other] if index == 0 else [group])
            ids.append(identifier)
        page.reload_collections(group)
        page.refresh(selected=ids[0])
        record = page.store.get(ids[0])
        window.palette_page.model.add_from_asset("秋日音乐节 · 参考配色",
            image_colors(str(page.store.path_for(ids[0], True))),
            dict(library_id=page.store.library_id, asset_id=ids[0], hash=record["hash"], title=record["title"]))
        states = []
        for width, height in ((1180, 800), (1020, 720)):
            states.extend([
                ("assets", width, height, lambda: window.open_tool("assets")),
                ("help", width, height, lambda: window.open_help("assets")),
                ("palette", width, height, lambda: window.open_tool("palettes")),
            ])
        states.append(("help-empty", 1020, 720, lambda: (window.open_help(), window.help_page.search.setText("找不到的帮助xyz"))))
        window.show()

        def step():
            if not states:
                window.quit_app()
                return
            name, width, height, navigate = states.pop(0)
            navigate()
            window.resize(width, height)
            def capture():
                window.grab().save(str(ART / f"{name}-{width}.png"))
                if width == 1180:
                    target = {"assets": "asset-inbox.png", "help": "help-center.png", "palette": "asset-palette.png"}.get(name)
                    if target:
                        window.grab().save(str(OUT / target))
                QTimer.singleShot(80, step)
            QTimer.singleShot(160, capture)
        QTimer.singleShot(180, step)
        app.exec()


if __name__ == "__main__":
    main()
