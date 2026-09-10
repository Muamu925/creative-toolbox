"""Win32 integration with explicit ctypes signatures (including 64-bit handles)."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os

from ..core import Shortcut, Snapshot, Target, recheck


class LASTINPUTINFO(C.Structure):
    _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]


class GUITHREADINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("hwndActive", W.HWND),
                ("hwndFocus", W.HWND), ("hwndCapture", W.HWND), ("hwndMenuOwner", W.HWND),
                ("hwndMoveSize", W.HWND), ("hwndCaret", W.HWND), ("rcCaret", W.RECT)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", C.c_size_t)]


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", C.c_size_t)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class INPUTUNION(C.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", W.DWORD), ("value", INPUTUNION)]


def keyboard_packet(vk: int, up: bool = False) -> INPUT:
    packet = INPUT()
    packet.type = 1
    packet.ki = KEYBDINPUT(vk, 0, 2 if up else 0, 0, 0)
    return packet


class WindowsBackend:
    platform = "win32"
    label = "Windows"

    def __init__(self) -> None:
        self.user = C.WinDLL("user32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.imm = C.WinDLL("imm32", use_last_error=True)
        signatures = [
            (self.user, "GetForegroundWindow", [], W.HWND),
            (self.user, "GetWindowThreadProcessId", [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            (self.user, "GetWindowTextW", [W.HWND, W.LPWSTR, C.c_int], C.c_int),
            (self.user, "GetClassNameW", [W.HWND, W.LPWSTR, C.c_int], C.c_int),
            (self.user, "GetLastInputInfo", [C.POINTER(LASTINPUTINFO)], W.BOOL),
            (self.user, "GetAsyncKeyState", [C.c_int], C.c_short),
            (self.user, "GetGUIThreadInfo", [W.DWORD, C.POINTER(GUITHREADINFO)], W.BOOL),
            (self.user, "IsWindowEnabled", [W.HWND], W.BOOL),
            (self.user, "SendInput", [W.UINT, C.POINTER(INPUT), C.c_int], W.UINT),
            (self.user, "OpenInputDesktop", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.user, "GetUserObjectInformationW", [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            (self.user, "CloseDesktop", [W.HANDLE], W.BOOL),
            (self.kernel, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.kernel, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            (self.kernel, "CloseHandle", [W.HANDLE], W.BOOL),
            (self.kernel, "GetTickCount64", [], C.c_ulonglong),
            (self.imm, "ImmGetContext", [W.HWND], W.HANDLE),
            (self.imm, "ImmGetCompositionStringW", [W.HANDLE, W.DWORD, W.LPVOID, W.DWORD], W.LONG),
            (self.imm, "ImmReleaseContext", [W.HWND, W.HANDLE], W.BOOL),
        ]
        for library, name, args, restype in signatures:
            fn = getattr(library, name)
            fn.argtypes, fn.restype = args, restype

    def _text(self, hwnd, classname=False) -> str:
        buf = C.create_unicode_buffer(1024)
        fn = self.user.GetClassNameW if classname else self.user.GetWindowTextW
        fn(hwnd, buf, len(buf))
        return buf.value

    def _desktop_ready(self) -> bool:
        desktop = self.user.OpenInputDesktop(0, False, 1)
        if not desktop:
            return False
        try:
            buf, needed = C.create_unicode_buffer(256), W.DWORD()
            ok = self.user.GetUserObjectInformationW(desktop, 2, buf, C.sizeof(buf), C.byref(needed))
            return bool(ok and buf.value.casefold() == "default")
        finally:
            self.user.CloseDesktop(desktop)

    def capture(self) -> Snapshot:
        last = LASTINPUTINFO(C.sizeof(LASTINPUTINFO), 0)
        if not self.user.GetLastInputInfo(C.byref(last)):
            return Snapshot(None, 0, 0, blocked="无法读取输入状态", can_send=False)
        idle = ((self.kernel.GetTickCount64() & 0xFFFFFFFF) - last.dwTime) & 0xFFFFFFFF
        if not self._desktop_ready():
            return Snapshot(None, idle / 1000, last.dwTime, blocked="锁屏或系统安全桌面，已暂停发送", can_send=False)
        hwnd = self.user.GetForegroundWindow()
        if not hwnd:
            return Snapshot(None, idle / 1000, last.dwTime)
        pid = W.DWORD()
        thread = self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        process = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not process:
            return Snapshot(None, idle / 1000, last.dwTime, blocked="无法识别前台程序", can_send=False)
        try:
            path, length = C.create_unicode_buffer(32768), W.DWORD(32768)
            if not self.kernel.QueryFullProcessImageNameW(process, 0, path, C.byref(length)):
                return Snapshot(None, idle / 1000, last.dwTime, blocked="无法读取程序身份", can_send=False)
            identity = path.value
        finally:
            self.kernel.CloseHandle(process)
        target = Target(identity, os.path.basename(identity), pid.value, str(hwnd), self._text(hwnd))
        pressed = any(self.user.GetAsyncKeyState(vk) & 0x8000 for vk in range(1, 256))
        info = GUITHREADINFO()
        info.cbSize = C.sizeof(info)
        blocked = ""
        if not self.user.GetGUIThreadInfo(thread, C.byref(info)):
            blocked = "无法确认当前窗口交互状态"
        elif info.flags & 0x1E or info.hwndCapture:
            blocked = "菜单、拖拽或窗口操作进行中"
        elif self._text(hwnd, True) == "#32770" or not self.user.IsWindowEnabled(hwnd):
            blocked = "对话框打开，等待返回编辑窗口"
        elif info.hwndFocus:
            cls = self._text(info.hwndFocus, True).casefold()
            if cls == "edit" or cls.startswith("richedit"):
                blocked = "文字输入控件获得焦点"
            context = self.imm.ImmGetContext(info.hwndFocus)
            if context:
                try:
                    if self.imm.ImmGetCompositionStringW(context, 8, None, 0) > 0:
                        blocked = "输入法正在组词"
                finally:
                    self.imm.ImmReleaseContext(info.hwndFocus, context)
        return Snapshot(target, idle / 1000, last.dwTime, pressed, blocked)

    def send(self, expected: Snapshot, shortcut: Shortcut, idle_required: int) -> tuple[bool, str]:
        if "Cmd" in shortcut.modifiers:
            return False, "Windows 不支持 Command 按键"
        error = recheck(expected, self.capture(), idle_required)
        if error:
            return False, error
        mod_codes = {"Ctrl": 0x11, "Alt": 0x12, "Shift": 0x10}
        mods = [mod_codes[m] for m in shortcut.modifiers]
        key = 0x70 + int(shortcut.key[1:]) - 1 if shortcut.key.startswith("F") and len(shortcut.key) > 1 else ord(shortcut.key)
        packets = [keyboard_packet(k) for k in mods] + [keyboard_packet(key), keyboard_packet(key, True)]
        packets += [keyboard_packet(k, True) for k in reversed(mods)]
        # One batch; never activate the target or release keys held by the user.
        array = (INPUT * len(packets))(*packets)
        count = self.user.SendInput(len(packets), array, C.sizeof(INPUT))
        if count != len(packets):
            # If a partial batch was inserted, balance only our own incomplete sequence.
            # Never issue another save. Physical-input races cannot be fully eliminated.
            held = set()
            for packet in packets[:count]:
                if packet.ki.dwFlags & 2:
                    held.discard(packet.ki.wVk)
                else:
                    held.add(packet.ki.wVk)
            if held:
                cleanup = (INPUT * len(held))(*(keyboard_packet(k, True) for k in held))
                self.user.SendInput(len(held), cleanup, C.sizeof(INPUT))
            return False, "系统未完整接受快捷键；可能存在权限差异，已暂停此应用"
        return True, "已发送保存请求 · 结果未确认"
