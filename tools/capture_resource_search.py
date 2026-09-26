"""Capture native resource-search UI with isolated sample data and inert backend."""
import tempfile
from pathlib import Path
from PySide6.QtGui import QImage, QColor, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from creative_toolbox.assets.library import AssetStore
from creative_toolbox.design_core import PaletteStore
from creative_toolbox.fonts.library import FontLibrary
from creative_toolbox.storage import Store, Settings
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.platforms.unavailable import UnavailableBackend


def main():
    app = QApplication([])
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    output = Path('artifacts/resource-review'); output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        image = QImage(320, 200, QImage.Format.Format_RGB32)
        image.fill(QColor('#245CDB')); image.save(str(root / 'sample.png'))
        assets = AssetStore(root / 'assets')
        identifier, _ = assets.add_file(root / 'sample.png', title='秋季音乐节 · 构图参考')
        assets.update(identifier, '秋季音乐节 · 构图参考', ['秋季', '海报'], '个人收集', '大标题与留白', True)
        source = dict(library_id=assets.library_id, asset_id=identifier, hash=assets.get(identifier)['hash'], title='秋季音乐节 · 构图参考')
        assets.close()
        PaletteStore(root / 'palettes.json').save(dict(schema=2, palettes=[dict(name='秋季音乐节 · 主配色', colors=[dict(name='钴蓝',hex='#245CDB'),dict(name='冷白',hex='#F3F5F9')],source_asset=source)]))
        fonts = FontLibrary(root / 'fonts.json')
        fonts.edit(['Microsoft YaHei UI'], tags=['秋季'], note='海报标题候选')
        window = MainWindow(UnavailableBackend('win32', '仅供界面演示'), Store(root, 'win32'), Settings(), start_timer=False)
        window.show(); window.navigate('library')
        for width, height in [(1180,800),(1020,720)]:
            window.resize(width,height)
            window.resource_search.search.setText('秋季')
            window.resource_search.refresh()
            for _ in range(100):
                QTest.qWait(20)
                if not window.resource_search.timer.isActive() and not window.resource_search.worker:
                    break
            QTest.qWait(250)
            window.grab().save(str(output / f'search-{width}.png'))
        window.resource_search.search.clear(); QTest.qWait(300)
        window.grab().save(str(output / 'library-empty.png'))
        window.quit_app(); window.close()
    print(output.resolve())

if __name__ == '__main__':
    main()
