"""Bundle the complete portable directory, documentation and shipped license files."""
from pathlib import Path
from importlib import metadata
import shutil
import sys
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / "dist" / "CreativeToolbox"
if not (output / "CreativeToolbox.exe").is_file():
    raise SystemExit("Run tools/build.py on Windows first")
shutil.copy2(ROOT / "README.md", output / "README.md")
(output / "docs").mkdir(exist_ok=True)
shutil.copy2(ROOT / "docs" / "FEATURE_ROADMAP.md", output / "docs" / "FEATURE_ROADMAP.md")
for name in ("PySide6-Essentials", "shiboken6", "PyInstaller"):
    distribution = metadata.distribution(name)
    for entry in distribution.files or []:
        if "license" not in str(entry).lower() or not any(part.endswith(".dist-info") for part in entry.parts):
            continue
        source = Path(distribution.locate_file(entry))
        if source.is_file():
            target = output / "third-party-licenses" / name / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    destination = output / "third-party-licenses" / "Python"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_license, destination / "LICENSE.txt")
version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
archive = ROOT / "dist" / f"CreativeToolbox-{version}-Windows-x64.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
    for file in sorted(output.rglob("*")):
        if file.is_file():
            package.write(file, file.relative_to(output.parent))
with zipfile.ZipFile(archive) as package:
    if package.testzip() is not None:
        raise SystemExit("Archive verification failed")
print(f"Verified portable package: {archive.name} ({archive.stat().st_size / 1048576:.1f} MiB)")
