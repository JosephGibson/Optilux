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
