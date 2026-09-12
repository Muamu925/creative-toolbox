"""Run on each target OS. macOS builds are unsigned until release credentials exist."""
import os
from pathlib import Path
import subprocess
import sys
import platform
import tomllib
import shutil
import tempfile
from distribution import copy_distribution_docs

ROOT = Path(__file__).resolve().parents[1]
# PyInstaller may replace these generated directories when rebuilding.
for generated in (ROOT / "dist", ROOT / "build", ROOT / ".runtime" / "pyinstaller-cache"):
    generated.resolve().relative_to(ROOT)
os.chdir(ROOT)
os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(ROOT / ".runtime" / "pyinstaller-cache"))
args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "CreativeToolbox", "--specpath", "build", "--distpath", "dist",
        "--workpath", "build/work", "--paths", str(ROOT)]
icon = ROOT / "assets" / "toolbox.ico"
if sys.platform == "win32" and icon.exists():
    args += ["--icon", str(icon)]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "org.creativetoolbox.desktop"]
args += ["run.py"]
subprocess.run(args, check=True)
if sys.platform == "win32":
    # Qt 6.11 uses the Windows system ICU's unversioned exports. Some Python
    # distributions put a private, version-suffixed ICU on the DLL search path;
    # PyInstaller can mistakenly collect it. Let Windows resolve its own ICU.
    import pefile
    output = (ROOT / "dist" / "CreativeToolbox").resolve()
    for library in output.rglob("icuuc.dll"):
        library.resolve().relative_to(output)
        pe = pefile.PE(str(library))
        exports = {symbol.name for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        pe.close()
        if b"ucnv_open" not in exports:
            library.unlink()
            print("Excluded incompatible private ICU; Qt will use the Windows system library.")
if sys.platform == "darwin":
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    # A fresh staging directory prevents stale docs from entering subsequent DMGs.
    with tempfile.TemporaryDirectory(prefix="dmg-", dir=ROOT / "build") as temporary:
        staging = Path(temporary)
        shutil.copytree(ROOT / "dist" / "CreativeToolbox.app", staging / "CreativeToolbox.app", symlinks=True)
        copy_distribution_docs(staging)
        subprocess.run(["hdiutil", "create", "-volname", "Creative Toolbox", "-srcfolder",
                        str(staging), "-ov", "-format", "UDZO",
                        f"dist/CreativeToolbox-{version}-macOS-{platform.machine()}-unsigned.dmg"], check=True)
