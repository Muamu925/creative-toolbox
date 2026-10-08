# Run through tools/build.py on macOS. Keep bundle metadata with the source.
from pathlib import Path
import tomllib

root = Path(SPECPATH).parent
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
a = Analysis(
    [str(root / "run.py")], pathex=[str(root)],
    datas=[(str(root / "creative_toolbox" / "resources"), "creative_toolbox/resources")],
    binaries=[], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CreativeToolbox",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CreativeToolbox")
app = BUNDLE(coll, name="CreativeToolbox.app", icon=str(root / "assets" / "toolbox.icns"),
             bundle_identifier="org.creativetoolbox.desktop", version=version,
             info_plist={
                 "CFBundleDisplayName": "创作工具箱",
                 "CFBundleName": "创作工具箱",
                 "CFBundleShortVersionString": version,
                 "NSHighResolutionCapable": True,
                 "LSMinimumSystemVersion": "13.0",
                 "LSApplicationCategoryType": "public.app-category.graphics-design",
                 "NSRequiresAquaSystemAppearance": True,
             })
