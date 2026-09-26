import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from threading import Event
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from creative_toolbox.assets.library import AssetStore, Cancelled
from creative_toolbox.design_core import PaletteStore
from creative_toolbox.fonts.library import FontLibrary
from creative_toolbox.resources_search import search_resources, asset_root
from creative_toolbox.workspace_backup import export_workspace, restore_workspace, activate_workspace, resolve_workspace
from creative_toolbox.storage import Store, Settings
from creative_toolbox.ui import MainWindow
from tests.test_assets import picture
from tests.test_safety import FakeBackend


class ResourceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'data'
        self.root.mkdir()
        self.assets = AssetStore(self.root / 'assets')
        image = picture(self.base / 'image.png')
        self.asset_id, _ = self.assets.add_file(image, title='音乐节海报')
        self.assets.update(self.asset_id, '音乐节海报', ['秋季'], '作者', '构图', True)
        self.group = self.assets.save_collection('秋季项目')
        self.assets.set_collections(self.asset_id, [self.group])
        self.source = dict(library_id=self.assets.library_id, asset_id=self.asset_id,
                           hash=self.assets.get(self.asset_id)['hash'], title='音乐节海报')
        PaletteStore(self.root / 'palettes.json').save(dict(schema=2, palettes=[
            dict(name='秋季配色', colors=[dict(name='主色', hex='#245CDB')], source_asset=self.source)]))
        fonts = FontLibrary(self.root / 'fonts.json')
        fonts.edit(['Missing Test Font'], tags=['秋季'], note='标题候选')
        Store(self.root, 'win32').save(Settings())
        self.archive = self.base / 'backup.ctbackup'
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.quit_app()
            self.window.close()
        self.assets.close()
        self.temp.cleanup()

    def test_search_aggregates_unicode_and_multiple_words(self):
        rows, warnings, counts = search_resources(self.root, '秋季')
        self.assertEqual(set(counts), {'assets', 'fonts', 'palettes'})
        self.assertEqual(len(rows), 3)
        self.assertFalse(warnings)
        self.assertEqual(search_resources(self.root, '秋季 #245cdb')[0][0]['kind'], 'palettes')
        self.assertEqual(len(search_resources(self.root, '秋季', 'fonts')[0]), 1)

    def test_search_does_not_create_missing_libraries(self):
        empty = self.base / 'empty'
        empty.mkdir()
        self.assertEqual(search_resources(empty, '字体'), ([], [], {}))
        self.assertEqual(list(empty.iterdir()), [])

    def test_search_excludes_trash_and_limits_each_kind(self):
        self.assets.set_deleted(self.asset_id, True)
        rows, _, counts = search_resources(self.root, '秋季', limit=1)
        self.assertNotIn('assets', counts)
        self.assertEqual(len(rows), 2)

    def test_bad_module_is_visible_without_hiding_other_results(self):
        (self.root / 'fonts.json').write_text('{bad', encoding='utf-8')
        rows, warnings, _ = search_resources(self.root, '秋季')
        self.assertEqual(len(rows), 2)
        self.assertIn('字体', warnings[0])
        self.assertEqual((self.root / 'fonts.json').read_text(), '{bad')

    def test_full_roundtrip_preserves_bytes_identity_collections_and_links(self):
        export_workspace(self.root, self.archive)
        destination = self.base / 'restored'
        restore_workspace(self.archive, destination)
        for name in ('fonts.json', 'palettes.json', 'settings.json'):
            self.assertEqual((self.root / name).read_bytes(), (destination / name).read_bytes())
        recovered = AssetStore(destination / 'assets')
        try:
            self.assertEqual(recovered.library_id, self.assets.library_id)
            self.assertEqual(recovered.asset_collections(self.asset_id), [self.group])
            self.assertEqual(recovered.path_for(self.asset_id).read_bytes(), self.assets.path_for(self.asset_id).read_bytes())
            source = PaletteStore.read(destination / 'palettes.json')['palettes'][0]['source_asset']
            self.assertEqual(source['hash'], recovered.get(source['asset_id'])['hash'])
            self.assertEqual(len(search_resources(destination, '秋季')[0]), 3)
        finally:
            recovered.close()

    def test_backup_does_not_migrate_legacy_image_index(self):
        with self.assets.db:
            self.assets.db.execute('DROP TABLE collection_assets')
            self.assets.db.execute('DROP TABLE collections')
            self.assets.db.execute('PRAGMA user_version=1')
        before = (self.root / 'assets/library.sqlite3').read_bytes()
        export_workspace(self.root, self.archive)
        self.assertEqual((self.root / 'assets/library.sqlite3').read_bytes(), before)
        self.assertFalse((self.root / 'assets/before-collections.sqlite3').exists())
        dest = self.base / 'legacy-restored'
        restore_workspace(self.archive, dest)
        recovered = AssetStore(dest / 'assets')
        try:
            self.assertEqual(recovered.get(self.asset_id)['title'], '音乐节海报')
        finally:
            recovered.close()

    def test_active_image_library_is_backed_up_and_normalized(self):
        other = self.root / ('assets-restored-' + 'a'*32)
        export = self.base / 'images.zip'
        self.assets.export_backup(export)
        AssetStore.restore_backup(export, other)
        (self.root / 'asset-location.json').write_text(json.dumps(dict(schema=1, directory=other.name)))
        self.assertEqual(asset_root(self.root), other)
        export_workspace(self.root, self.archive)
        dest = self.base / 'restored'
        restore_workspace(self.archive, dest)
        self.assertEqual(asset_root(dest), dest / 'assets')
        self.assertEqual(len(search_resources(dest, '秋季')[0]), 3)

    def test_cancel_export_preserves_existing_archive(self):
        self.archive.write_bytes(b'previous')
        cancel = Event(); cancel.set()
        with self.assertRaises(Cancelled):
            export_workspace(self.root, self.archive, cancel)
        self.assertEqual(self.archive.read_bytes(), b'previous')
        self.assertFalse(list(self.base.glob('*.tmp')))

    def test_corrupt_metadata_never_creates_successful_backup(self):
        (self.root / 'palettes.json').write_text('{}')
        with self.assertRaises((ValueError, TypeError)):
            export_workspace(self.root, self.archive)
        self.assertFalse(self.archive.exists())

    def test_restore_tampering_and_path_injection_leave_destination_absent(self):
        export_workspace(self.root, self.archive)
        with zipfile.ZipFile(self.archive) as z:
            files = {n: z.read(n) for n in z.namelist()}
        for invalid in ({**files, 'fonts.json': b'{}'}, {**files, '../outside': b'bad'}):
            bad = self.base / 'bad.ctbackup'
            with zipfile.ZipFile(bad, 'w') as z:
                for name, content in invalid.items():
                    z.writestr(name, content)
            destination = self.base / 'failed'
            with self.assertRaises(ValueError):
                restore_workspace(bad, destination)
            self.assertFalse(destination.exists())
        self.assertFalse((self.base / 'outside').exists())

    def test_restore_never_overwrites_and_cancel_leaves_no_partial_destination(self):
        export_workspace(self.root, self.archive)
        with self.assertRaises(ValueError):
            restore_workspace(self.archive, self.root)
        cancel = Event(); cancel.set()
        dest = self.base / 'cancelled'
        with self.assertRaises(Cancelled):
            restore_workspace(self.archive, dest, cancel)
        self.assertFalse(dest.exists())

    def test_switch_persists_and_preserves_original(self):
        export_workspace(self.root, self.archive)
        destination = self.root / ('workspace-restored-' + 'b'*32)
        restore_workspace(self.archive, destination)
        original = (self.root / 'palettes.json').read_bytes()
        activate_workspace(self.root, destination)
        self.assertEqual(resolve_workspace(self.root), destination)
        self.assertEqual((self.root / 'palettes.json').read_bytes(), original)
        with self.assertRaises(ValueError):
            activate_workspace(self.root, self.base)

    def test_resource_result_opens_exact_asset_palette_and_missing_font(self):
        self.window = MainWindow(FakeBackend(), Store(self.root, 'win32'), Settings(), start_timer=False)
        rows, _, _ = search_resources(self.root, '秋季')
        with patch('creative_toolbox.fonts.page.catalog', return_value={}):
            for row in rows:
                self.window.open_resource(row)
        self.assertEqual(self.window.tool_pages['assets'].current_id, self.asset_id)
        self.assertEqual(self.window.palette_page.model.palette['name'], '秋季配色')
        self.assertEqual(self.window.font_page.selected(), ['Missing Test Font'])

    def test_changed_palette_result_never_opens_wrong_palette(self):
        self.window = MainWindow(FakeBackend(), Store(self.root, 'win32'), Settings(), start_timer=False)
        result = search_resources(self.root, '秋季', 'palettes')[0][0]
        model = self.window.palette_page.model
        candidate = json.loads(json.dumps(model.library))
        candidate['palettes'][0]['name'] = '已改名'
        model.commit(candidate)
        with patch.object(QMessageBox, 'warning') as warning:
            self.window.open_resource(result)
        warning.assert_called_once()

    def test_backup_dialog_completes_and_restore_remains_available_with_bad_current_fonts(self):
        from creative_toolbox.resource_ui import run_backup
        from PySide6.QtWidgets import QFileDialog
        self.window = MainWindow(FakeBackend(), Store(self.root, 'win32'), Settings(), start_timer=False)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.archive), '')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Ok):
            run_backup(self.window)
        self.assertTrue(self.archive.is_file())
        self.assertFalse(self.window.backup_busy)
        with patch('creative_toolbox.fonts.page.catalog', return_value={}):
            page = self.window.font_page
        page.library.read_only = True
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(self.archive), '')), \
             patch.object(QMessageBox, 'question', side_effect=[QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.No]), \
             patch.object(QMessageBox, 'information'):
            run_backup(self.window, restore=True)
        restored = list(self.root.glob('workspace-restored-*'))
        self.assertEqual(len(restored), 1)
        self.assertEqual(len(search_resources(restored[0], '秋季')[0]), 3)
        self.assertFalse((self.root / 'active-workspace.json').exists())

    def test_async_latest_query_wins_and_backup_blocks_quit(self):
        self.window = MainWindow(FakeBackend(), Store(self.root, 'win32'), Settings(), start_timer=False)
        search = self.window.resource_search
        search.search.setText('秋季')
        search.start_search()
        search.search.setText('没有这个资料')
        for _ in range(150):
            QTest.qWait(10)
            if not search.worker and not search.timer.isActive():
                break
        self.assertEqual(search.results.count(), 0)
        self.assertIn('没有找到', search.status.text())
        self.window.backup_busy = True
        self.window.quit_app()
        self.assertFalse(self.window.quitting)
        self.window.backup_busy = False

if __name__ == '__main__':
    unittest.main()
