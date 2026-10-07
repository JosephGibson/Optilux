"""A minimal SendInput helper (user32, through ctypes; plans/m1.md P33).

The harness's own OS input, for the few checks that need a real device path: 0.01.06's mouse nudge
with input.block off, A2's F2 press, and A7's positive control and blocked arm. SendInput
injects into the foreground window's input stream; it is refused across integrity levels (UIPI)
without saying so, so a caller judges the effect in the game, never the return value alone.
Windows only: user32 is loaded on first use; tests pass a fake.
"""

import ctypes
from typing import Any

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
# F2, the vanilla screenshot key (A2): its virtual-key code and its set-1 scan code. SDL3 reads a
# key's scan code from the message, so an injected key carries both, as a keyboard's would.
VK_F2 = 0x71
SCAN_F2 = 0x3C
# A7's keys: T opens the chat screen (Gui's keyChat), Escape closes it, which grabs the mouse
# (Gui.setScreen(null) calls MouseHandler.grabMouse; read in the 26.3 jar, 0.01.09).
VK_T = 0x54
SCAN_T = 0x14
VK_ESCAPE = 0x1B
SCAN_ESCAPE = 0x01
# Fixed-width fields, so the layout is Windows' on any host: 40 bytes per INPUT on 64-bit.
LONG = ctypes.c_int32
DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", _UNION)]


_user32: Any = None


def user32() -> Any:
    """user32.SendInput with its argument types (Windows)."""
    global _user32
    if _user32 is None:
        dll = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        dll.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        dll.SendInput.restype = ctypes.c_uint
        _user32 = dll
    return _user32


def send(inputs: list[INPUT], api: Any = None) -> int:
    """Inject the events in order; the count SendInput reports inserted."""
    array = (INPUT * len(inputs))(*inputs)
    return int((api or user32()).SendInput(len(inputs), array, ctypes.sizeof(INPUT)))


def mouse_move(dx: int, dy: int, api: Any = None) -> int:
    """One relative mouse motion of (dx, dy) mickeys; 1 when SendInput took it."""
    event = INPUT(type=INPUT_MOUSE)
    event.u.mi = MOUSEINPUT(dx=dx, dy=dy, dwFlags=MOUSEEVENTF_MOVE)
    return send([event], api)


def key_press(vk: int, api: Any = None, scan: int = 0) -> int:
    """One key down and up by virtual-key code and scan code; 2 when SendInput took both."""
    down = INPUT(type=INPUT_KEYBOARD)
    down.u.ki = KEYBDINPUT(wVk=vk, wScan=scan)
    up = INPUT(type=INPUT_KEYBOARD)
    up.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=KEYEVENTF_KEYUP)
    return send([down, up], api)


def left_click(api: Any = None) -> int:
    """One left button down and up where the cursor is; 2 when SendInput took both. In game with
    no screen open it grabs the mouse (docs/mod.md#9-input-and-hud)."""
    down = INPUT(type=INPUT_MOUSE)
    down.u.mi = MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN)
    up = INPUT(type=INPUT_MOUSE)
    up.u.mi = MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)
    return send([down, up], api)
