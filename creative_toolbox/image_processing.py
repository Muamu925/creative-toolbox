"""Bounded image color extraction shared by palette and asset tools."""
from collections import Counter
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImageReader, QColorSpace

def image_colors(path: str) -> list[str]:
    """Bounded sRGB thumbnail histogram; an approximate palette, not ICC proofing."""
    reader = QImageReader(path)
    try:
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 40_000_000:
            raise ValueError('请选择不超过 4000 万像素的图片')
        reader.setScaledSize(size.scaled(QSize(160, 160), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            raise ValueError('无法读取图片：' + reader.errorString())
    finally:
        if reader.device() is not None:
            reader.device().close()
    if image.colorSpace().isValid():
        image.convertToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    image = image.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    counts, sums = Counter(), {}
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() < 128:
                continue
            values = (color.red(), color.green(), color.blue())
            key = tuple(v // 32 for v in values)
            counts[key] += 1
            total = sums.setdefault(key, [0, 0, 0])
            for i, v in enumerate(values):
                total[i] += v
    if not counts:
        raise ValueError('图片没有可提取的不透明颜色')
    return ['#' + ''.join(f'{round(v / count):02X}' for v in sums[key])
            for key, count in counts.most_common(6)]
