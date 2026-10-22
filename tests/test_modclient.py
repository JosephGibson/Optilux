"""The mod client and the protocol fake (docs/mod-protocol.md#client-rules): commands.json
against the doc's tables, the pipe's name, the client against the fake over a socket pair and,
on Windows, over a real named pipe with the mod's flags and DACL; the redacted request log;
timeouts that nest and cancel."""

import json
import os
import re
import threading
import time
from pathlib import Path

import pytest

from optilux import REPO_ROOT, modclient, modfake

TOKEN = "T" * 43
DOC = REPO_ROOT / "docs" / "mod-protocol.md"
COMMANDS = modclient.load_commands()


def section(name: str) -> str:
    text = DOC.read_text(encoding="utf-8")
    return text.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0]


def table_rows(text: str) -> list[list[str]]:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.startswith("| ") and not line.startswith("|---")
    ]
    return rows[1:]  # the header


def command_names(cell: str) -> list[str]:
    """`timers.start / .read / .stop` is three commands."""
    parts = [part.strip() for part in cell.split("/")]
    base = parts[0].rsplit(".", 1)[0]
    return [parts[0], *(base + part for part in parts[1:])]


def arg_names(cell: str) -> set[str]:
    """The argument names of an Args cell: comma, `or` and `+` separate them; a parenthesis
    explains (values, a default), except one starting with `or`, which names alternatives."""
    if cell == "-":
        return set()
    found: set[str] = set()

    def split(text: str) -> list[str]:
        return [part.strip() for part in re.split(r",| or | \+ ", text) if part.strip()]

    def paren(match: re.Match[str]) -> str:
        if match.group(1).startswith("or "):
            found.update(split(match.group(1)[3:]))
        return ""

    found.update(split(re.sub(r"\(([^)]*)\)", paren, cell)))
    for name in found:
        assert re.fullmatch(r"[a-z][A-Za-z]*", name), f"{name!r} in {cell!r}"
    return found


def test_commands_json_matches_the_doc_table() -> None:
    rows = table_rows(section("Commands"))
    names: list[str] = []
    for name_cell, args_cell, _result, phase_cell in rows:
        group = command_names(name_cell)
        names += group
        specs = [COMMANDS["byName"][name] for name in group]
        assert {spec["phase"] for spec in specs} == {phase_cell.split()[0]}, name_cell
        declared = set().union(*(spec["args"] for spec in specs))
        assert declared == arg_names(args_cell), name_cell
    assert names == [command["name"] for command in COMMANDS["commands"]]
    m1 = [c["name"] for c in COMMANDS["commands"] if c["phase"] == "M1"]
    assert len(m1) == 17  # roadmap.md#m1-game-control


def test_the_error_codes_match_the_doc_table() -> None:
    codes = [code.strip() for row in table_rows(section("Errors")) for code in row[0].split(",")]
    assert codes == COMMANDS["errors"]


def test_commands_json_uses_only_known_keys_and_types() -> None:
    keys = {"type", "required", "default", "min", "max", "gt", "minLength", "maxLength", "values"}
    types = {"string", "integer", "number", "boolean", "object", "array", "id"}
    for command in COMMANDS["commands"]:
        for name, spec in command["args"].items():
            assert set(spec) <= keys and spec["type"] in types, f"{command['name']}.{name}"
            if "default" in spec:
                modclient.check_value(name, spec, spec["default"])
        for kind in command["result"].values():
            assert kind.removesuffix("|null") in types
        if "exclusive" in command:
            assert command["exclusive"] in COMMANDS["resources"]


def test_the_pipe_name_is_the_mods() -> None:
    # The same vectors are in the mod's JsonTest: both ends derive one name.
    assert modclient.pipe_name(TOKEN) == "\\\\.\\pipe\\optilux-259f63a5ba1ef1eb91eb57b3aa0f4732"
    assert modclient.pipe_name("AZaz09_-" * 5 + "abc").endswith("6fe187d6673374b0f58a87a64a213784")


def minimal_args(command: dict) -> dict:
    """The required arguments with values inside their ranges."""
    found = {}
    for name, spec in command["args"].items():
        if not spec.get("required"):
            continue
        kind = spec["type"]
        if kind == "string":
            found[name] = (
                spec["values"][0] if "values" in spec else "x" * max(spec.get("minLength", 1), 1)
            )
        elif kind in ("integer", "number"):
            low = spec["gt"] + 1 if "gt" in spec else spec.get("min", 1)
            found[name] = min(low, spec.get("max", low))
        elif kind == "id":
            found[name] = 1
        else:
            found[name] = {"boolean": True, "object": {}, "array": []}[kind]
    if command["name"] == "hello":
        found["token"] = TOKEN
    return found


def session(
    tmp_path: Path, fake: modfake.Fake | None = None
) -> tuple[modclient.Client, modfake.Fake]:
    fake = fake or modfake.Fake(TOKEN)
    stream, _ = modfake.serve_streams(fake)
    client = modclient.Client(stream, TOKEN, tmp_path / "requests.jsonl", os.getpid())
    return client, fake


def test_the_pipe_ends_only_when_the_mod_closes_it(tmp_path: Path) -> None:
    """wait_closed: True once the mod closed its end after the quit (every line read); False
    while it is open, and after the client closed its own end."""
    client, _ = session(tmp_path)
    client.hello()
    assert client.wait_closed(0.05) is False  # still open
    client.request("quit")  # the fake answers, then closes its end
    assert client.wait_closed(2.0) is True and client.gone == modclient.MOD_CLOSED
    other, _ = session(tmp_path)
    other.hello()
    other.close()
    assert other.wait_closed(0.05) is False and other.gone == "the client closed the pipe"


