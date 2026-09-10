from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .core import Profile, resolve_shortcut


def data_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CreativeToolbox"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CreativeToolbox"


def presets(platform: str) -> list[Profile]:
    rows = [("photoshop", "Photoshop", "Photoshop.exe", "com.adobe.Photoshop", False),
            ("blender", "Blender", "blender.exe", "org.blenderfoundation.blender", False),
            ("resolve", "DaVinci Resolve", "Resolve.exe", "com.blackmagic-design.DaVinciResolve", True),
            ("cubase", "Cubase", "Cubase15.exe", "com.steinberg.cubase15", True)]
    return [Profile(i, n, mac if platform == "darwin" else win, platform,
                    enabled=False, reminder_only=reminder) for i, n, win, mac, reminder in rows]


@dataclass
class Settings:
    profiles: list[Profile] = field(default_factory=list)
    style: str = "auto"
    custom: str = "Ctrl+S"


class Store:
    def __init__(self, root: Path, platform: str) -> None:
        self.root, self.platform = root, platform
        self.path = root / "settings.json"
        self.warning = ""

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings(presets(self.platform))
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("schema") != 1:
                raise ValueError("不支持的配置版本")
            profiles = [Profile(**p) for p in raw["profiles"]]
            for profile in profiles:
                profile.validate()
            if len({p.id for p in profiles}) != len(profiles):
                raise ValueError("应用标识重复")
            settings = Settings(profiles, raw["style"], raw["custom"])
            resolve_shortcut(settings.style, settings.custom, self.platform)
            return settings
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.warning = f"配置未载入：{exc}。原文件保留，保存设置后将替换。"
            return Settings(presets(self.platform))

    def save(self, settings: Settings) -> None:
        for profile in settings.profiles:
            profile.validate()
        resolve_shortcut(settings.style, settings.custom, self.platform)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 1, **asdict(settings)}
        fd, name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def event(self, kind: str, app: str, message: str) -> None:
        """Bounded local metadata only; never persist window titles or keystrokes."""
        from datetime import datetime
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "events.jsonl"
        if path.exists() and path.stat().st_size > 512_000:
            os.replace(path, self.root / "events.previous.jsonl")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                                     "kind": kind, "app": app, "message": message},
                                    ensure_ascii=False) + "\n")
