"""L2 (optilux/l2.py, plans/m3.md D70): RGA's output parsed from a fixture (RGA 2.15's for the
hello pack's final program, gfx1101), a print's programs, a build and a known offline failure
through a stand-in for RGA, `check L2` over a dump record; the pinned RGA itself where
runtime/tools/ holds it (not in CI)."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from optilux import REPO_ROOT, l2, record
from optilux.verbs import check

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


FINAL_VSH = b"#version 330 core\nvoid main() {}\n"
FINAL_FSH = b"#version 330 core\nout vec4 c;\nvoid main() {}\n"


def dumped(root: Path, folder: str = "dumps/overworld/a") -> tuple[dict, dict[str, str]]:
    """A dump's capture and files under root: final's two stages, then basic and basic_color
    with the same text (as Iris prints a ShaderKey's program), a compute stage, a .json and an
    ID map."""
    texts = {
        "patched_shaders/001_final.vsh": FINAL_VSH,
        "patched_shaders/001_final.fsh": FINAL_FSH,
        "patched_shaders/001_final.json": b"{}\n",
        "patched_shaders/002_basic.vsh": FINAL_VSH,
        "patched_shaders/002_basic.fsh": FINAL_FSH + b"// basic\n",
        "patched_shaders/003_basic_color.vsh": FINAL_VSH,
        "patched_shaders/003_basic_color.fsh": FINAL_FSH + b"// basic\n",
        "patched_shaders/004_setup.csh": b"#version 430\nvoid main() {}\n",
        "patched_shaders/entity.properties": b"entity.1=x\n",
    }
    files = {}
    for name, data in texts.items():
        (root / folder / name).parent.mkdir(parents=True, exist_ok=True)
        (root / folder / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    return {"dump": {"folder": folder}}, files


def test_a_prints_programs_group_its_stage_files_by_name(tmp_path: Path) -> None:
    capture, files = dumped(tmp_path)
    (final, basic, color), skipped = l2.programs(tmp_path, capture, files)
    assert (final.name, sorted(final.stages), basic.name, color.name) == (
        "final",
        ["fsh", "vsh"],
        "basic",
        "basic_color",
    )
    assert skipped == ["setup.csh"]  # listed, never dropped unsaid
    assert final.digest != basic.digest and basic.digest == color.digest  # one RGA run for both
    args = l2.command(Path("rga.exe"), final, tmp_path / "out")
    assert args[:5] == ["rga.exe", "-s", "opengl", "-c", "gfx1101"]
    assert "--livereg-sgpr" in args and "--cfg" in args
    assert args[-4:] == ["--vert", str(final.stages["vsh"]), "--frag", str(final.stages["fsh"])]
    twice = {**files, "patched_shaders/009_final.fsh": files["patched_shaders/001_final.fsh"]}
    (tmp_path / capture["dump"]["folder"] / "patched_shaders" / "009_final.fsh").write_bytes(
        FINAL_FSH
    )
    with pytest.raises(l2.L2Error, match=r"two files of the print are final\.fsh"):
        l2.programs(tmp_path, capture, twice)
    files["patched_shaders/002_basic.fsh"] = "0" * 64
    with pytest.raises(l2.L2Error, match="does not hash to its record's sha256"):
        l2.programs(tmp_path, capture, files)


def stand_in(said: str, written: tuple[str, ...] = ("stats", "livereg", "livereg_sgpr")):
    """RGA's stand-in: it prints `said` and writes the fixture's files where RGA would for each
    stage given, of the kinds in `written`."""
    names = {flag: l2.NAMES[ending] for ending, flag in l2.FLAGS.items()}

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        out = Path(args[args.index("-a") + 1]).parent
        for flag in (a for a in args if a in names):
            stage = names[flag]
            for kind in written:
                ending = "csv" if kind == "stats" else "txt"
                name = f"gfx1101_{kind}_{stage}.{ending}"
                (out / name).write_bytes((FIXTURES / name).read_bytes())
        return subprocess.CompletedProcess(args, 0, said.encode(), b"")

    return run


BUILT = "Target GPU detected:\n\nBuilding for gfx1101... succeeded.\n"
FAILED = "Building for gfx1101... failed.\nCompiling final.fsh\n"


def test_a_built_program_reports_each_stage_and_a_failed_one_is_a_known_offline_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, files = dumped(tmp_path)
    (final, *_), _ = l2.programs(tmp_path, capture, files)
    out = tmp_path / "l2" / "final"
    monkeypatch.setattr(l2.subprocess, "run", stand_in(BUILT))
    built = l2.analyze(Path("rga.exe"), final, out)
    assert (built["failed"], built["tool"]) == ({}, None)
    assert built["stages"]["vsh"]["vgprs"] == 9 and built["stages"]["fsh"]["liveVgprs"] == 4
    assert built["stages"]["vsh"]["liveSgprs"] == 40
    # A rerun starts from an empty folder: a failed build never reads the last run's figures.
    monkeypatch.setattr(l2.subprocess, "run", stand_in(FAILED, ()))
    failed = l2.analyze(Path("rga.exe"), final, out)
    assert failed["stages"] == {} and failed["failed"] == {
        "vsh": ["Building for gfx1101... failed.", "Compiling final.fsh"],
        "fsh": ["Building for gfx1101... failed.", "Compiling final.fsh"],
    }
    assert sorted(p.name for p in out.iterdir()) == ["rga.txt"]
    # A built stage lacking a figure is named, never passed with the figure missing.
    monkeypatch.setattr(l2.subprocess, "run", stand_in(BUILT, ("stats", "livereg")))
    short = l2.analyze(Path("rga.exe"), final, out)
    assert short["stages"] == {} and short["failed"]["vsh"] == [
        "RGA's livereg_sgpr file for vsh states no peak"
    ]
    monkeypatch.setattr(l2.subprocess, "run", stand_in("", ()))
    assert l2.analyze(Path("rga.exe"), final, out)["tool"].startswith("RGA built nothing")


def l2_root(tmp_path: Path, status: str = "ok") -> Path:
    """A root holding a dump record of one variant in two dimensions, sharing one print."""
    root = tmp_path / "root"
    capture, files = dumped(root / record.RAW / "m3-dump-test")
    manifest = record.dump_manifest(files)
    captures = [
        {
            "index": n,
            "view": "v",
            "dimension": dim,
            "variant": "a",
            "dump": {**capture["dump"], "files": len(files), "manifest": manifest, "dated": {}},
            "valid": True,
        }
        for n, dim in enumerate(record.DIMENSIONS[:2], start=1)
    ]
    found = {
        "name": "m3-dump-test",
        "kind": record.DUMP,
        "status": status,
        "raw": f"{record.RAW}/m3-dump-test",
        "variants": [{"id": "a"}],
        "captures": captures,
        "dumps": {manifest: files},
    }
    (root / record.RECORDS).mkdir(parents=True)
    path = root / record.RECORDS / "m3-dump-test.json"
    path.write_text(json.dumps(found), encoding="utf-8")
    return root


def test_check_l2_names_each_programs_stages_under_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = l2_root(tmp_path)
    monkeypatch.setattr(check, "rga_exe", lambda root_: (Path("rga.exe"), "2.15.0.30"))
    monkeypatch.setattr(l2.subprocess, "run", stand_in(BUILT))
    found = check.run_l2(root, "m3-dump-test")
    (printed,) = found["prints"]
    assert [d["dimension"] for d in printed["dumps"]] == list(record.DIMENSIONS[:2])
    assert len(found["results"]) == 2 and found["failures"] == []
    assert printed["notBuilt"] == ["setup.csh"]
    assert (root / found["folder"] / "l2.json").is_file()
    check.print_l2(found)
    said = capsys.readouterr().out
    for name in ("final.vsh: VGPRs 9", "basic.fsh: VGPRs 4", "basic_color.fsh: VGPRs 4"):
        assert name in said
    assert "setup.csh: not built" in said and "6 stages in 2 distinct programs" in said
    monkeypatch.setattr(l2.subprocess, "run", stand_in("", ()))
    with pytest.raises(l2.L2Error, match="not a shader's failure: RGA built nothing"):
        check.run_l2(root, "m3-dump-test")
    with pytest.raises(l2.L2Error, match="ended failed; L2 reads an ok dump record's"):
        check.run_l2(l2_root(tmp_path / "failed", "failed"), "m3-dump-test")


@needs_rga
def test_the_pinned_rga_builds_the_hello_packs_final_program(tmp_path: Path) -> None:
    stages = {e: REPO_ROOT / "shader" / "shaders" / f"final.{e}" for e in ("vsh", "fsh")}
    program = l2.Program("final", stages, "0" * 64)
    found = l2.analyze(RGA, program, tmp_path / "final")
    assert (found["failed"], found["tool"]) == ({}, None), found
    assert found["stages"]["fsh"]["vgprs"] > 0 and found["stages"]["vsh"]["liveVgprs"] > 0
    assert (tmp_path / "final" / "gfx1101_isa_frag.txt").is_file()
    assert (tmp_path / "final" / "gfx1101_cfg_vert.dot").is_file()
    assert check.rga_exe(REPO_ROOT)[1] == "2.15.0.30"
