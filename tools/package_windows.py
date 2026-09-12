"""Bundle the complete portable directory, documentation and shipped license files."""
from pathlib import Path
from distribution import copy_distribution_docs
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / "dist" / "CreativeToolbox"
if not (output / "CreativeToolbox.exe").is_file():
    raise SystemExit("Run tools/build.py on Windows first")
copy_distribution_docs(output)
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
