"""Built-in tool catalogue and local navigation preferences (no document contents)."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _assets(root):
    from .assets.page import AssetPage
    return AssetPage(root)


def _palette(root):
    from .design_ui import PalettePage
    return PalettePage(root / "palettes.json")


def _fonts(root):
    from .fonts.page import FontPage
    return FontPage(root / "fonts.json")


def _calculators(root):
    from .design_ui import CalculatorPage
    return CalculatorPage()


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    description: str
    keywords: str
    area: str
    factory: Callable | None = None
    requires_protection: bool = False


TOOLS = (
    Tool("assets", "图片素材库", "收集参考图片，整理标签与来源，置顶查看。",
         "素材 图片 参考 收集 标签 备份 image asset reference", "library", _assets),
    Tool("fonts", "字体工作台", "用自己的文案选字，整理分组、标签与候选字体。",
         "字体 文字 字样 排版 对照 比较 分组 font typography", "library", _fonts),
    Tool("palettes", "配色工作台", "保存常用色板、从图片提色，悬浮复制颜色。",
         "色卡 色号 颜色 配色 图片 提色 对比度 hex rgb hsl color palette", "library", _palette),
    Tool("calculators", "创作换算", "换算毫米、像素与 PPI，计算比例和 BPM 音符时长。",
         "毫米 像素 尺寸 等比 缩放 节奏 音乐 延迟 毫秒 mm px ppi bpm size music", "tools", _calculators),
    Tool("protection", "创作保护", "按应用配置保存节奏，查看规则与触发记录。",
         "自动 保存 保护 规则 日志 ctrl cmd save autosave", "protection",
         requires_protection=True),
)
TOOL_BY_ID = {tool.id: tool for tool in TOOLS}


def search_tools(query: str) -> list[Tool]:
    words = query.casefold().split()
    return [tool for tool in TOOLS
            if all(word in f"{tool.name} {tool.description} {tool.keywords}".casefold()
                   for word in words)]


class WorkspaceStore:
    """Small atomic store, deliberately separate from save rules and resource files."""
    LIMIT = 64_000

    def __init__(self, path: Path):
        self.path = path
        self.warning = ""
        self.read_only = False
        self.data = {"schema": 1, "favorites": ["fonts", "palettes", "calculators"], "recent": []}
        try:
            if not path.exists():
                return
            if path.stat().st_size > self.LIMIT:
                raise ValueError("文件过大")
            self.data = self.validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            self.read_only = True
            self.warning = f"工具偏好未载入：{exc}。原文件保留；本次仍可打开工具，收藏与最近使用暂不写入。"

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError("不支持的工具偏好版本")
        favorites, recent = data.get("favorites"), data.get("recent")
        valid_id = lambda value: isinstance(value, str) and 0 < len(value) <= 64
        if (not isinstance(favorites, list) or len(favorites) > 128
                or not all(valid_id(value) for value in favorites)
                or len(set(favorites)) != len(favorites)):
            raise ValueError("收藏格式无效")
        if not isinstance(recent, list) or len(recent) > 12:
            raise ValueError("最近使用格式无效")
        ids = set()
        for item in recent:
            if (not isinstance(item, dict) or not valid_id(item.get("id"))
                    or not isinstance(item.get("used_at"), str) or len(item["used_at"]) > 40):
                raise ValueError("最近使用记录无效")
            stamp = datetime.fromisoformat(item["used_at"])
            if stamp.tzinfo is None or item["id"] in ids:
                raise ValueError("最近使用时间或标识无效")
            ids.add(item["id"])
        return {"schema": 1, "favorites": list(favorites),
                "recent": [{"id": item["id"], "used_at": item["used_at"]} for item in recent]}

    def save(self, candidate):
        if self.read_only:
            raise ValueError(self.warning)
        candidate = self.validate(candidate)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.data = candidate

    def toggle_favorite(self, tool_id):
        if tool_id not in TOOL_BY_ID:
            raise ValueError("未知工具")
        values = list(self.data["favorites"])
        if tool_id in values:
            values.remove(tool_id)
        else:
            values.append(tool_id)
        self.save({**self.data, "favorites": values})

    def record_open(self, tool_id):
        if tool_id not in TOOL_BY_ID:
            raise ValueError("未知工具")
        recent = [{"id": tool_id, "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]
        recent += [item for item in self.data["recent"] if item["id"] != tool_id]
        self.save({**self.data, "recent": recent[:12]})
