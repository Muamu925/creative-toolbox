"""Platform-independent policy. A sent request is never a confirmed disk save."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Shortcut:
    modifiers: tuple[str, ...]
    key: str

    @classmethod
    def parse(cls, text: str) -> "Shortcut":
        aliases = {"control": "Ctrl", "ctrl": "Ctrl", "shift": "Shift",
                   "alt": "Alt", "option": "Alt", "cmd": "Cmd", "command": "Cmd"}
        parts = [p.strip() for p in text.split("+")]
        if len(parts) < 2 or any(not p for p in parts):
            raise ValueError("请使用组合键，例如 Ctrl+S、Cmd+S 或 Ctrl+Shift+S")
        try:
            mods = [aliases[p.lower()] for p in parts[:-1]]
        except KeyError as exc:
            raise ValueError("修饰键仅支持 Ctrl、Cmd、Alt、Shift") from exc
        if len(set(mods)) != len(mods):
            raise ValueError("组合键中存在重复修饰键")
        key = parts[-1].upper()
        if not re.fullmatch(r"[A-Z0-9]|F(?:[1-9]|1[0-2])", key):
            raise ValueError("主键支持 A–Z、0–9、F1–F12")
        if set(mods) == {"Shift"}:
            raise ValueError("请至少包含 Ctrl、Cmd 或 Alt，避免输入普通字符")
        return cls(tuple(m for m in ("Ctrl", "Alt", "Shift", "Cmd") if m in mods), key)

    def text(self) -> str:
        return "+".join((*self.modifiers, self.key))


def resolve_shortcut(style: str, custom: str, platform: str) -> Shortcut:
    text = {"auto": "Cmd+S" if platform == "darwin" else "Ctrl+S",
            "windows": "Ctrl+S", "macos": "Cmd+S", "custom": custom}.get(style)
    if text is None:
        raise ValueError("未知快捷键模式")
    shortcut = Shortcut.parse(text)
    if platform != "darwin" and "Cmd" in shortcut.modifiers:
        raise ValueError("Command 快捷键仅适用于 macOS；Windows 请选 Ctrl 或自定义")
    return shortcut


@dataclass
class Profile:
    id: str
    name: str
    identity: str
    platform: str
    enabled: bool = True
    interval: int = 120
    idle: int = 8
    style: str = "inherit"
    custom: str = "Ctrl+S"
    reminder_only: bool = False

    def validate(self) -> None:
        if not self.id or not self.name.strip() or not self.identity.strip():
            raise ValueError("请填写应用名称和程序标识")
        if self.platform not in ("win32", "darwin"):
            raise ValueError("不支持的平台")
        if not 10 <= self.interval <= 7200 or not 2 <= self.idle <= 600:
            raise ValueError("保存间隔范围 10–7200 秒，空闲时间范围 2–600 秒")
        if self.style not in ("inherit", "auto", "windows", "macos", "custom"):
            raise ValueError("未知快捷键模式")
        if self.style != "inherit":
            resolve_shortcut(self.style, self.custom, self.platform)

    def matches(self, target: "Target", platform: str) -> bool:
        if self.platform != platform or not self.enabled:
            return False
        if platform == "darwin":
            return self.identity == target.identity
        expected = self.identity.replace("/", "\\").casefold()
        actual = target.identity.replace("/", "\\").casefold()
        return actual == expected if "\\" in expected else actual.rsplit("\\", 1)[-1] == expected


@dataclass(frozen=True)
class Target:
    identity: str
    name: str
    pid: int
    window: str
    title: str

    @property
    def key(self) -> tuple:
        return self.identity, self.pid, self.window, self.title


@dataclass(frozen=True)
class Snapshot:
    target: Target | None
    idle: float
    input_token: int
    pressed: bool = False
    blocked: str = ""
    can_send: bool = True
    permission: str = ""


@dataclass(frozen=True)
class Decision:
    code: str
    message: str
    profile_id: str = ""
    due: bool = False
    remaining: int = 0


@dataclass
class WindowState:
    last_attempt: float
    last_token: int | None = None


class Engine:
    def __init__(self) -> None:
        self.windows: dict[tuple, WindowState] = {}
        self.failed: set[str] = set()
        self.stable_key: tuple | None = None
        self.stable_since = 0.0
        self.last_tick: float | None = None

    def reset(self) -> None:
        self.windows.clear()
        self.failed.clear()
        self.stable_key = None
        self.last_tick = None

    def evaluate(self, snap: Snapshot, profiles: list[Profile], platform: str,
                 now: float, paused: bool = False) -> Decision:
        if self.last_tick is not None and (now - self.last_tick > 5 or now < self.last_tick):
            self.reset()  # Sleep, lock recovery or a stalled event loop must start afresh.
        self.last_tick = now
        key = snap.target.key if snap.target else None
        if key != self.stable_key:
            self.stable_key, self.stable_since = key, now
        if paused:
            return Decision("paused", "保护已暂停，不会发送快捷键")
        if not snap.target:
            if snap.blocked:
                self.windows.clear()
            return Decision("no_window", snap.blocked or "等待可识别的前台应用")
        matches = [p for p in profiles if p.matches(snap.target, platform)]
        # A full path is more specific than a basename preset.
        matches.sort(key=lambda p: len(p.identity), reverse=True)
        if not matches:
            return Decision("unlisted", "当前应用未启用保护")
        profile = matches[0]
        pid = profile.id
        if pid in self.failed:
            return Decision("failed", "上次发送失败；修正后点击「重新开始」", pid)
        state_key = (pid, *snap.target.key)
        if len(self.windows) > 256 and state_key not in self.windows:
            self.windows.clear()
        state = self.windows.setdefault(state_key, WindowState(now))
        if snap.blocked:
            return Decision("blocked", snap.blocked, pid)
        if snap.pressed:
            return Decision("held", "检测到按键或鼠标按钮仍按住", pid)
        if now - self.stable_since < 1:
            return Decision("switching", "等待前台窗口稳定", pid)
        if not math.isfinite(snap.idle) or snap.idle < 0:
            return Decision("unknown_input", "无法确认输入空闲状态", pid)
        if snap.idle < profile.idle:
            return Decision("active", "正在操作，等待输入停顿", pid,
                            remaining=math.ceil(profile.idle - snap.idle))
        remaining = math.ceil(profile.interval - (now - state.last_attempt))
        if remaining > 0:
            return Decision("interval", "等待保存间隔", pid, remaining=remaining)
        if state.last_token == snap.input_token:
            return Decision("unchanged", "本次空闲已处理，等待新的输入活动", pid)
        return Decision("ready", "输入空闲，已满足通用规则", pid, True)

    def mark_attempt(self, profile_id: str, target: Target, now: float, input_token: int,
                     failed: bool = False) -> None:
        self.windows[(profile_id, *target.key)] = WindowState(now, input_token)
        if failed:
            self.failed.add(profile_id)


def recheck(expected: Snapshot, current: Snapshot, idle_required: int) -> str:
    """Fail closed on all observable changes immediately before native dispatch."""
    if not current.target or not expected.target or current.target.key != expected.target.key:
        return "目标窗口已变化，取消本次发送"
    if current.input_token != expected.input_token:
        return "检测到新的输入，取消本次发送"
    if current.blocked:
        return current.blocked
    if current.pressed or not math.isfinite(current.idle) or current.idle < idle_required:
        return "用户正在输入，取消本次发送"
    if not current.can_send:
        return current.permission or "没有发送快捷键所需的系统权限"
    return ""
