"""L2 (optilux/l2.py, plans/m3.md D70): RGA's output parsed from a fixture (RGA 2.15's for the
hello pack's final program, gfx1101), a print's programs, a build and a known offline failure
through a stand-in for RGA; the pinned RGA itself where runtime/tools/ holds it (not in CI)."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from optilux import REPO_ROOT, l2

FIXTURES = Path(__file__).parent / "fixtures" / "l2"
PIN = json.loads((REPO_ROOT / "config" / "tools.json").read_text(encoding="utf-8"))["rga"]
RGA = REPO_ROOT / "runtime" / "tools" / PIN["unpack"] / PIN["exe"]
needs_rga = pytest.mark.skipif(not RGA.is_file(), reason="no RGA under runtime/tools/")


def test_rgas_statistics_and_live_registers_parse_from_its_files() -> None:
    frag = l2.parse_stats((FIXTURES / "gfx1101_stats_frag.csv").read_text(encoding="utf-8"))
    vert = l2.parse_stats((FIXTURES / "gfx1101_stats_vert.csv").read_text(encoding="utf-8"))
    assert frag == {
        "vgprs": 4,
        "sgprs": 16,
        "vgprSpills": 0,
        "sgprSpills": 0,
        "scratch": 0,
        "isaBytes": 324,
    }
    assert (vert["vgprs"], vert["sgprs"], vert["isaBytes"]) == (9, 44, 700)
    live = (FIXTURES / "gfx1101_livereg_vert.txt").read_text(encoding="utf-8")
    sgpr = (FIXTURES / "gfx1101_livereg_sgpr_vert.txt").read_text(encoding="utf-8")
    assert l2.parse_live(live, l2.LIVE_VGPRS) == 9
    assert l2.parse_live(sgpr, l2.LIVE_SGPRS) == 40
    assert l2.parse_live("no summary", l2.LIVE_VGPRS) is None
    # RGA writes CRLF; the parse reads either.
    crlf = (FIXTURES / "gfx1101_stats_frag.csv").read_text(encoding="utf-8").replace("\n", "\r\n")
    assert l2.parse_stats(crlf) == frag
    with pytest.raises(l2.L2Error, match="hold 0 rows"):
        l2.parse_stats(crlf.splitlines()[0])


def dumped(tmp_path: Path) -> tuple[dict, dict[str, str]]:
    """A dump's capture and files under tmp_path: final's two stages, basic's fragment stage,
    a .json and an ID map (no stages of RGA's)."""
    folder = tmp_path / "dumps" / "overworld" / "a"
    texts = {
        "patched_shaders/001_final.vsh": b"#version 330 core\nvoid main() {}\n",
        "patched_shaders/001_final.fsh": b"#version 330 core\nout vec4 c;\nvoid main() {}\n",
        "patched_shaders/001_final.json": b"{}\n",
        "patched_shaders/002_basic.fsh": b"#version 330 core\nvoid main() {}\n",
        "patched_shaders/entity.properties": b"entity.1=x\n",
    }
    files = {}
    for name, data in texts.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    return {"dump": {"folder": "dumps/overworld/a"}}, files


def test_a_prints_programs_group_its_stage_files_by_name(tmp_path: Path) -> None:
    capture, files = dumped(tmp_path)
    final, basic = l2.programs(tmp_path, capture, files)
    assert (final.name, sorted(final.stages), basic.name, sorted(basic.stages)) == (
        "final",
        ["fsh", "vsh"],
        "basic",
        ["fsh"],
    )
    assert final.digest != basic.digest and len(final.digest) == 64
    args = l2.command(Path("rga.exe"), final, tmp_path / "out")
    assert args[:5] == ["rga.exe", "-s", "opengl", "-c", "gfx1101"]
    assert "--livereg-sgpr" in args and "--cfg" in args
    assert args[-4:] == ["--vert", str(final.stages["vsh"]), "--frag", str(final.stages["fsh"])]
    files["patched_shaders/002_basic.fsh"] = "0" * 64
    with pytest.raises(l2.L2Error, match="does not hash to its record's sha256"):
        l2.programs(tmp_path, capture, files)


def stand_in(succeeds: bool):
    """RGA's stand-in: on success it writes the fixture's files where RGA would, per stage."""

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        out = Path(args[args.index("-a") + 1]).parent
        stages = [args[n + 1] for n, a in enumerate(args) if a in l2.FLAGS.values()]
        if succeeds:
            for stage in ("vert", "frag")[: len(stages)]:
                for name in (f"gfx1101_stats_{stage}.csv", f"gfx1101_livereg_{stage}.txt"):
                    (out / name).write_bytes((FIXTURES / name).read_bytes())
        said = "succeeded." if succeeds else "failed.\nCompiling final.fsh\nERROR: 0:2: oops"
        return subprocess.CompletedProcess(
            args, 0, f"Building for gfx1101... {said}\n".encode(), b""
        )

    return run


def test_a_built_program_reports_each_stage_and_a_failed_one_is_a_known_offline_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, files = dumped(tmp_path)
    final, _ = l2.programs(tmp_path, capture, files)
    monkeypatch.setattr(l2.subprocess, "run", stand_in(True))
    built = l2.analyze(Path("rga.exe"), final, tmp_path / "l2" / "final")
    assert built["failed"] == [] and built["stages"]["vsh"]["vgprs"] == 9
    assert built["stages"]["fsh"]["liveVgprs"] == 4 and built["stages"]["fsh"]["liveSgprs"] is None
    monkeypatch.setattr(l2.subprocess, "run", stand_in(False))
    failed = l2.analyze(Path("rga.exe"), final, tmp_path / "l2" / "broken")
    assert failed["stages"] == {} and failed["failed"] == [
        "Building for gfx1101... failed.",
        "Compiling final.fsh",
        "ERROR: 0:2: oops",
    ]
    assert "failed." in (tmp_path / "l2" / "broken" / "rga.txt").read_text(encoding="utf-8")


@needs_rga
def test_the_pinned_rga_builds_the_hello_packs_final_program(tmp_path: Path) -> None:
    stages = {e: REPO_ROOT / "shader" / "shaders" / f"final.{e}" for e in ("vsh", "fsh")}
    program = l2.Program("final", stages, "0" * 64)
    found = l2.analyze(RGA, program, tmp_path / "final")
    assert found["failed"] == [], found["failed"]
    assert found["stages"]["fsh"]["vgprs"] > 0 and found["stages"]["vsh"]["liveVgprs"] is not None
    assert (tmp_path / "final" / "gfx1101_isa_frag.txt").is_file()
    assert (tmp_path / "final" / "gfx1101_cfg_vert.dot").is_file()
