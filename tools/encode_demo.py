"""Optional authoring tool: requires Pillow, not used by the desktop app."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
frames = [Image.open(p).convert("RGB").quantize(colors=160)
          for p in sorted((root / "artifacts" / "demo-frames").glob("*.png"))]
if len(frames) != 6:
    raise SystemExit("Run tools/capture_demo.py first; expected six frames")
output = root / "assets" / "demo" / "palette-demo.gif"
frames[0].save(output, save_all=True, append_images=frames[1:],
               duration=[2500, 2500, 2500, 2800, 2600, 3000], loop=0, disposal=2, optimize=False)
with Image.open(output) as demo:
    assert demo.n_frames == 6
print(f"Verified demo: {output.stat().st_size} bytes, six frames")
