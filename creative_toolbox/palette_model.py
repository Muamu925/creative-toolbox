"""Shared palette state for the workspace and its floating window."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .design_core import PaletteStore, format_color


class PaletteModel(QObject):
    changed = Signal(bool)  # True when document changes should reset the editor.
    message = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.store = PaletteStore(path)
        self.library = self.store.load()
        self.history = []

    @property
    def selected(self):
        return self.library.get('preferences', {}).get('selected', 0)

    @property
    def copy_format(self):
        return self.library.get('preferences', {}).get('format', 'HEX')

    @property
    def palette(self):
        return self.library['palettes'][self.selected]

    def commit(self, candidate, selected=None):
        candidate = deepcopy(candidate)
        index = self.selected if selected is None else selected
        candidate['preferences'] = {'selected': index, 'format': self.copy_format}
        old = (deepcopy(self.library['palettes']), self.selected)
        if not self._save(candidate):
            return False
        self.history.append(old)
        self.history = self.history[-20:]
        self.changed.emit(True)
        self.message.emit('已保存 · 可撤销')
        return True

    def _save(self, candidate):
        try:
            clean = self.store.save(candidate)
        except (ValueError, OSError) as exc:
            self.message.emit(f'未保存：{exc}')
            return False
        self.library = clean
        return True

    def set_preferences(self, selected=None, style=None):
        index = self.selected if selected is None else selected
        style = self.copy_format if style is None else style
        if index == self.selected and style == self.copy_format:
            return True
        candidate = deepcopy(self.library)
        candidate['preferences'] = {'selected': index, 'format': style}
        reset = index != self.selected
        if not self._save(candidate):
            self.changed.emit(False)  # Restore both view controls to the saved value.
            return False
        self.changed.emit(reset)
        return True

    def undo(self):
        if not self.history:
            return False
        palettes, index = self.history[-1]
        candidate = deepcopy(self.library)
        candidate['palettes'] = deepcopy(palettes)
        candidate['preferences'] = {'selected': index, 'format': self.copy_format}
        if not self._save(candidate):
            return False
        self.history.pop()
        self.changed.emit(True)
        self.message.emit('已撤销上一次修改')
        return True

    def toggle_favorite(self, index):
        candidate = deepcopy(self.library)
        color = candidate['palettes'][self.selected]['colors'][index]
        color['favorite'] = not color.get('favorite', False)
        return self.commit(candidate)

    def move(self, index, offset):
        candidate = deepcopy(self.library)
        colors = candidate['palettes'][self.selected]['colors']
        target = index + offset
        if not 0 <= target < len(colors):
            return False
        colors.insert(target, colors.pop(index))
        return self.commit(candidate)

    def copy_text(self, index):
        return format_color(self.palette['colors'][index]['hex'], self.copy_format)

    def source_palettes(self, library_id, asset_id):
        return [(index, palette["name"]) for index, palette in enumerate(self.library["palettes"])
                if palette.get("source_asset", {}).get("library_id") == library_id
                and palette.get("source_asset", {}).get("asset_id") == asset_id]

    def add_from_asset(self, name, colors, source):
        candidate = deepcopy(self.library)
        candidate["schema"] = 2
        candidate["palettes"].append({"name": name, "colors": [
            {"name": f"主色 {index}", "hex": code} for index, code in enumerate(colors, 1)],
            "source_asset": deepcopy(source)})
        return self.commit(candidate, len(candidate["palettes"]) - 1)
