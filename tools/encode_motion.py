"""Optional authoring step, using Pillow; not an app dependency."""
import json
from pathlib import Path
from PIL import Image
root=Path('artifacts/motion-frames')
records=json.loads((root/'frames.json').read_text())
frames=[]
for record in records:
    with Image.open(root/record['file']) as source:
        frames.append(source.convert('RGB').quantize(colors=160))
durations=[max(20,b['ms']-a['ms']) for a,b in zip(records,records[1:])]+[1000]
target=Path('assets/demo/interaction-demo.gif')
frames[0].save(target,save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2,optimize=False)
with Image.open(target) as check:
    assert check.n_frames>15
print('Interaction preview:',target.stat().st_size,'bytes')