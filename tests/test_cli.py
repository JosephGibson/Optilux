"""The CLI contract: no verb is a usage error exiting 1; every M0 verb is registered."""

import pytest

from optilux import cli


def test_no_verb_prints_usage_and_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 1
    err = capsys.readouterr().err
    assert err.startswith("usage: optilux")
    assert "optilux --help" in err


def test_test_verb_is_registered() -> None:
    assert "test" in [verb.name for verb in cli.VERBS]
    assert cli.build_parser().parse_args(["test"]).verb == "test"


def test_test_verb_runs_in_parallel_unless_serial() -> None:
    from optilux.verbs import test as test_verb

    assert cli.build_parser().parse_args(["test", "--serial"]).serial is True
    assert test_verb.command(serial=False)[-2:] == ["-n", "auto"]
    assert "-n" not in test_verb.command(serial=True)


def test_run_names_an_os_error_before_its_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A world a running game still locks fails the snapshot hash with PermissionError: `run`
    says so with a fix, never a traceback."""
    from optilux.verbs import run as run_verb

    def locked(*args: object) -> dict:
        raise PermissionError(13, "Permission denied", "saves/spike/session.lock")

    monkeypatch.setattr(run_verb, "perform", locked)
    assert cli.main(["run", "spec.json"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("optilux run: ") and "session.lock" in err and "fix:" in err