def test_the_fake_answers_every_command_typed_from_commands_json(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    client.hello()
    fake.game["frozen"] = True  # ticks.step needs it, as in the mod
    common = set(COMMANDS["common"])
    for command in COMMANDS["commands"]:
        if command["name"] == "quit":
            continue
        args = minimal_args(command)
        if command["name"] == "frames.capture":
            args["directory"] = str(tmp_path / "captures")  # the mod takes an absolute folder
        if command["name"] == "window.measure":  # seconds or frames, and frames are not built
            args = {"after": "now", "skipSeconds": 0, "seconds": 0.1}
        result = client.request(command["name"], args)
        assert set(result) == set(command["result"]) | common, command["name"]
    client.request("quit")
    client.close()


def test_the_client_against_the_fake(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    with pytest.raises(modclient.ModRefused) as refused:
        client.request("frames.index")
    assert refused.value.code == "unauthenticated"
    hello = client.hello()
    assert hello["pid"] == os.getpid() and hello["protocol"] == 1 and hello["resumed"] is False
    first = client.request("frames.index")["frameIndex"]
    assert client.request("frames.index")["frameIndex"] > first
    fake.refusals["state"] = ("not-ready", "no world")
    with pytest.raises(modclient.ModRefused, match="state: not-ready: no world"):
        client.request("state")
    with pytest.raises(ValueError, match=r"frames.index: unknown argument x; it takes none"):
        client.request("frames.index", {"x": 1})
    with pytest.raises(ValueError, match=r"no command camera.spin"):
        client.request("camera.spin")
    with pytest.raises(ValueError, match=r"hud.set.hideGui must be true or false"):
        client.request("hud.set", {"hideGui": 1})
    assert fake.emit("world.left", {"reason": "test"})
    event = client.next_event(5)
    assert event["event"] == "world.left" and event["data"] == {"reason": "test"}
    # quit is answered, then the fake ends the connection, as the game exits.
    client.request("quit")
    deadline = time.monotonic() + 5
    while client.gone is None and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(modclient.ModGone):
        client.request("frames.index")
    client.close()


def test_events_only_after_hello(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    assert not fake.emit("world.left", {})
    client.hello()
    assert fake.emit("world.left", {})
    assert client.next_event(5)["event"] == "world.left"
    client.close()


def test_answers_out_of_order_are_matched_by_id(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    client.hello()
    fake.delays["world.wait"] = 0.5
    waited: list[dict] = []
    worker = threading.Thread(
        target=lambda: waited.append(client.request("world.wait", {"timeoutSeconds": 5}))
    )
    worker.start()
    time.sleep(0.1)
    index = client.request("frames.index")
    assert not waited, "frames.index waited behind world.wait"
    worker.join(5)
    assert set(waited[0]) == {"pose", "time", "joinedQpcNs", "frameIndex", "sinceReload", "qpcNs"}
    received = [r["message"] for r in modfake.log_lines(client.log.path) if r["dir"] == "received"]
    order = [m.get("id") for m in received]
    assert order.index(3) < order.index(2)  # frames.index (3) answered before world.wait (2)
    assert index["frameIndex"] == 100
    client.close()


def test_the_mods_own_timeout_and_a_client_timeout(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    client.hello()
    # The mod's own timeoutSeconds answers first: a coded refusal, not a client timeout.
    fake.delays["ready"] = 5
    args = {"stableFrames": 3, "minSeconds": 0, "timeoutSeconds": 0.1}
    with pytest.raises(modclient.ModRefused) as refused:
        client.request("ready", args, wait=0.3)
    assert refused.value.code == "timeout"
    # A command without timeoutSeconds that never answers: the client gives up and cancels.
    fake.delays["state"] = 5
    began = time.monotonic()
    with pytest.raises(modclient.ModTimeout, match=r"state 3: no answer within 0.3 s; cancel sent"):
        client.request("state", wait=0.3)
    assert time.monotonic() - began < 2
    deadline = time.monotonic() + 5
    while len(client.stray) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fake.cancelled == [3]
    codes = sorted((m["id"], m["ok"], m.get("error", {}).get("code")) for m in client.stray)
    assert codes == [(3, False, "cancelled"), (4, True, None)]  # the request, then the cancel
    # The session goes on.
    assert client.request("frames.index")["frameIndex"] == 100
    client.close()


def test_the_fake_answers_busy_and_unsupported_as_the_mod(tmp_path: Path) -> None:
    fake = modfake.Fake(TOKEN, built=["frames.index", "frames.capture", "command", "quit"])
    client, _ = session(tmp_path, fake)
    hello = client.hello()
    assert hello["capabilities"] == [
        "hello",
        "command",
        "frames.index",
        "frames.capture",
        "cancel",
        "quit",
    ]
    with pytest.raises(modclient.ModRefused, match="state: unsupported"):
        client.request("state")
    fake.delays["frames.capture"] = 0.5
    capture = {"directory": str(tmp_path / "d"), "count": 3, "timeoutSeconds": 5}
    worker = threading.Thread(target=lambda: client.request("frames.capture", capture))
    worker.start()
    time.sleep(0.1)
    with pytest.raises(modclient.ModRefused, match=r"frames.capture: busy: capture is in use"):
        client.request("frames.capture", capture)
    with pytest.raises(modclient.ModRefused, match="command: busy: capture active"):
        client.request("command", {"text": "/tick freeze", "timeoutSeconds": 5})
    worker.join(5)
    assert client.request("command", {"text": "/tick freeze", "timeoutSeconds": 5})["succeeded"]
    client.close()


def test_the_game_helpers_against_the_fake(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    client.hello()
    joined = client.world_wait(30)
    assert joined["pose"]["dimension"] == "minecraft:overworld" and joined["time"] == 6000
    state = client.state()
    assert state["inWorld"] and state["gamemode"] == "spectator" and state["focused"]
    assert state["framebuffer"] == {"width": 3840, "height": 2160}
    assert client.command("/tick freeze")["messages"] == ["fake: tick freeze"]
    assert fake.game["frozen"]
    assert client.ticks_step(20, 5)["ticks"] == 20
    pose = {"x": -533.3, "y": 75.0, "z": -368.25, "yaw": 12.3, "pitch": -4.5}
    placed = client.camera_place(pose, 30)
    assert modclient.pose_differences(pose, placed["pose"]) == []
    got = client.camera_get()
    assert modclient.pose_differences(placed["pose"], got["pose"]) == []
    assert got["eye"]["y"] == pytest.approx(75.0 + modfake.EYE_HEIGHT)
    nether = {**pose, "dimension": "minecraft:the_nether"}
    assert client.camera_place(nether, 30)["pose"]["dimension"] == "minecraft:the_nether"
    event = client.next_event(5)
    assert event["event"] == "dimension.changed"
    assert event["data"] == {"from": "minecraft:overworld", "to": "minecraft:the_nether"}
    sent = [r["message"] for r in modfake.log_lines(client.log.path) if r["dir"] == "sent"]
    assert sent[-1]["args"] == {
        **pose,
        "dimension": "minecraft:the_nether",
        "tpSemantics": False,
        "timeoutSeconds": 30,
    }
    assert client.hud_set(hide_gui=True)["hideGui"] is True
    assert client.hud_set()["hideGui"] is True, "an empty hud.set reads the flags"
    assert client.hud_set(debug_overlay=False)["debugOverlay"] is False
    assert client.input_block(True)["on"] is True and fake.game["inputBlocked"]
    assert client.input_block(False)["on"] is False
    client.close()


def test_the_render_helpers_against_the_fake(tmp_path: Path) -> None:
    client, _fake = session(tmp_path)
    client.hello()
    ready = client.ready(10, 0.5, 60)
    assert ready["limitedBy"] == "stableFrames" and ready["rendererCheck"]["holds"] is True
    client.request("frames.index")
    reloaded = client.shaders_reload(30, pack="fake-pack.zip")
    assert reloaded["pack"] == "fake-pack.zip" and reloaded["framesAfter"] == 2
    # Answered after framesAfter frames of the new pipeline: sinceReload counts from reloadFrame.
    assert reloaded["frameIndex"] - reloaded["reloadFrame"] == reloaded["framesAfter"] + 1
    assert reloaded["sinceReload"] == reloaded["frameIndex"] - reloaded["reloadFrame"]
    event = client.next_event(5)
    assert event["event"] == "reload.done" and event["data"]["pack"] == "fake-pack.zip"
    after = client.request("frames.index")
    assert after["sinceReload"] == after["frameIndex"] - reloaded["reloadFrame"]
    with pytest.raises(modclient.ModError, match=r"not the requested other.zip"):
        client.shaders_reload(30, pack="other.zip")
    assert client.shaders_options()["values"] == {"FAKE_BOOL": True, "FAKE_VALUE": "2"}
    captured = client.frames_capture(tmp_path / "captures", 3, 30, every=1)
    assert [f["name"] for f in captured["frames"]] == [f"frame-{n:05d}.png" for n in (1, 2, 3)]
    assert captured["verified"]["frames"] == 3 and captured["verified"]["complete"] is True
    assert Path(captured["manifest"]).parent.name == "attempt-001"
    again = client.frames_capture(tmp_path / "captures", 1, 30)
    assert Path(again["manifest"]).parent.name == "attempt-002", "a new folder per attempt"
    with pytest.raises(modclient.ModRefused, match="not absolute"):
        client.frames_capture(Path("relative"), 1, 30)
    result = client.selftest(60)
    assert result["pass"] is True and set(result["checks"]) == set(modfake.SELFTEST_CHECKS)
    client.close()


def test_the_window_against_the_fake(tmp_path: Path) -> None:
    """window.measure: `after: reload` needs a reload since the last pipeline creation; the skip
    counts from it and the window from the first frame past it; frames are end minus start, and
    window.start and window.end carry the answer's marks; the unbuilt arguments are refused."""
    client, _ = session(tmp_path)
    client.hello()
    with pytest.raises(modclient.ModRefused) as refused:
        client.window_measure("reload", 1.5, 2.5)
    assert refused.value.code == "not-ready"
    reloaded = client.shaders_reload(30)
    assert client.next_event(5)["event"] == "reload.done"
    window = client.window_measure("reload", 1.5, 2.5)
    start, end = window["start"], window["end"]
    assert start["qpcNs"] >= reloaded["reloadFrame"] * modfake.FRAME_NS + 1_500_000_000
    assert window["frames"] == end["frameIndex"] - start["frameIndex"] > 0
    assert window["seconds"] >= 2.5 and window["skippedSeconds"] >= 1.5
    assert start["sinceReload"] == start["frameIndex"] - reloaded["reloadFrame"]
    events = [client.next_event(5) for _ in range(2)]
    assert [e["event"] for e in events] == ["window.start", "window.end"]
    assert events[0]["data"] == start
    assert events[1]["data"] == {**end, "frames": window["frames"]}
    assert client.window_measure("now", 0, 0.1)["start"]["frameIndex"] > end["frameIndex"]
    # A dimension change makes a new pipeline: no anchor until the next reload.
    nether = {"dimension": "minecraft:the_nether", "x": 0.5, "y": 70.0, "z": 0.5, "yaw": 0.0}
    client.camera_place({**nether, "pitch": 0.0}, 30)
    with pytest.raises(modclient.ModRefused, match="not-ready"):
        client.window_measure("reload", 0, 1)
    for args, code in (
        ({"after": "now", "skipFrames": 3, "frames": 10}, "unsupported"),
        ({"after": "path", "skipSeconds": 1, "seconds": 1}, "unsupported"),
        ({"after": "now", "seconds": 1}, "bad-request"),
    ):
        with pytest.raises(modclient.ModRefused) as refused:
            client.request("window.measure", args)
        assert refused.value.code == code, args
    client.close()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda found: {**found, "frames": found["frames"] + 1}, r"frames \d+, its marks span \d+"),
        (
            lambda found: {**found, "start": {**found["start"], "swapQpcNs": None}},
            "its start lacks swapQpcNs",
        ),
        (
            lambda found: {**found, "end": {k: v for k, v in found["end"].items() if k != "qpcNs"}},
            "its end lacks qpcNs",
        ),
        (lambda found: {**found, "end": [1]}, "its end lacks frameIndex"),
    ],
)
def test_the_window_helper_refuses_an_answer_whose_marks_disagree(
    tmp_path: Path, change, message: str
) -> None:
    class Off(modfake.Fake):
        def _window(self, args: dict) -> dict:
            return change(super()._window(args))

    client, _ = session(tmp_path, Off(TOKEN))
    client.hello()
    with pytest.raises(modclient.ModError, match=message):
        client.window_measure("now", 0, 0.1)
    client.close()


def test_the_window_waits_for_its_skip_and_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """window.measure has no timeoutSeconds: the client's wait covers the skip and the window
    from now, plus MARGIN, so a 4 s settle and a 2.5 s window outlast DEFAULT_WAIT's 10 s."""
    client, _ = session(tmp_path)
    client.hello()
    waits = []
    answer = client.answer
    monkeypatch.setattr(
        client, "answer", lambda c, a=None, wait=None: waits.append(wait) or answer(c, a, wait)
    )
    client.window_measure("now", 4.0, 2.5)
    assert waits == [4.0 + 2.5 + modclient.MARGIN]
    client.close()


def test_the_fake_keeps_a_window_out_while_a_mutation_runs(tmp_path: Path) -> None:
    """As the mod's Protocol.dispatch: an exclusive request answers busy while a mutating one's
    handler runs, its early `timeout` notwithstanding."""
    client, fake = session(tmp_path)
    client.hello()
    fake.delays["shaders.reload"] = 0.8
    with pytest.raises(modclient.ModRefused) as refused:
        client.request("shaders.reload", {"timeoutSeconds": 0.2})
    assert refused.value.code == "timeout"
    with pytest.raises(modclient.ModRefused, match="busy: a mutation is running"):
        client.window_measure("now", 0, 0.1)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.window_measure("now", 0, 0.1)
            break
        except modclient.ModRefused as error:
            assert error.code == "busy"
            time.sleep(0.05)
    else:
        pytest.fail("the window stayed busy after the reload's handler ended")
    # A steered failed reload drops the anchor, as the mod's does.
    del fake.delays["shaders.reload"]
    client.shaders_reload(30)
    fake.refusals["shaders.reload"] = ("iris-compile-error", "broken")
    with pytest.raises(modclient.ModRefused, match="iris-compile-error"):
        client.shaders_reload(30)
    with pytest.raises(modclient.ModRefused, match="not-ready"):
        client.window_measure("reload", 0, 0.1)
    client.close()


def test_the_fake_keeps_a_window_and_a_capture_apart(tmp_path: Path) -> None:
    """commands.json `excludes`, as the mod reads it: each answers busy beside the other."""
    client, fake = session(tmp_path)
    client.hello()
    fake.delays["frames.capture"] = 0.5
    capture = {"directory": str(tmp_path / "d"), "count": 1, "timeoutSeconds": 5}
    worker = threading.Thread(target=lambda: client.request("frames.capture", capture))
    worker.start()
    time.sleep(0.1)
    with pytest.raises(modclient.ModRefused, match="busy: capture is in use"):
        client.window_measure("now", 0, 0.1)
    worker.join(5)
    fake.delays["window.measure"] = 0.5
    worker = threading.Thread(target=lambda: client.window_measure("now", 0, 0.1))
    worker.start()
    time.sleep(0.1)
    with pytest.raises(modclient.ModRefused, match="busy: window is in use"):
        client.request("frames.capture", capture)
    worker.join(5)
    client.close()


def advance(client: modclient.Client, until: int) -> int:
    """The fake's frame clock moved to `until` or past through frames.index; the frame now."""
    now = client.request("frames.index")["frameIndex"]
    while now < until:
        now = client.request("frames.index")["frameIndex"]
    return now


def test_the_timers_against_the_fake(tmp_path: Path) -> None:
    """timers.start holds the timers resource until timers.stop: a second start and a mutation
    answer busy meanwhile; a read takes the frames that ended before it, each with Iris's passes
    in push order, answered once the mod read them; a stop takes the rest, the frame in progress
    included, and frees the resource; read and stop answer not-ready without a start; maxFrames
    (its first drop pushed as timers.dropped) and perPass as the mod's; a disconnect stops them."""
    fake = modfake.Fake(TOKEN)
    stream, serving = modfake.serve_streams(fake)
    client = modclient.Client(stream, TOKEN, tmp_path / "requests.jsonl", os.getpid())
    client.hello()
    for command in ("timers.read", "timers.stop"):
        with pytest.raises(modclient.ModRefused) as refused:
            client.request(command)
        assert refused.value.code == "not-ready", command
    started = client.timers_start(max_pending=3, max_frames=600)
    assert (started["perPass"], started["maxPending"], started["maxFrames"]) == (True, 3, 600)
    first = started["frameIndex"] + 1
    with pytest.raises(modclient.ModRefused, match=r"timers.start: busy: timers is in use"):
        client.timers_start()
    with pytest.raises(modclient.ModRefused, match="command: busy: timers active"):
        client.command("/tick freeze")
    now = advance(client, first + 2)
    read = client.timers_read()
    assert [f["frameIndex"] for f in read["frames"]] == list(range(first, now))
    assert read["frameIndex"] > now, "answered once the mod read them, frames later"
    expected = [{"name": n, "depth": d, "gpuNanos": g} for n, d, g in modfake.FAKE_PASSES]
    assert all(frame["passes"] == expected for frame in read["frames"])
    assert modclient.top_level_nanos(read["frames"][0]) == 6_850_000
    assert read["dropped"] == {"late": 0, "full": 0, "overflow": 0, "lost": 0}
    later = advance(client, read["frameIndex"] + 2)
    stopped = client.timers_stop()
    assert [f["frameIndex"] for f in stopped["frames"]] == list(range(now, later + 1))
    assert stopped["frameIndex"] > later
    assert client.command("/tick freeze")["succeeded"], "the stop freed the resource"
    with pytest.raises(modclient.ModRefused, match=r"timers.read: not-ready"):
        client.timers_read()
    started = client.timers_start(per_pass=False, max_frames=2)
    ended = advance(client, started["frameIndex"] + 6) - started["frameIndex"] - 1
    read = client.timers_read()
    assert len(read["frames"]) == 2 and read["dropped"]["full"] == ended - 2 >= 3
    assert all(item["depth"] == 0 for item in read["frames"][0]["passes"])
    event = client.next_event(5)
    assert event is not None and event["event"] == "timers.dropped"
    assert event["data"] == {"count": 1, "frameIndex": started["frameIndex"] + 3, "reason": "full"}
    client.close()
    serving.join(5)
    assert fake.game["timers"] is None, "a disconnect left the timers running"
    stream, serving = modfake.serve_streams(fake)
    again = modclient.Client(stream, TOKEN, tmp_path / "again.jsonl", os.getpid())
    again.hello()
    with pytest.raises(modclient.ModRefused, match="not-ready"):
        again.timers_read()
    assert again.command("/tick freeze")["succeeded"]
    again.close()


def test_the_timers_waits_outlast_the_mods_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeouts nest (docs/mod-protocol.md#client-rules): the client waits for timers.read and
    timers.stop the mod's own bounds, read from Timers.java, plus MARGIN."""
    source = (REPO_ROOT / "mod/src/main/java/optilux/helper/core/Timers.java").read_text(
        encoding="utf-8"
    )
    bounds = {
        name: int(value.replace("_", "")) / 1e9
        for name, value in re.findall(r"(READ_WAIT_NANOS|DRAIN_NANOS) = ([\d_]+)L;", source)
    }
    assert bounds == {
        "READ_WAIT_NANOS": modclient.TIMERS_READ_SECONDS,
        "DRAIN_NANOS": modclient.TIMERS_DRAIN_SECONDS,
    }
    client, _ = session(tmp_path)
    client.hello()
    waits = []
    answer = client.answer
    monkeypatch.setattr(
        client,
        "answer",
        lambda c, a=None, wait=None: waits.append((c, wait)) or answer(c, a, wait),
    )
    client.timers_start()
    client.timers_read()
    client.timers_stop()
    assert waits == [
        ("timers.read", modclient.TIMERS_READ_SECONDS + modclient.MARGIN),
        ("timers.stop", modclient.TIMERS_DRAIN_SECONDS + modclient.MARGIN),
    ]
    client.close()


def test_the_fake_keeps_the_timers_and_a_mutation_apart(tmp_path: Path) -> None:
    """As the mod's Protocol.dispatch: timers.start answers busy while a mutating request's
    handler runs, its early `timeout` notwithstanding, and a mutation while the timers run."""
    client, fake = session(tmp_path)
    client.hello()
    fake.delays["shaders.reload"] = 0.8
    with pytest.raises(modclient.ModRefused) as refused:
        client.request("shaders.reload", {"timeoutSeconds": 0.2})
    assert refused.value.code == "timeout"
    with pytest.raises(modclient.ModRefused, match="busy: a mutation is running"):
        client.timers_start()
    deadline = time.monotonic() + 5
    while True:
        try:
            client.timers_start()
            break
        except modclient.ModRefused as error:
            assert error.code == "busy" and time.monotonic() < deadline
            time.sleep(0.05)
    del fake.delays["shaders.reload"]
    with pytest.raises(modclient.ModRefused, match=r"shaders.reload: busy: timers active"):
        client.shaders_reload(30)
    client.timers_stop()
    client.shaders_reload(30)
    client.close()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda found: {**found, "frames": found["frames"][::-1]},
            r"frame \d+ follows frame \d+",
        ),
        (lambda found: {**found, "frames": None}, "frames is None, not a list"),
        (lambda found: {**found, "frames": [{"frameIndex": 1}]}, "a frame lacks frameIndex"),
        (
            lambda found: {
                **found,
                "frames": [{"frameIndex": 1, "passes": [{"name": "final", "depth": 0}]}],
            },
            "a pass of frame 1 lacks gpuNanos",
        ),
        (
            lambda found: {
                **found,
                "frames": [
                    {"frameIndex": 1, "passes": [{"name": "c1", "depth": 1, "gpuNanos": 5}]}
                ],
            },
            "pass c1 at depth 1 after depth -1",
        ),
        (
            lambda found: {
                **found,
                "frames": [
                    {"frameIndex": 1, "passes": [{"name": "final", "depth": 0, "gpuNanos": -5}]}
                ],
            },
            "pass final took -5 ns",
        ),
        (lambda found: {**found, "dropped": {"late": 0}}, "lacks late, full, overflow, lost"),
        (lambda found: {**found, "cutPasses": None}, "are not all integers"),
    ],
)
def test_the_timers_helpers_refuse_an_answer_they_cannot_use(
    tmp_path: Path, change, message: str
) -> None:
    class Off(modfake.Fake):
        def _timers(self, name: str, args: dict) -> dict:
            found = super()._timers(name, args)
            return found if name == "timers.start" else change(found)

    client, _ = session(tmp_path, Off(TOKEN))
    client.hello()
    started = client.timers_start()
    advance(client, started["frameIndex"] + 3)
    with pytest.raises(modclient.ModError, match=message):
        client.timers_read()
    client.close()


def test_timers_start_stops_the_timers_it_refuses(tmp_path: Path) -> None:
    """An ok start with other settings than asked is refused, and the timers it started are
    stopped first, so the session's mutations run."""

    class Off(modfake.Fake):
        def _timers(self, name: str, args: dict) -> dict:
            found = super()._timers(name, args)
            return {**found, "maxPending": 4} if name == "timers.start" else found

    client, fake = session(tmp_path, Off(TOKEN))
    client.hello()
    with pytest.raises(modclient.ModError, match=r"timers.start: the mod answered"):
        client.timers_start(max_pending=3)
    assert fake.game["timers"] is None
    assert client.command("/tick freeze")["succeeded"]
    client.close()


def test_a_capture_is_judged_by_its_files(tmp_path: Path) -> None:
    client, _ = session(tmp_path)
    client.hello()

    def capture() -> tuple[dict, Path]:
        answer = client.answer(
            "frames.capture",
            {"directory": str(tmp_path / "c"), "count": 2, "every": 1, "timeoutSeconds": 30},
        )
        return answer, Path(answer["manifest"]).parent

    answer, folder = capture()
    assert modclient.verify_manifest(answer)["frames"] == 2
    (folder / "frame-00002.png").write_bytes(modfake.png(1, 1, bytes(4)))
    with pytest.raises(modclient.ModError, match=r"frame-00002.png: sha256"):
        modclient.verify_manifest(answer)
    answer, folder = capture()
    (folder / "frame-00001.png").unlink()
    with pytest.raises(modclient.ModError, match=r"frame-00001.png"):
        modclient.verify_manifest(answer)
    answer, folder = capture()
    (folder / "extra.png").write_bytes(b"")
    with pytest.raises(modclient.ModError, match=r"does not list: extra.png"):
        modclient.verify_manifest(answer)
    answer, folder = capture()
    (folder / "frame-00001.png").write_bytes(b"GIF89a")
    with pytest.raises(modclient.ModError, match="is no PNG"):
        modclient.verify_manifest(answer)
    answer, folder = capture()
    with pytest.raises(modclient.ModError, match="its frames differ"):
        modclient.verify_manifest({**answer, "frames": answer["frames"][:1]})
    manifest = json.loads((folder / modclient.MANIFEST).read_text(encoding="utf-8"))
    manifest["frames"][0]["name"] = "../frame-00001.png"
    (folder / modclient.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(modclient.ModError, match="no file name beside the manifest"):
        modclient.verify_manifest({**answer, "frames": manifest["frames"]})
    client.close()


def test_the_game_helpers_refuse_what_they_cannot_use(tmp_path: Path) -> None:
    client, fake = session(tmp_path)
    client.hello()
    fake.refusals["camera.get"] = ("not-ready", "not in a world")
    with pytest.raises(modclient.ModRefused, match=r"camera.get: not-ready"):
        client.camera_get()
    with pytest.raises(ValueError, match=r"camera.place: missing argument timeoutSeconds"):
        client.request("camera.place", {"x": 0, "y": 0, "z": 0, "yaw": 0, "pitch": 0})
    with pytest.raises(modclient.ModRefused, match=r"ticks.step: failed: ticks are not frozen"):
        client.ticks_step(1, 5)
    pose = {"x": 0, "y": 0, "z": 0, "yaw": 0, "pitch": 95}
    with pytest.raises(modclient.ModRefused, match=r"camera.place: bad-request: .*pitch 95"):
        client.camera_place(pose, 5)
    assert client.camera_place(pose, 5, tp_semantics=True)["pose"]["pitch"] == 95  # no /tp here
    with pytest.raises(modclient.ModRefused, match=r"camera.place: bad-request: .*the_moon"):
        client.camera_place({**pose, "pitch": 0, "dimension": "minecraft:the_moon"}, 5)
    # A command the game ran without success, and an answer that lacks a field.
    real = fake._game

    def failing(name: str, args: dict) -> dict:
        if name == "command":
            return {"succeeded": False, "messages": [], "failures": ["Unknown command"]}
        if name == "state":
            return {"inWorld": True}
        return real(name, args)

    fake._game = failing
    with pytest.raises(modclient.ModError, match="did not succeed: Unknown command"):
        client.command("/nothing")
    assert client.command("/nothing", check=False)["succeeded"] is False
    with pytest.raises(modclient.ModError, match="state: the answer lacks dimension"):
        client.state()
    client.close()


def test_poses_compare_at_the_games_precision() -> None:
    want = {"dimension": "minecraft:overworld", "x": 1.5, "y": 64, "z": -2.25, "yaw": 12.3}
    want["pitch"] = -4.5
    # The game holds 12.3 as the float 12.300000190734863 and answers that.
    got = {**want, "yaw": 12.300000190734863, "y": 64.0}
    assert modclient.pose_differences(want, got) == []
    assert modclient.pose_differences(want, {**got, "yaw": 12.31}) == [
        "yaw 12.31 != 12.3 as a float"
    ]
    assert modclient.pose_differences(want, {**got, "x": 1.5000000001}) == ["x 1.5000000001 != 1.5"]
    assert modclient.pose_differences(want, {**got, "dimension": "minecraft:the_end"}) == [
        "dimension minecraft:the_end != minecraft:overworld"
    ]
    assert modclient.pose_differences({**want, "dimension": None}, {**got, "z": None}) == [
        "z None is no number"
    ]


def test_the_bounds_the_mod_refuses_are_refused_here() -> None:
    with pytest.raises(ValueError, match="outside the 64-bit range"):
        modclient.check_id("id", 2**63)
    assert modclient.check_id("id", -(2**63)) == -(2**63)
    with pytest.raises(ValueError, match="lone surrogate"):
        modclient.strict_json('{"a": "\\ud800"}')
    with pytest.raises(ValueError, match="out of the double range"):
        modclient.check_value("x", {"type": "number"}, float("inf"))
    with pytest.raises(ValueError, match="over 1048576"):
        modclient.encode({"id": 1, "cmd": "command", "args": {"text": "x" * (1 << 20)}})


def test_waits_nest(tmp_path: Path) -> None:
    client, _fake = session(tmp_path)
    client.hello()
    with pytest.raises(ValueError, match="client wait 4 s must exceed timeoutSeconds 5 s"):
        client.request("world.wait", {"timeoutSeconds": 5}, wait=4)
    with client.within(2):
        with pytest.raises(ValueError, match="does not fit the outer wait"):
            client.request("world.wait", {"timeoutSeconds": 5})
        with pytest.raises(ValueError, match="does not fit the outer wait"):
            client.request("frames.index")  # the default wait, 10 s
        assert client.request("frames.index", wait=1)["frameIndex"] == 100
    client.close()


def test_the_request_log_holds_no_token(tmp_path: Path) -> None:
    client, _fake = session(tmp_path)
    client.hello()
    client.request("frames.index")
    client.note({"check": f"a note quoting {TOKEN}"})
    client.close()
    text = client.log.path.read_text(encoding="utf-8")
    assert TOKEN not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert records[0]["dir"] == "sent"
    assert records[0]["message"] == {
        "id": 1,
        "cmd": "hello",
        "args": {"token": modclient.REDACTED},
    }
    assert {r["dir"] for r in records} == {"sent", "received", "note"}
    assert records[-2]["message"] == {"check": f"a note quoting {modclient.REDACTED}"}
    assert all(
        re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", r["at"]) for r in records
    )


def test_strict_json_refuses_what_the_mod_refuses() -> None:
    assert modclient.strict_json('{"a": [1, 2.5, null]}') == {"a": [1, 2.5, None]}
    for bad in ('{"a": NaN}', '{"a": 1, "a": 2}', '{"a": Infinity}', "{'a': 1}"):
        with pytest.raises(ValueError):
            modclient.strict_json(bad)


@pytest.mark.windows
def test_the_client_and_the_fake_over_a_real_named_pipe(tmp_path: Path) -> None:
    from optilux import winpipe

    token = "W" * 40 + str(os.getpid())
    name = modclient.pipe_name(token)
    fake = modfake.Fake(token)
    services: list[modfake.PipeService] = []
    # The fake creates its pipe after the client started retrying.
    starter = threading.Timer(0.3, lambda: services.append(modfake.PipeService(fake, name)))
    starter.start()
    began = time.monotonic()
    client = modclient.connect(token, os.getpid(), tmp_path / "requests.jsonl", timeout=10)
    try:
        assert time.monotonic() - began >= 0.25  # it waited for the pipe
        assert client.server_pid == os.getpid()
        sid = winpipe.current_user_sid()
        aces = [ace.split(";") for ace in re.findall(r"\(([^)]*)\)", client.dacl)]
        assert len(aces) == 1 and aces[0][0] == "A", client.dacl
        assert winpipe.canonical_sid(aces[0][5]) == sid, client.dacl
        assert winpipe.second_instance(name) in (
            winpipe.ERROR_ACCESS_DENIED,
            winpipe.ERROR_PIPE_BUSY,
        )
        assert client.hello()["pid"] == os.getpid()
        assert client.request("frames.index")["frameIndex"] == 100
        client.request("quit")
    finally:
        client.close()
    # A client expecting another server pid refuses the pipe before sending anything.
    with pytest.raises(
        modclient.ModError, match=f"served by pid {os.getpid()}, not the launched 1"
    ):
        modclient.connect(token, 1, None, timeout=10)
    # The fake serves again after the refusal's disconnect.
    again = modclient.connect(token, os.getpid(), None, timeout=10)
    try:
        assert again.hello()["resumed"] is True
    finally:
        again.close()
        services[0].stop()
    assert TOKEN not in (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert token not in (tmp_path / "requests.jsonl").read_text(encoding="utf-8")


@pytest.mark.windows
def test_connect_names_a_pipe_that_never_appears() -> None:
    with pytest.raises(modclient.ModError, match=r"does not exist after 0.2 s"):
        modclient.connect("N" * 43, None, None, timeout=0.2)


@pytest.mark.windows
def test_sids_compare_in_full_form() -> None:
    from optilux import winpipe

    # SDDL writes well-known SIDs as aliases: CI's user, the built-in Administrator, is LA.
    assert winpipe.canonical_sid("SY") == "S-1-5-18"
    sid = winpipe.current_user_sid()
    assert winpipe.canonical_sid(sid) == sid


def raw_peer(tmp_path: Path) -> tuple[modclient.Client, modclient.Stream]:
    """A client on one end of a socket pair; the test writes the mod's side by hand."""
    mine, theirs = modfake.socket_streams()
    return modclient.Client(mine, TOKEN, tmp_path / "requests.jsonl", os.getpid()), theirs


def read_request(stream: modclient.Stream) -> dict:
    line = b""
    while not line.endswith(b"\n"):
        line += stream.read(65536)
    return json.loads(line)


STAMPS = {"frameIndex": 5, "sinceReload": 5, "qpcNs": 1}


def test_a_line_whose_id_no_request_can_have_leaves_the_reader_running(tmp_path: Path) -> None:
    """An id that is a list cannot key a request: the line is stray, and the answer after it
    still reaches its request (the reader once died on it, and every wait timed out)."""
    client, mod = raw_peer(tmp_path)

    def answer() -> None:
        request = read_request(mod)
        mod.write(b'{"id":[1],"ok":true,"result":{}}\n')
        mod.write(json.dumps({"id": request["id"], "ok": True, "result": STAMPS}).encode() + b"\n")

    threading.Thread(target=answer, daemon=True).start()
    assert client.request("frames.index", wait=2.0)["frameIndex"] == 5
    assert client.stray == [{"id": [1], "ok": True, "result": {}}]
    client.close()


def test_an_answer_the_reader_takes_as_the_wait_ends_is_returned(tmp_path: Path) -> None:
    """The reader pops the waiter, then sets its answer: a wait ending between the two is not a
    timeout (the answer would be lost and a cancel sent for a request that completed)."""

    class Slow(modclient.Client):
        def _dispatch(self, line: bytes) -> None:
            message = json.loads(line)
            with self._lock:
                waiter = self._pending.pop(message["id"])
            time.sleep(0.6)  # past the request's wait
            waiter.answer = message
            waiter.done.set()

    mine, mod = modfake.socket_streams()
    client = Slow(mine, TOKEN, tmp_path / "requests.jsonl", os.getpid())

    def answer() -> None:
        request = read_request(mod)
        mod.write(json.dumps({"id": request["id"], "ok": True, "result": STAMPS}).encode() + b"\n")

    threading.Thread(target=answer, daemon=True).start()
    assert client.request("frames.index", wait=0.3)["frameIndex"] == 5
    client.close()


def test_the_fake_refuses_the_capture_arguments_the_mod_refuses(tmp_path: Path) -> None:
    """flush and after wait for M5; align and ready are refused as the mod's Capture refuses
    them (CaptureTest): a cycle not dividing 720720, a phase outside it, a field unknown or
    missing, ready outside the ready command's ranges."""
    client, _ = session(tmp_path)
    client.hello()
    refusals = [
        ({"flush": True}, "unsupported"),
        ({"after": 3}, "unsupported"),
        ({"after": 0}, "unsupported"),
        ({"align": {"cycle": 32, "phase": 0}}, "bad-request"),
        ({"align": {"cycle": 4, "phase": 4}}, "bad-request"),
        ({"align": {"cycle": 4, "phase": True}}, "bad-request"),
        ({"align": {"after": 1}}, "bad-request"),
        ({"align": {"cycle": 4}}, "bad-request"),
        ({"ready": {"stableFrames": 0, "minSeconds": 0}}, "bad-request"),
        ({"ready": {"stableFrames": 10}}, "bad-request"),
        ({"ready": {"stableFrames": 10, "minSeconds": 3601}}, "bad-request"),
        ({"ready": {"stableFrames": 10, "minSeconds": "1"}}, "bad-request"),
    ]
    for later, code in refusals:
        args = {"directory": str(tmp_path / "c"), "count": 1, "timeoutSeconds": 10.0, **later}
        with pytest.raises(modclient.ModRefused) as refused:
            client.request("frames.capture", args)
        assert refused.value.code == code, later
    with pytest.raises(modclient.ModRefused, match="32 does not divide 720720"):
        client.frames_capture(tmp_path / "c", 1, 10.0, align=(32, 0))
    client.close()


def test_aligned_ready_and_imageless_captures_against_the_fake(tmp_path: Path) -> None:
    """align takes only frames at the phase; ready answers its report, whose frame is the
    first taken (the fake's predicate holds at once); without images the frames are stamps
    alone, with no file beside capture.json."""
    client, fake = session(tmp_path)
    client.hello()
    client.shaders_reload(30)
    aligned = client.frames_capture(tmp_path / "c", 3, 30.0, every=1, align=(4, 1))
    assert [f["sinceReload"] % 4 for f in aligned["frames"]] == [1, 1, 1]
    assert aligned["ready"] is None
    before = client.request("frames.index")["frameIndex"]
    shot = client.frames_capture(tmp_path / "c", 2, 30.0, ready=(10, 1.0), images=False)
    assert shot["ready"]["frameIndex"] == shot["frames"][0]["frameIndex"]
    # 1 s of 7 ms frames outlasts 10 stable ones, as the mod's Readiness reports it.
    assert shot["ready"]["limitedBy"] == "minSeconds" and shot["ready"]["frames"] == 143
    assert shot["frames"][0]["frameIndex"] == before + 143
    quick = client.frames_capture(tmp_path / "c", 1, 30.0, ready=(10, 0.0), images=False)
    assert quick["ready"]["limitedBy"] == "stableFrames" and quick["ready"]["frames"] == 10
    assert [sorted(f) for f in shot["frames"]] == [sorted(modclient.MARK_KEYS)] * 2
    assert shot["verified"] == {
        "folder": str(Path(shot["manifest"]).parent),
        "frames": 2,
        "bytes": 0,
        "complete": True,
        "images": False,
    }
    assert [p.name for p in Path(shot["manifest"]).parent.iterdir()] == [modclient.MANIFEST]
    both = client.frames_capture(tmp_path / "c", 1, 30.0, align=(16, 5), ready=(3, 0.0))
    first = both["frames"][0]
    assert first["sinceReload"] % 16 == 5
    assert 0 <= first["frameIndex"] - both["ready"]["frameIndex"] < 16
    sent = [m["args"] for m in fake.received if m.get("cmd") == "frames.capture"]
    assert sent[-1]["align"] == {"cycle": 16, "phase": 5}
    assert sent[-1]["ready"] == {"stableFrames": 3, "minSeconds": 0.0}
    assert sent[1]["images"] is False and sent[0]["images"] is True
    client.close()


def test_the_schedule_check_refuses_what_the_capture_did_not_ask() -> None:
    """check_schedule (plans/m3.md section 7): an aligned frame off its phase; a ready capture
    without a report, or whose first frame (written or dropped) is not the first after it; a
    report for a capture that asked none."""

    def frame(index: int, since: int) -> dict:
        return {"frameIndex": index, "sinceReload": since}

    report = {"frameIndex": 50, "limitedBy": "stableFrames"}
    good = {"frames": [frame(52, 9), frame(56, 13)], "dropped": [], "ready": report}
    modclient.check_schedule(good, (4, 1), True)
    modclient.check_schedule({**good, "ready": None}, (4, 1), False)
    with pytest.raises(modclient.ModError, match="frame 53 at sinceReload 10 lies off phase 1"):
        modclient.check_schedule({**good, "frames": [frame(53, 10)]}, (4, 1), True)
    with pytest.raises(modclient.ModError, match="no report"):
        modclient.check_schedule({**good, "ready": None}, (4, 1), True)
    with pytest.raises(modclient.ModError, match="asked none"):
        modclient.check_schedule(good, (4, 1), False)
    late = {"frames": [frame(51, 4)], "dropped": [], "ready": report}
    with pytest.raises(modclient.ModError, match="first frame 51 is not the first from frame 50"):
        modclient.check_schedule(late, None, True)
    modclient.check_schedule({**late, "dropped": [{"frameIndex": 50}]}, None, True)
    with pytest.raises(modclient.ModError, match="not the first at the phase"):
        modclient.check_schedule({**good, "frames": [frame(56, 13)]}, (4, 1), True)
    early = {"frames": [frame(49, 4)], "dropped": [], "ready": report}
    with pytest.raises(modclient.ModError, match="first frame 49"):
        modclient.check_schedule(early, None, True)
    # intervalMs (a visual run's pair, plans/m3.md D63): each frame that long after the one before.
    spaced = [{**frame(50, 7), "qpcNs": 1_000_000_000}, {**frame(337, 294), "qpcNs": 3_002_000_000}]
    modclient.check_schedule({**good, "frames": spaced}, (1, 0), True, 2000)
    close = [spaced[0], {**spaced[1], "qpcNs": 2_999_000_000}]
    with pytest.raises(modclient.ModError, match=r"frame 337 came 1999\.000 ms after frame 50"):
        modclient.check_schedule({**good, "frames": close}, (1, 0), True, 2000)


def test_a_capture_whose_manifest_disagrees_with_its_request_is_refused(tmp_path: Path) -> None:
    """The client judges what the mod wrote against what it asked: images, and the ready report
    the answer and capture.json both carry."""

    class Pictures(modfake.Fake):
        def _capture(self, args: dict) -> dict:
            return super()._capture({**args, "images": True})

    client, _ = session(tmp_path, Pictures(TOKEN))
    client.hello()
    with pytest.raises(modclient.ModError, match="asked images False"):
        client.frames_capture(tmp_path / "c", 1, 10.0, images=False)
    shot = client.frames_capture(tmp_path / "c", 1, 10.0, ready=(3, 0.0))
    manifest = json.loads(Path(shot["manifest"]).read_text(encoding="utf-8"))
    manifest["ready"]["frameIndex"] += 1
    Path(shot["manifest"]).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(modclient.ModError, match="its ready differ"):
        modclient.verify_manifest(shot)
    client.close()


def test_an_imageless_capture_is_judged_by_its_manifest(tmp_path: Path) -> None:
    """Without images the folder holds capture.json alone and each frame is its stamps."""
    client, _ = session(tmp_path)
    client.hello()
    shot = client.frames_capture(tmp_path / "c", 2, 10.0, images=False)
    folder = Path(shot["manifest"]).parent
    (folder / "frame-00001.png").write_bytes(modfake.png(1, 1, bytes(4)))
    with pytest.raises(modclient.ModError, match=r"does not list: frame-00001\.png"):
        modclient.verify_manifest(shot)
    (folder / "frame-00001.png").unlink()
    manifest = json.loads((folder / modclient.MANIFEST).read_text(encoding="utf-8"))
    manifest["frames"][0]["name"] = "frame-00001.png"
    (folder / modclient.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(modclient.ModError, match="not its stamps alone"):
        modclient.verify_manifest({**shot, "frames": manifest["frames"]})
    client.close()


def test_input_block_waits_out_a_capture_that_answered_timeout(tmp_path: Path) -> None:
    """The mod answers `timeout` first and frees the capture when its handler returns
    (Protocol.stop): until then input.block answers busy, and A2's cleanup waits for it."""
    client, fake = session(tmp_path)
    client.hello()
    fake.delays["frames.capture"] = 1.5
    with pytest.raises(modclient.ModRefused) as refused:
        client.frames_capture(tmp_path / "c", 1, 0.2, every=1)
    assert refused.value.code == "timeout"
    with pytest.raises(modclient.ModRefused) as busy:
        client.input_block(True)
    assert busy.value.code == "busy"
    assert client.input_block_when_free(True, 5.0)["on"] is True
    client.close()


def test_the_manifest_check_refuses_an_unreadable_or_incomplete_manifest(tmp_path: Path) -> None:
    client, _ = session(tmp_path)
    client.hello()
    shot = client.frames_capture(tmp_path / "c", 1, 10.0, every=1)
    manifest = Path(shot["manifest"])
    good = manifest.read_text(encoding="utf-8")
    manifest.write_text("{not json", encoding="utf-8")
    with pytest.raises(modclient.ModError, match=r"capture.json"):
        modclient.verify_manifest(shot)
    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(modclient.ModError, match=r"capture.json"):
        modclient.verify_manifest(shot)
    data = json.loads(good)
    del data["frames"][0]["swapQpcNs"]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(modclient.ModError, match="swapQpcNs"):
        modclient.verify_manifest({**shot, "frames": data["frames"]})
    client.close()


def test_a_request_in_flight_hears_the_pipe_close_at_once(tmp_path: Path) -> None:
    """A game that dies mid-request ends the wait as ModGone, not after the full wait plus a
    cancel to a dead pipe."""
    client, mod = raw_peer(tmp_path)

    def die() -> None:
        read_request(mod)
        mod.close()

    threading.Thread(target=die, daemon=True).start()
    began = time.monotonic()
    with pytest.raises(modclient.ModGone, match="closed first"):
        client.request("frames.index", wait=10.0)
    assert time.monotonic() - began < 5.0
    client.close()
