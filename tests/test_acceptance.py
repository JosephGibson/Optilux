"""The acceptance items' verdicts and the run's status, on fakes: no game, no Windows
(docs/workflow.md#testing; the QA pass, docs/plans/m1.md#00112-review-and-cleanup)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optilux import acceptance, session

# A4's refusal as m1-acceptance-4 to -7 recorded it.
A4_MESSAGE = (
    "ShaderCompileException: final.fsh: final.fsh: ERROR: 0:20: 'optiluxA4Undeclared' : "
    "undeclared identifier \nERROR: 0:20: '' : compilation terminated \n"
)
SEEN = {"sessionPipeListed": True, "sessionMixinsApplied": 9, "sessionThreads": ["optilux-pipe"]}


def test_a1_counts_a_detector_that_could_not_be_read_as_blind() -> None:
    assert acceptance.a1_seen(SEEN) is True
    for blind in (
        {"sessionThreads": "unread: jcmd exited 1"},
        {"sessionThreads": []},
        {"sessionPipeListed": "unread: [WinError 5]"},
        {"sessionMixinsApplied": 0},
    ):
        assert acceptance.a1_seen({**SEEN, **blind}) is False, blind


def test_a4_names_the_broken_file_not_any_word_holding_final() -> None:
    assert acceptance.a4_names(A4_MESSAGE) == {"namesProgram": True, "namesIdentifier": True}
    other = "Failed to finalize the pipeline: composite.fsh: ERROR: 0:3: syntax error"
    assert acceptance.a4_names(other) == {"namesProgram": False, "namesIdentifier": False}


def test_a9_fails_on_an_event_that_invalidates_its_capture() -> None:
    matched = {"pass": True}
    assert acceptance.a9_pass(matched, True, 0, [], []) is True
    assert acceptance.a9_pass(matched, True, 0, [], [{"event": "focus.lost"}]) is False
    assert acceptance.a9_pass(matched, True, 0, ["optilux-x"], []) is False
    assert acceptance.a9_pass(matched, False, 0, [], []) is False
    assert acceptance.a9_pass({"pass": False}, True, 0, [], []) is False


def test_the_helper_log_counts_hook_failures_and_iris_failures_outside_a_reload() -> None:
    log = "\n".join(
        [
            "[12:00:01] [Render thread/INFO]: optilux-helper: active: pipe \\\\.\\pipe\\optilux-ab",
            "[12:00:09] [Render thread/WARN]: optilux-helper: frame head failed at frame 12",
            "[12:00:10] [Render thread/WARN]: optilux-helper: Iris failed to load a pack outside "
            "shaders.reload: ShaderCompileException",
            "[12:00:11] [Render thread/WARN]: optilux-helper: shaders.reload of a.zip failed in "
            "0.2 s: iris-compile-error x",
        ]
    )
    found = acceptance.helper_lines(log)
    assert len(found["hookFailures"]) == 1 and "frame 12" in found["hookFailures"][0]
    assert len(found["irisOutsideReload"]) == 1
    assert len(found["active"]) == 1


def status(facts: dict, items: dict, asked=("A10",), problems=None, start="ok"):
    problems = [] if problems is None else problems
    found, entries = session.record_status(start, problems, facts, items, asked, 0, None)
    return found, entries, problems


def test_the_status_is_ok_only_when_every_item_passed_and_nothing_went_wrong() -> None:
    assert status({}, {"A10": {"pass": True}})[0] == "ok"
    found, entries, problems = status({}, {"A10": {"pass": False}})
    assert (found, problems) == ("failed", ["items failed: A10"])
    assert entries == [{"item": "A10", "pass": False, "evidence": {}}]
    found, entries, _ = status({}, {}, problems=["the session: ModGone"])
    assert found == "failed"
    assert entries[0]["evidence"] == {"notRun": "the session: ModGone"}
    assert status({"quit": {"exitCode": 1}}, {"A10": {"pass": True}})[0] == "failed"
    assert status({"readBack": {"ok": False}}, {"A10": {"pass": True}})[0] == "failed"
    assert status({}, {}, problems=["stopped by the user"], start="aborted")[0] == "aborted"


def test_a_hook_failure_makes_the_run_invalid_even_before_hello() -> None:
    """hook.error is an event, sent only after hello; a failure before it reaches only the log,
    and the session's latest.log is read for it."""
    assert status({"events": [{"event": "hook.error"}]}, {"A10": {"pass": True}})[0] == "invalid"
    logged = {"helperLog": {"applied": 9, "active": 1, "hookFailures": 1, "irisOutsideReload": 0}}
    found, _, problems = status(logged, {"A10": {"pass": True}})
    assert found == "invalid" and "hook failure" in problems[0]
    iris = {"helperLog": {"applied": 9, "active": 1, "hookFailures": 0, "irisOutsideReload": 2}}
    found, _, problems = status(iris, {"A10": {"pass": True}})
    assert found == "invalid" and "outside shaders.reload" in problems[0]


