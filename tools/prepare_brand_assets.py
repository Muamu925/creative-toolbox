"""Rebuild PNG, ICO and ICNS from the generated master and licensed SVG sources. Run from repo root."""
from pathlib import Path
import struct
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
root = Path.cwd()
master = root/'assets/toolbox-master.png'

resources = root/'creative_toolbox/resources'
resources.mkdir(exist_ok=True)
im = QImage(str(master))
assert not im.isNull()
def png(size):
    img = im.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray(); buf = QBuffer(data); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    assert img.save(buf, 'PNG'); return bytes(data)
(root/'assets/toolbox.png').write_bytes(png(256))
for size in (16,24,32,48,64,128,256,512):
    (resources/f'toolbox-{size}.png').write_bytes(png(size))
sizes = (16,24,32,48,64,128,256)
blobs = [png(s) for s in sizes]
offset = 6 + 16*len(sizes)
entries = []
for size, blob in zip(sizes, blobs):
    entries.append(struct.pack('<BBBBHHII', size if size<256 else 0,size if size<256 else 0,0,0,1,32,len(blob),offset)); offset += len(blob)
(root/'assets/toolbox.ico').write_bytes(struct.pack('<HHH',0,1,len(sizes))+b''.join(entries)+b''.join(blobs))
chunks = []
for kind, size in ((b'icp4',16),(b'icp5',32),(b'icp6',64),(b'ic07',128),(b'ic08',256),(b'ic09',512),(b'ic10',1024)):
    blob = png(size); chunks.append(kind+struct.pack('>I',len(blob)+8)+blob)
body = b''.join(chunks)
(root/'assets/toolbox.icns').write_bytes(b'icns'+struct.pack('>I',len(body)+8)+body)
icons = {'home':'house','library':'folders','tools':'squares-four','protection':'timer','settings':'gear-six','help':'question','assets':'images','fonts':'text-aa','palettes':'palette','calculators':'ruler','caret-down':'caret-down','caret-up':'caret-up','check':'check'}
source = root/'assets/icons'; source.mkdir(exist_ok=True)
for key, name in icons.items():
    svg = (source/f'{name}.svg').read_bytes()
    renderer = QSvgRenderer(svg.replace(b'currentColor', b'#FFFFFF' if name == 'check' else b'#526078'))
    assert renderer.isValid(), name
    icon = QImage(64,64,QImage.Format.Format_ARGB32_Premultiplied); icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon); renderer.render(painter); painter.end()
    assert icon.save(str(resources/f'{key}.png'))
print('Application and navigation icons rebuilt from local sources.')
