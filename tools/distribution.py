"""Include offline documentation and the licenses supplied by build dependencies."""
from importlib import metadata
from pathlib import Path
import shutil
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]


def copy_distribution_docs(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in ("README.md", "README.en.md", "CONTRIBUTING.md", "LICENSE"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copytree(ROOT / "docs", output / "docs", dirs_exist_ok=True)
    shutil.copytree(ROOT / "assets" / "demo", output / "assets" / "demo", dirs_exist_ok=True)
    names = {"PySide6-Essentials", "shiboken6", "PyInstaller"}
    names.update(d.metadata["Name"] for d in metadata.distributions()
                 if d.metadata.get("Name", "").lower().startswith("pyobjc"))
    manifest = ["Bundled third-party components retain their own licenses.",
                "The project MIT license does not replace these licenses.", ""]
    for name in sorted(names):
        distribution = metadata.distribution(name)
        manifest.append(f"{name} {distribution.version}")
        for entry in distribution.files or []:
            # Preserve relative paths so license files with identical names do not collide.
            if "license" not in str(entry).lower():
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file() or ".." in entry.parts:
                continue
            target = output / "third-party-licenses" / name / str(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for source in (Path(sys.base_prefix) / "LICENSE.txt",
                   Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"):
        if source.is_file():
            target = output / "third-party-licenses" / "Python" / "LICENSE.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            break
    manifest += [f"Python {sys.version.split()[0]}", "",
                 "Upstream sources and license information:",
                 "https://www.python.org/downloads/source/",
                 "https://code.qt.io/cgit/pyside/pyside-setup.git/",
                 "https://code.qt.io/cgit/qt/",
                 "https://doc.qt.io/qtforpython-6/licenses.html",
                 "https://github.com/ronaldoussoren/pyobjc",
                 "https://github.com/pyinstaller/pyinstaller"]
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
