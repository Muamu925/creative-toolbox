#!/usr/bin/env python3
"""Build the standalone native utility without changing xcode-select."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "autosave-lite"
BUILD = ROOT / "build" / "autosave-lite"
ARTIFACTS = ROOT / "artifacts" / "autosave-lite"
DIST = ROOT / "dist"


def run(args, **kwargs):
    print("+", " ".join(str(a) for a in args), flush=True)
    kwargs.setdefault("check", True)
    return subprocess.run([str(a) for a in args], **kwargs)


def toolchain():
    compiler = subprocess.check_output(["xcrun", "--find", "swiftc"], text=True).strip()
    version = subprocess.check_output([compiler, "--version"], text=True).strip()
    match = re.search(r"Swift version (\d+)\.(\d+)", version)
    language = tuple(map(int, match.groups()))
    if os.environ.get("AUTOSAVE_SDK"):
        sdk = Path(os.environ["AUTOSAVE_SDK"]).resolve()
    else:
        developer = Path(subprocess.check_output(["xcode-select", "-p"], text=True).strip())
        bases = [developer / "SDKs", developer / "Platforms/MacOSX.platform/Developer/SDKs"]
        candidates = {}
        for base in bases:
            for path in base.glob("MacOSX*.sdk"):
                path = path.resolve()
                interfaces = list((path / "usr/lib/swift/Swift.swiftmodule").glob("*.swiftinterface"))
                if not interfaces:
                    continue
                header = interfaces[0].read_text()[:1000]
                built = re.search(r"Swift version (\d+)\.(\d+)", header)
                name = re.search(r"MacOSX(\d+)\.(\d+)", path.name)
                if built and name and tuple(map(int, built.groups())) <= language:
                    candidates[path] = tuple(map(int, name.groups()))
        if not candidates:
            raise SystemExit("没有找到兼容 SDK，请通过 AUTOSAVE_SDK 指定配套 SDK。")
        sdk = max(candidates, key=candidates.get)
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        raise SystemExit(f"Unsupported architecture: {arch}")
    flags = ["-swift-version", "5", "-sdk", sdk, "-target", f"{arch}-apple-macosx13.0",
             "-module-cache-path", BUILD / "module-cache"]
    return compiler, flags, {"compiler": version, "sdk": str(sdk), "architecture": arch, "minimum_system": "13.0"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--package-only", action="store_true", help="Package an existing tested app without rebuilding")
    parser.add_argument("--app", type=Path, help="Existing app, only with --package-only")
    args = parser.parse_args()
    for directory in [BUILD, ARTIFACTS, DIST]:
        directory.mkdir(parents=True, exist_ok=True)
    compiler, flags, environment = toolchain()
    sources = sorted((PROJECT / "Sources").glob("*.swift"))
    version = re.search(r'static let version = "([^"]+)"', (PROJECT / "Sources/SavePolicy.swift").read_text()).group(1)
    if args.test:
        binary = BUILD / "AutosaveLiteTests"
        test_sources = [s for s in sources if s.name != "main.swift"] + [PROJECT / "Tests/main.swift"]
        run([compiler, *flags, "-g", *test_sources, "-o", binary])
        result = run([binary], capture_output=True, text=True, check=False)
        (ARTIFACTS / "tests.log").write_text(result.stdout + result.stderr)
        print(result.stdout)
        if result.returncode:
            raise SystemExit(result.returncode)
        return
    if args.app and not args.package_only:
        raise SystemExit("--app requires --package-only")
    app = args.app.resolve() if args.app else DIST / "Autosave Lite.app"
    if not args.package_only:
        if app.exists():
            shutil.rmtree(app)
        macos = app / "Contents/MacOS"
        resources = app / "Contents/Resources"
        macos.mkdir(parents=True)
        resources.mkdir()
        run([compiler, *flags, "-O", *sources, "-o", macos / "AutosaveLite"])
        info = {
            "CFBundleIdentifier": "org.creativetoolbox.autosave-lite",
            "CFBundleName": "AutosaveLite", "CFBundleDisplayName": "Autosave Lite",
            "CFBundleExecutable": "AutosaveLite", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": version, "CFBundleVersion": "1",
            "LSMinimumSystemVersion": "13.0", "LSUIElement": True,
            "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "CFBundleIconFile": "AutosaveLite",
            "NSHumanReadableCopyright": "Creative Toolbox contributors. MIT License.",
        }
        with (app / "Contents/Info.plist").open("wb") as f:
            plistlib.dump(info, f, sort_keys=True)
        icon_program = BUILD / "MakeIcon"
        run([compiler, *flags, PROJECT / "scripts/MakeIcon.swift", "-o", icon_program])
        iconset = BUILD / "AutosaveLite.iconset"
        iconset.mkdir(exist_ok=True)
        run([icon_program, iconset])
        # PNG-backed ICNS chunks avoid a dependency on iconutil's GUI services.
        chunks = []
        for kind, name in [(b"icp4", "16x16"), (b"icp5", "32x32"), (b"icp6", "32x32@2x"),
                           (b"ic07", "128x128"), (b"ic08", "256x256"), (b"ic09", "512x512"),
                           (b"ic10", "512x512@2x"), (b"ic11", "16x16@2x"), (b"ic13", "128x128@2x"),
                           (b"ic14", "256x256@2x")]:
            png = (iconset / f"icon_{name}.png").read_bytes()
            chunks.append(kind + struct.pack(">I", len(png) + 8) + png)
        body = b"".join(chunks)
        (resources / "AutosaveLite.icns").write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
        run(["codesign", "--force", "--sign", "-", "--timestamp=none", app])
    else:
        with (app / "Contents/Info.plist").open("rb") as handle:
            existing = plistlib.load(handle)
        if existing.get("CFBundleIdentifier") != "org.creativetoolbox.autosave-lite" or existing.get("CFBundleShortVersionString") != version:
            raise SystemExit("Existing app identity/version does not match source")
    run(["codesign", "--verify", "--deep", "--strict", app])
    environment.update(version=version, app_bytes=sum(p.stat().st_size for p in app.rglob("*") if p.is_file()),
                       signed="ad-hoc", notarized=False)
    (ARTIFACTS / "build.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2))
    if args.package or args.package_only:
        staging = BUILD / "dmg-staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            shutil.copytree(app, staging / app.name, symlinks=True)
            (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
            manual = (PROJECT / "README.md").read_text().replace("../docs/AUTOSAVE_LITE_PLAN.md", "开发审查方案.md")
            (staging / "使用说明.md").write_text(manual)
            shutil.copy(PROJECT / "VALIDATION.md", staging / "VALIDATION.md")
            review = (ROOT / "docs/AUTOSAVE_LITE_PLAN.md").read_text()
            review = review.replace("../autosave-lite/README.md", "使用说明.md").replace("../autosave-lite/VALIDATION.md", "VALIDATION.md")
            (staging / "开发审查方案.md").write_text(review)
            shutil.copy(ROOT / "LICENSE", staging / "LICENSE")
            image = DIST / f"AutosaveLite-{version}-macOS-{environment['architecture']}-unsigned.dmg"
            run(["hdiutil", "create", "-ov", "-format", "UDZO", "-volname", f"AutosaveLite {version}",
                 "-srcfolder", staging, image])
            run(["hdiutil", "verify", image])
            archive = DIST / f"AutosaveLite-{version}-source.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
                for path in sorted(PROJECT.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                        out.write(path, path.relative_to(ROOT))
                out.write(ROOT / "LICENSE", "LICENSE")
                out.write(ROOT / "docs/AUTOSAVE_LITE_PLAN.md", "docs/AUTOSAVE_LITE_PLAN.md")
                for evidence in ["tests.log", "build.json"]:
                    if (ARTIFACTS / evidence).exists():
                        out.write(ARTIFACTS / evidence, "validation/" + evidence)
            checksums = "\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in [image, archive]) + "\n"
            (DIST / f"AutosaveLite-{version}-SHA256SUMS.txt").write_text(checksums)
            print(checksums)
        finally:
            registrar = Path("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister")
            if registrar.exists() and (staging / app.name).exists():
                subprocess.run([str(registrar), "-u", str(staging / app.name)], capture_output=True)
            shutil.rmtree(staging, ignore_errors=True)
    print(f"Built {app}; {environment['app_bytes'] / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()
