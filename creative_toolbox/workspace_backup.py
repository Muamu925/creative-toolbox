"""Consistent full-workspace archives. Caller holds the UI write barrier."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
from .assets.library import AssetStore, check_cancel, MAX_LIBRARY_BYTES, MAX_DATABASE_BYTES
from .resources_search import asset_root

METADATA = ('palettes.json', 'fonts.json', 'settings.json', 'workspace.json', 'appearance.json')
MAX_META = 8 * 1024**2
MAX_ARCHIVE = MAX_LIBRARY_BYTES + MAX_DATABASE_BYTES + 128 * 1024**2


def validate_metadata(root):
    from .design_core import PaletteStore
    from .fonts.library import read_file
    from .workspace import WorkspaceStore
    from .appearance import AppearanceStore
    from .storage import Store
    import sys
    if (root / 'palettes.json').exists():
        PaletteStore.read(root / 'palettes.json')
    if (root / 'fonts.json').exists():
        read_file(root / 'fonts.json')
    for cls, name in ((WorkspaceStore, 'workspace.json'), (AppearanceStore, 'appearance.json')):
        store = cls(root / name)
        if store.read_only:
            raise ValueError(store.warning)
    store = Store(root, sys.platform)
    store.load()
    if store.warning:
        raise ValueError(store.warning)


def copy_stream(source, target, cancel=None, maximum=MAX_ARCHIVE):
    digest, size = hashlib.sha256(), 0
    while chunk := source.read(1024 * 1024):
        check_cancel(cancel)
        size += len(chunk)
        if size > maximum:
            raise ValueError('备份内容超过大小限制')
        digest.update(chunk)
        target.write(chunk)
    return size, digest.hexdigest()


def export_workspace(root, output, cancel=None, progress=lambda d, t: None):
    root, output = Path(root), Path(output)
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError('请将备份保存到当前数据目录以外')
    fd, stage = tempfile.mkstemp(dir=output.parent, suffix='.tmp')
    os.close(fd)
    try:
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            snapshot = Path(temporary)
            for name in METADATA:
                path = root / name
                if path.exists():
                    if path.is_symlink() or path.stat().st_size > MAX_META:
                        raise ValueError('配置文件无效或过大：' + name)
                    (snapshot / name).write_bytes(path.read_bytes())
            validate_metadata(snapshot)
            assets = asset_root(root)
            if (assets / 'library.sqlite3').exists():
                store = AssetStore.open_readonly(assets)
                try:
                    store.export_backup(snapshot / 'assets.zip', cancel, progress)
                finally:
                    store.close()
            entries = []
            with zipfile.ZipFile(stage, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for path in sorted(snapshot.iterdir()):
                    check_cancel(cancel)
                    with path.open('rb') as source, archive.open(path.name, 'w', force_zip64=True) as target:
                        size, digest = copy_stream(source, target, cancel)
                    entries.append(dict(path=path.name, size=size, sha256=digest))
                archive.writestr('manifest.json', json.dumps(dict(format='creative-toolbox-workspace', schema=1, files=entries)))
            check_cancel(cancel)
            os.replace(stage, output)
    finally:
        Path(stage).unlink(missing_ok=True)
    return output


def restore_workspace(archive_path, destination, cancel=None, progress=lambda d, t: None):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('恢复目标必须为新目录，现有资料不会被覆盖')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='workspace-restore-') as temporary:
        stage = Path(temporary)
        restored = stage / 'data'
        restored.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            allowed = set(METADATA) | {'assets.zip', 'manifest.json'}
            if len(names) != len(set(names)) or not set(names) <= allowed or 'manifest.json' not in names:
                raise ValueError('备份包含重复或不允许的文件')
            if archive.getinfo('manifest.json').file_size > 16384:
                raise ValueError('备份清单过大')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('format') != 'creative-toolbox-workspace' or manifest.get('schema') != 1:
                raise ValueError('请选择工具箱完整备份')
            entries = manifest.get('files')
            if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
                raise ValueError('备份清单无效')
            expected = [e.get('path') for e in entries]
            if any(not isinstance(n, str) for n in expected) or len(expected) != len(set(expected)) or set(expected) != set(names) - {'manifest.json'}:
                raise ValueError('备份清单不匹配')
            total = 0
            for entry in entries:
                name, size = entry['path'], entry.get('size')
                maximum = MAX_ARCHIVE if name == 'assets.zip' else MAX_META
                if type(size) is not int or not 0 <= size <= maximum or archive.getinfo(name).file_size != size:
                    raise ValueError('备份大小无效')
                total += size
                if total > MAX_ARCHIVE:
                    raise ValueError('完整备份超限')
                target_path = (stage if name == 'assets.zip' else restored) / name
                with archive.open(name) as source, target_path.open('wb') as target:
                    written, digest = copy_stream(source, target, cancel, size)
                if written != size or digest != entry.get('sha256'):
                    raise ValueError('备份校验失败，未切换资料')
        validate_metadata(restored)
        if (stage / 'assets.zip').exists():
            AssetStore.restore_backup(stage / 'assets.zip', restored / 'assets', cancel, progress)
        check_cancel(cancel)
        os.replace(restored, destination)
    return destination


def resolve_workspace(base):
    base = Path(base)
    pointer = base / 'active-workspace.json'
    if not pointer.exists():
        return base
    if pointer.stat().st_size > 4096:
        raise ValueError('工作空间位置设置过大')
    raw = json.loads(pointer.read_text(encoding='utf-8'))
    name = raw.get('directory')
    if raw.get('schema') != 1 or not isinstance(name, str) or not re.fullmatch(r'workspace-restored-[0-9a-f]{32}', name):
        raise ValueError('工作空间位置设置无效')
    target = base / name
    if not target.is_dir() or target.is_symlink():
        raise ValueError('恢复的工作空间缺失')
    return target


def activate_workspace(base, restored):
    base, restored = Path(base).resolve(), Path(restored).resolve()
    if restored.parent != base or not re.fullmatch(r'workspace-restored-[0-9a-f]{32}', restored.name) or not restored.is_dir():
        raise ValueError('恢复工作空间位置无效')
    validate_metadata(restored)
    fd, name = tempfile.mkstemp(dir=base, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(schema=1, directory=restored.name), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, base / 'active-workspace.json')
    finally:
        Path(name).unlink(missing_ok=True)
