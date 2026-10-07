"""The minimal SendInput helper (plans/m1.md P33) on a fake user32: the INPUT layout Windows
expects and the events each call injects."""

import ctypes

from optilux import sendinput


class FakeUser32:
    """Records each SendInput call's events as plain tuples; takes all, or `take` of them."""

    def __init__(self, take: int | None = None) -> None:
        self.calls: list[list[tuple]] = []
        self.take = take

    def SendInput(self, count: int, array, size: int) -> int:
        assert size == ctypes.sizeof(sendinput.INPUT)
        events = []
        for event in array[:count]:
            if event.type == sendinput.INPUT_MOUSE:
                mi = event.u.mi
                events.append(("mouse", mi.dx, mi.dy, mi.dwFlags))
            else:
                ki = event.u.ki
                events.append(("key", ki.wVk, ki.wScan, ki.dwFlags))
        self.calls.append(events)
        return count if self.take is None else self.take


def test_the_input_layout_is_windows() -> None:
    # 64-bit Windows: type, padding, then the 32-byte union whose largest member is MOUSEINPUT.
    pointer = ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(sendinput.MOUSEINPUT) == (32 if pointer == 8 else 24)
    assert ctypes.sizeof(sendinput.INPUT) == (40 if pointer == 8 else 28)


def test_a_mouse_move_is_one_relative_motion() -> None:
    api = FakeUser32()
    assert sendinput.mouse_move(120, -7, api) == 1
    assert api.calls == [[("mouse", 120, -7, sendinput.MOUSEEVENTF_MOVE)]]


def test_a_key_press_is_down_then_up() -> None:
    api = FakeUser32()
    assert sendinput.key_press(0x71, api) == 2  # VK_F2
    assert api.calls == [[("key", 0x71, 0, 0), ("key", 0x71, 0, sendinput.KEYEVENTF_KEYUP)]]


def test_f2_carries_its_scan_code_down_and_up() -> None:
    # SDL3 reads the scan code from the message: an injected F2 carries 0x3C as a keyboard would.
    api = FakeUser32()
    assert sendinput.key_press(sendinput.VK_F2, api, scan=sendinput.SCAN_F2) == 2
    up = sendinput.KEYEVENTF_KEYUP
    assert api.calls == [[("key", 0x71, 0x3C, 0), ("key", 0x71, 0x3C, up)]]


def test_a_left_click_is_button_down_then_up() -> None:
    api = FakeUser32()
    assert sendinput.left_click(api) == 2
    down, up = sendinput.MOUSEEVENTF_LEFTDOWN, sendinput.MOUSEEVENTF_LEFTUP
    assert api.calls == [[("mouse", 0, 0, down), ("mouse", 0, 0, up)]]


def test_the_count_sendinput_reports_is_returned() -> None:
    # A refused injection reports fewer events; the caller compares with what it sent.
    assert sendinput.mouse_move(1, 0, FakeUser32(take=0)) == 0
