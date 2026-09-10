"""macOS adapter. Requires on-device verification before claiming compatibility."""
from __future__ import annotations

import ctypes
import time

from ..core import Shortcut, Snapshot, Target, recheck


class MacOSBackend:
    platform = "darwin"
    label = "macOS · 待实机验证"

    def __init__(self) -> None:
        import AppKit
        import Quartz
        import ApplicationServices
        self.appkit, self.q, self.ax = AppKit, Quartz, ApplicationServices
        self.workspace = AppKit.NSWorkspace.sharedWorkspace()
        self.event_time, self.token = 0.0, 0
        self.carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        self.carbon.IsSecureEventInputEnabled.argtypes = []
        self.carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool

    def _attr(self, element, attribute):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)
        return value if error == 0 else None

    def capture(self) -> Snapshot:
        q, ax = self.q, self.ax
        state = q.kCGEventSourceStateHIDSystemState
        idle = q.CGEventSourceSecondsSinceLastEventType(state, q.kCGAnyInputEventType)
        estimate = time.monotonic() - idle
        if estimate > self.event_time + 0.03:
            self.event_time, self.token = estimate, self.token + 1
        trusted = bool(ax.AXIsProcessTrusted())
        post = bool(q.CGPreflightPostEventAccess())
        listen = bool(q.CGPreflightListenEventAccess())
        can_send = trusted and post and listen
        permission = "" if can_send else "需在系统设置开启辅助功能与输入监控，再重新启动工具箱"
        session = q.CGSessionCopyCurrentDictionary()
        if not session or session.get("CGSSessionScreenIsLocked", False) or not session.get("kCGSessionOnConsoleKey", True):
            return Snapshot(None, idle, self.token, blocked="锁屏或非活动会话", can_send=False)
        front = self.workspace.frontmostApplication()
        if front is None:
            return Snapshot(None, idle, self.token, can_send=False)
        identity = str(front.bundleIdentifier() or "")
        if not identity:
            return Snapshot(None, idle, self.token, blocked="应用没有可识别的 bundle ID", can_send=False)
        title, window_id, blocked = "", "", ""
        if self.carbon.IsSecureEventInputEnabled():
            blocked = "系统安全输入启用，暂停发送"
        if trusted:
            app = ax.AXUIElementCreateApplication(front.processIdentifier())
            ax.AXUIElementSetMessagingTimeout(app, 0.1)
            window = self._attr(app, "AXFocusedWindow")
            if window:
                title = str(self._attr(window, "AXTitle") or "")
                window_id = str(hash(window))
                if self._attr(window, "AXModal") or self._attr(window, "AXSheets"):
                    blocked = "对话框打开，等待返回编辑窗口"
            else:
                blocked = "无法确认前台窗口"
            focus = self._attr(app, "AXFocusedUIElement")
            role = self._attr(focus, "AXRole") if focus else None
            if role in ("AXTextField", "AXTextArea", "AXComboBox", "AXMenu", "AXMenuItem"):
                blocked = "文字输入或菜单获得焦点"
        else:
            blocked = "开启辅助功能后才能识别窗口状态"
        pressed = any(q.CGEventSourceKeyState(state, code) for code in range(128))
        pressed = pressed or any(q.CGEventSourceButtonState(state, b) for b in range(5))
        target = Target(identity, str(front.localizedName()), int(front.processIdentifier()), window_id, title)
        return Snapshot(target, idle, self.token, pressed, blocked, can_send, permission)

    def send(self, expected: Snapshot, shortcut: Shortcut, idle_required: int) -> tuple[bool, str]:
        error = recheck(expected, self.capture(), idle_required)
        if error:
            return False, error
        q = self.q
        # Apple virtual key positions; custom non-US layouts need explicit validation.
        keycodes = {"A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6,
                    "X": 7, "C": 8, "V": 9, "B": 11, "Q": 12, "W": 13,
                    "E": 14, "R": 15, "Y": 16, "T": 17, "1": 18, "2": 19,
                    "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
                    "8": 28, "0": 29, "O": 31, "U": 32, "I": 34, "P": 35,
                    "L": 37, "J": 38, "K": 40, "N": 45, "M": 46,
                    "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96,
                    "F6": 97, "F7": 98, "F8": 100, "F9": 101, "F10": 109,
                    "F11": 103, "F12": 111}
        masks = {"Ctrl": q.kCGEventFlagMaskControl, "Cmd": q.kCGEventFlagMaskCommand,
                 "Shift": q.kCGEventFlagMaskShift, "Alt": q.kCGEventFlagMaskAlternate}
        flags = 0
        for modifier in shortcut.modifiers:
            flags |= masks[modifier]
        source = q.CGEventSourceCreate(q.kCGEventSourceStatePrivate)
        down = q.CGEventCreateKeyboardEvent(source, keycodes[shortcut.key], True)
        up = q.CGEventCreateKeyboardEvent(source, keycodes[shortcut.key], False)
        if down is None or up is None:
            return False, "无法创建系统输入事件"
        q.CGEventSetFlags(down, flags)
        q.CGEventSetFlags(up, flags)
        # PID-directed delivery avoids redirecting a late event to a different process.
        q.CGEventPostToPid(expected.target.pid, down)
        q.CGEventPostToPid(expected.target.pid, up)
        return True, "已发送保存请求 · 结果未确认"
