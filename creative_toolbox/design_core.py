"""Portable design calculations and a separate, atomic palette library."""
from __future__ import annotations

import colorsys
import json
import math
import os
from pathlib import Path
import re
import tempfile


def normalize_hex(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("色号需要是文本")
    value = value.strip().removeprefix('#')
    if not re.fullmatch(r'[0-9a-fA-F]{3}|[0-9a-fA-F]{6}', value):
        raise ValueError("请输入 3 位或 6 位 HEX 色号，例如 #355E46")
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return '#' + value.upper()


def rgb(value: str) -> tuple[int, int, int]:
    value = normalize_hex(value)
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


COPY_FORMATS = ('HEX', 'HEX（无 #）', 'hex（小写）', 'RGB', 'RGB 数值', 'HSL')


def format_color(value: str, style: str = 'HEX') -> str:
    value = normalize_hex(value)
    r, g, b = rgb(value)
    if style == 'HEX（无 #）':
        return value[1:]
    if style == 'hex（小写）':
        return value.lower()
    if style == 'RGB 数值':
        return f'{r}, {g}, {b}'
    if style == 'RGB':
        return f'rgb({r}, {g}, {b})'
    if style == 'HSL':
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return f'hsl({round(h * 360) % 360}, {round(s * 100)}%, {round(l * 100)}%)'
    return value


def contrast_ratio(a: str, b: str) -> float:
    def luminance(color):
        channels = [v / 255 for v in rgb(color)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def harmony(value: str, mode: str) -> list[str]:
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb(value)))
    offsets = {'互补色': (0, .5), '邻近色': (-1/12, 0, 1/12), '三等分': (0, 1/3, 2/3)}
    colors = []
    for offset in offsets[mode]:
        values = colorsys.hls_to_rgb((h + offset) % 1, l, s)
        code = '#' + ''.join(f'{round(v * 255):02X}' for v in values)
        if code not in colors:
            colors.append(code)
    return colors


def positive(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("数值必须大于零且有限")
    return value


def print_pixels(mm: float, ppi: float) -> int:
    return math.floor(positive(mm) / 25.4 * positive(ppi) + .5)


def print_mm(px: float, ppi: float) -> float:
    return positive(px) / positive(ppi) * 25.4


def scaled_height(width: float, height: float, target_width: float) -> int:
    return math.floor(positive(height) / positive(width) * positive(target_width) + .5)


def note_ms(bpm: float, denominator: int, modifier: str = '普通') -> float:
    factor = {'普通': 1, '附点': 1.5, '三连音': 2 / 3}[modifier]
    return 60000 / positive(bpm) * 4 / positive(denominator) * factor


def validate_library(raw: object) -> dict:
    if not isinstance(raw, dict) or raw.get('schema') != 1:
        raise ValueError("不支持的配色库格式")
    palettes = raw.get('palettes')
    if not isinstance(palettes, list) or not 1 <= len(palettes) <= 100:
        raise ValueError("配色库须含 1 至 100 个色板")
    clean = []
    for palette in palettes:
        if not isinstance(palette, dict):
            raise ValueError("色板格式无效")
        name, colors = palette.get('name'), palette.get('colors')
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError("色板名称须为 1 至 80 个字符")
        if not isinstance(colors, list) or len(colors) > 100:
            raise ValueError("每个色板最多 100 个颜色")
        items = []
        for color in colors:
            if not isinstance(color, dict) or not isinstance(color.get('name'), str) or len(color['name']) > 80:
                raise ValueError("颜色名称无效或过长")
            item = {'name': color['name'], 'hex': normalize_hex(color.get('hex'))}
            if 'favorite' in color:
                if not isinstance(color['favorite'], bool):
                    raise ValueError('收藏状态必须为布尔值')
                item['favorite'] = color['favorite']
            items.append(item)
        clean.append({'name': name.strip(), 'colors': items})
    result = {'schema': 1, 'palettes': clean}
    if 'preferences' in raw:
        prefs = raw['preferences']
        if not isinstance(prefs, dict):
            raise ValueError('配色偏好格式无效')
        selected = prefs.get('selected', 0)
        style = prefs.get('format', 'HEX')
        if type(selected) is not int or not 0 <= selected < len(clean) or style not in COPY_FORMATS:
            raise ValueError('色板选择或复制格式无效')
        result['preferences'] = {'selected': selected, 'format': style}
    return result


def default_library() -> dict:
    return {'schema': 1, 'palettes': [{'name': '创作工具箱 · 森林', 'colors': [
        {'name': n, 'hex': c} for n, c in [('主色', '#355E46'), ('浅绿', '#B3CF9C'),
        ('暖白', '#F4F6F3'), ('墨色', '#203C31'), ('点缀', '#E9EDC8')]]}]}


class PaletteStore:
    def __init__(self, path: Path):
        self.path = path
        self.warning = ''
        self.read_only = False

    @staticmethod
    def read(path: Path) -> dict:
        if path.stat().st_size > 2_000_000:
            raise ValueError('配色库文件超过 2 MB')
        return validate_library(json.loads(path.read_text(encoding='utf-8')))

    def load(self) -> dict:
        if not self.path.exists():
            return default_library()
        try:
            return self.read(self.path)
        except (OSError, ValueError, TypeError) as exc:
            self.read_only = True
            self.warning = f'配色库未载入：{exc}。原文件保留；本次只读展示示例色板，请先备份并修复原文件。'
            return default_library()

    def save(self, library: dict) -> dict:
        if self.read_only:
            raise ValueError(self.warning)
        clean = validate_library(library)
        self.write(self.path, clean)
        return clean

    @staticmethod
    def write(path: Path, library: dict):
        clean = validate_library(library)
        payload = json.dumps(clean, ensure_ascii=False, indent=2)
        if len(payload.encode('utf-8')) > 2_000_000:
            raise ValueError('配色库超过 2 MB，请拆分色板后再保存')
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def css_palette(palette: dict) -> str:
    # Numbered names avoid invalid or colliding identifiers from user labels.
    rows = [f'  --color-{i}: {normalize_hex(c["hex"])};' for i, c in enumerate(palette['colors'], 1)]
    return ':root {\n' + '\n'.join(rows) + '\n}\n'
