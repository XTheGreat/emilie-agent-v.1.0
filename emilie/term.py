"""Cross-platform raw keyboard input (POSIX: termios + select, Windows: console VT input via ctypes).

    with RawInput(cbreak=False) as ri:
        if ri.ready(0.3):
            data = ri.read(256)      # bytes, VT sequences ("\\x1b[A" for the up arrow, ...)
"""
import os
import sys

IS_WIN = os.name == "nt"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.GetStdHandle.restype = wintypes.HANDLE
    _k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
    _STD_IN, _STD_OUT = -10, -11
    _ENABLE_PROCESSED_INPUT, _ENABLE_LINE_INPUT, _ENABLE_ECHO_INPUT = 0x1, 0x2, 0x4
    _ENABLE_VT_INPUT = 0x200
    _ENABLE_VT_OUTPUT = 0x4


def enable_vt_output() -> None:
    """Windows: make the console understand ANSI escape codes (no-op elsewhere)."""
    if not IS_WIN:
        return
    try:
        h = _k32.GetStdHandle(_STD_OUT)
        mode = wintypes.DWORD()
        if _k32.GetConsoleMode(h, ctypes.byref(mode)):
            _k32.SetConsoleMode(h, mode.value | _ENABLE_VT_OUTPUT)
    except Exception:
        pass


class RawInput:
    """Unbuffered stdin. cbreak=True keeps Ctrl+C as a signal on POSIX (viewer); raw=everything is a byte (prompts)."""

    def __init__(self, cbreak: bool = False):
        self.cbreak = cbreak
        self._old = None

    def __enter__(self) -> "RawInput":
        if IS_WIN:
            self._h = _k32.GetStdHandle(_STD_IN)
            mode = wintypes.DWORD()
            if _k32.GetConsoleMode(self._h, ctypes.byref(mode)):
                self._old = mode.value
                new = (mode.value & ~(_ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT | _ENABLE_PROCESSED_INPUT)) | _ENABLE_VT_INPUT
                _k32.SetConsoleMode(self._h, new)
            enable_vt_output()
        else:
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            (tty.setcbreak if self.cbreak else tty.setraw)(self._fd)
        return self

    def __exit__(self, *exc) -> None:
        if IS_WIN:
            if self._old is not None:
                _k32.SetConsoleMode(self._h, self._old)
        else:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def ready(self, timeout: float) -> bool:
        if IS_WIN:
            return _k32.WaitForSingleObject(self._h, int(timeout * 1000)) == 0
        import select
        return bool(select.select([self._fd], [], [], timeout)[0])

    def read(self, n: int = 256) -> bytes:
        if IS_WIN:
            buf = ctypes.create_string_buffer(n)
            got = wintypes.DWORD()
            if not _k32.ReadFile(self._h, buf, n, ctypes.byref(got), None):
                return b""
            return buf.raw[:got.value]
        return os.read(self._fd, n)

    def flush(self) -> None:
        if IS_WIN:
            _k32.FlushConsoleInputBuffer(self._h)
        else:
            import termios
            termios.tcflush(self._fd, termios.TCIFLUSH)
