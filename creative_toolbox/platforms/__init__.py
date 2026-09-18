import sys


def create_backend():
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    if sys.platform == "darwin":
        from .macos import MacOSBackend
        return MacOSBackend()
    raise RuntimeError("当前初版支持 Windows 与 macOS")


def load_backend():
    """Load native save support without making local utilities depend on it."""
    try:
        return create_backend()
    except Exception as exc:
        from .unavailable import UnavailableBackend
        reason = f"系统保存适配未能加载（{type(exc).__name__}）。请检查系统依赖后重启；字体、配色与换算仍可使用。"
        return UnavailableBackend(sys.platform, reason)
