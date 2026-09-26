"""Read-only resource discovery; no font enumeration or document migration."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from .design_core import PaletteStore
from .fonts.library import read_file


def asset_root(root):
    root = Path(root)
    pointer = root / 'asset-location.json'
    if not pointer.exists():
        return root / 'assets'
    if pointer.stat().st_size > 4096:
        raise ValueError('素材库位置设置过大')
    raw = json.loads(pointer.read_text(encoding='utf-8'))
    name = raw.get('directory')
    if raw.get('schema') != 1 or not isinstance(name, str) or not re.fullmatch(r'assets-restored-[0-9a-f]{32}', name):
        raise ValueError('素材库位置设置无效')
    result = root / name
    if not (result / 'library.sqlite3').is_file():
        raise ValueError('当前素材库目录缺失')
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def search_resources(root, query, kind='all', limit=100):
    """Return bounded per-kind results and explicit partial-failure warnings."""
    root = Path(root)
    words = query.casefold().split()
    results, warnings, counts = [], [], {}
    if not words:
        return results, warnings, counts
    def add(category, title, details, reference):
        if all(word in (title + ' ' + details).casefold() for word in words):
            counts[category] = counts.get(category, 0) + 1
            if counts[category] <= limit:
                results.append(dict(kind=category, title=title, details=details, reference=reference))
    if kind in ('all', 'assets'):
        try:
            path = asset_root(root) / 'library.sqlite3'
            if path.exists():
                db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
                db.row_factory = sqlite3.Row
                try:
                    if db.execute('PRAGMA user_version').fetchone()[0] not in (1, 2):
                        raise ValueError('不支持的素材库版本')
                    identity = db.execute("SELECT value FROM meta WHERE key='library_id'").fetchone()[0]
                    for row in db.execute('SELECT id,hash,title,tags,source,notes FROM assets WHERE deleted=0 ORDER BY created DESC, rowid DESC'):
                        details = ' '.join([*json.loads(row['tags']), row['source'], row['notes']])
                        add('assets', row['title'], details, dict(library_id=identity, asset_id=row['id'], hash=row['hash']))
                finally:
                    db.close()
        except Exception as exc:
            warnings.append('图片暂未搜索：' + str(exc))
    if kind in ('all', 'palettes'):
        try:
            path = root / 'palettes.json'
            if path.exists():
                for index, palette in enumerate(PaletteStore.read(path)['palettes']):
                    details = ' '.join(c['name'] + ' ' + c['hex'] for c in palette['colors'])
                    details += ' ' + palette.get('source_asset', {}).get('title', '')
                    add('palettes', palette['name'], details, dict(index=index, fingerprint=fingerprint(palette)))
        except Exception as exc:
            warnings.append('色板暂未搜索：' + str(exc))
    if kind in ('all', 'fonts'):
        try:
            path = root / 'fonts.json'
            if path.exists():
                library = read_file(path)
                for family, meta in library['fonts'].items():
                    details = ' '.join([meta['alias'], meta['note'], meta['source'], *meta['tags'],
                                        *[library['groups'][g] for g in meta['groups']]])
                    add('fonts', family, details, family)
        except Exception as exc:
            warnings.append('字体暂未搜索：' + str(exc))
    return results, warnings, counts