class FakeClient:
    """The client calls settle_view and A2's start make, answered at once."""

    def __init__(self, focused: bool = True) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.focused = focused

    def command(self, text: str, timeout: float = 10.0, check: bool = True) -> dict:
        self.calls.append(("command", text))
        return {"succeeded": True, "messages": [], "failures": []}

    def ticks_step(self, n: int, timeout: float) -> dict:
        self.calls.append(("ticks.step", n))
        return {}

    def camera_place(self, pose: dict, timeout: float) -> dict:
        return {"pose": pose, "arrivedSeconds": 0.1}

    def ready(self, stable: int, settle: float, timeout: float) -> dict:
        self.calls.append(("ready", settle))
        return {"seconds": settle, "limitedBy": "minSeconds"}

    def state(self) -> dict:
        return {"focused": self.focused, "screen": None}


def fake_session(client: FakeClient, foreground: int = 4242, tmp: Path | None = None) -> Any:
    def step(name, call, show=None):
        return call()

    host = SimpleNamespace(
        foreground_pid=lambda: foreground,
        focus=lambda pid: "SetForegroundWindow refused",
        click_focus=lambda pid: "no click: another window",
        key_press=lambda vk, scan: pytest.fail("a key was sent to another window"),
    )
    return SimpleNamespace(
        client=client,
        host=host,
        launched=SimpleNamespace(pid=4242, game=tmp or Path(".")),
        raw=tmp or Path("."),
        step=step,
        label="",
        events=[],
        drain=lambda: None,
        say=lambda line: None,
    )


VIEW = {
    "id": "underwater",
    "dim": "minecraft:overworld",
    "x": -333.1,
    "y": 54.5,
    "z": 908.5,
    "yaw": -145.6,
    "pitch": 34.9,
    "time": 6000,
    "weather": "clear",
}
SUITE = {
    "capture": {
        "ticksAfterWeatherChange": 120,
        "visualSettleS": {"default": 1.0, "underwater": 2.0, "addAfterDimensionChange": 3.0},
    }
}


def test_settle_view_takes_the_suites_settle_for_its_view() -> None:
    client = FakeClient()
    done = session.settle_view(fake_session(client), VIEW, "clear", SUITE, VIEW["dim"])
    assert done["settleSeconds"] == 2.0 and ("ready", 2.0) in client.calls
    night = {**VIEW, "id": "night"}
    done = session.settle_view(fake_session(FakeClient()), night, "clear", SUITE, "x")
    assert done["settleSeconds"] == 4.0  # the default plus the dimension change's addition


def test_injected_input_needs_the_games_window_in_front(monkeypatch: pytest.MonkeyPatch) -> None:
    """A2's F2 and A7's keys go out only while the game reports focus and owns the foreground
    window: SendInput reaches whatever window is in front (m1-acceptance-6)."""
    sent = []
    s = fake_session(FakeClient(focused=True), foreground=7)
    found = acceptance.inject(s, "F2", lambda: sent.append(1) or 2)
    assert (found["inserted"], found["foregroundPid"], sent) == (0, 7, [])
    s = fake_session(FakeClient(focused=True), foreground=4242)
    assert acceptance.inject(s, "F2", lambda: 2)["inserted"] == 2
    # A2 refuses to start while another window is in front, as A7 does.
    monkeypatch.setattr(session.time, "sleep", lambda seconds: None)
    found = acceptance.a2_attempt(
        fake_session(FakeClient(focused=True), foreground=7), VIEW, 1, "3840x2160"
    )
    assert found["pass"] is False and "foreground" in found["problem"]
    assert found["focusFallback"][0] == "foreground pid 7"


