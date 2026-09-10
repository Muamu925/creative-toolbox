import sys


def create_backend():
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    if sys.platform == "darwin":
        from .macos import MacOSBackend
        return MacOSBackend()
    raise RuntimeError("当前初版支持 Windows 与 macOS")