def test_a2_passes_only_on_a_matched_unmoved_screenshot_at_the_resolution() -> None:
    good = (2, True, [7], [], [], "3840x2160", "3840x2160")
    assert acceptance.a2_pass(*good) is True
    for at, bad in (
        (0, 0),  # F2 not inserted (another window in front)
        (1, False),
        (2, []),  # equal to no captured frame
        (3, [{"event": "screen.opened"}]),
        (4, ["x: 1.0 != 2.0"]),
        (5, "2560x1440"),
    ):
        args = list(good)
        args[at] = bad
        assert acceptance.a2_pass(*args) is False, (at, bad)


def injected(count: int) -> dict:
    return {"what": "x", "focused": True, "foregroundPid": 4242, "inserted": count}


CONTROL = {
    "key": injected(2),
    "screen": acceptance.CHAT_SCREEN,
    "escape": injected(2),
    "closed": True,
    "prime": injected(1),
    "mouse": injected(1),
    "poseAfter": {"yaw": 10.0},
}
BLOCKED = {
    "mouse": injected(1),
    "key": injected(2),
    "poseChanged": False,
    "stateChanged": [],
    "screensOpened": [],
    "framesHeld": acceptance.A7_HOLD_FRAMES,
}
AFTER = {"mouse": injected(1), "poseAfter": {"yaw": 20.0}}


def test_a7_judges_its_three_arms() -> None:
    assert acceptance.a7_verdicts(CONTROL, BLOCKED, AFTER) == (True, True, True)
    blind = {**CONTROL, "key": {**injected(2), "inserted": 0}}  # T never reached the game
    assert acceptance.a7_verdicts(blind, BLOCKED, AFTER)[0] is False
    for leak in (
        {"poseChanged": True},
        {"stateChanged": ["screen"]},
        {"screensOpened": [acceptance.CHAT_SCREEN]},
        {"framesHeld": acceptance.A7_HOLD_FRAMES - 1},
    ):
        assert acceptance.a7_verdicts(CONTROL, {**BLOCKED, **leak}, AFTER)[1] is False, leak
    assert acceptance.a7_verdicts(CONTROL, BLOCKED, {"mouse": injected(1)})[2] is False


def test_f4_reports_the_growth_per_reload_from_its_first_row_to_its_last() -> None:
    first = {"heapUsedMiB": 597.3, "privateMiB": 13174.6}
    last = {"heapUsedMiB": 1599.6, "privateMiB": 16809.7}
    assert acceptance.per_reload(first, last, 50) == {"heapMiB": 20.05, "privateMiB": 72.7}


def test_a4_counts_every_invalidating_event_but_its_own_reloads() -> None:
    """A4 reloads on purpose (reload.failed, then reload.done); focus.lost, dimension.changed,
    screen.opened or hook.error across its window invalidate it (mod-protocol.md#client-rules)."""
    reloads = [{"event": "reload.failed"}, {"event": "reload.done"}]
    assert acceptance.a4_clean(reloads) is True
    for event in ("focus.lost", "dimension.changed", "screen.opened", "hook.error"):
        assert acceptance.a4_clean([*reloads, {"event": event}]) is False, event


def test_a_request_log_with_the_token_or_unchecked_fails_the_run() -> None:
    """The token check runs on every session's request log, a failed one's too (m1-acceptance-1
    and -2 had none): a log holding the token, or a session with no check, fails the run."""
    launched = {"mod": {"hello": {}}}
    assert (
        status({**launched, "logCheck": {"tokenAbsent": True}}, {"A10": {"pass": True}})[0] == "ok"
    )
    found, _, problems = status(
        {**launched, "logCheck": {"tokenAbsent": False}}, {"A10": {"pass": True}}
    )
    assert found == "failed" and "holds the token" in problems[0]
    found, _, problems = status(launched, {"A10": {"pass": True}})
    assert found == "failed" and "not checked" in problems[0]


def test_an_answer_no_request_sent_fails_the_run() -> None:
    """The mod answers a line it cannot read with `id: null`: the client files it as stray, and
    the run says so instead of ending on a timeout."""
    stray = [{"id": None, "ok": False, "error": {"code": "bad-json", "message": "at 3"}}]
    found, _, problems = status({"stray": stray}, {"A10": {"pass": True}})
    assert found == "failed" and "1 answer" in problems[0] and "bad-json" in problems[0]
