"""L4 (optilux/l4.py, plans/m4.md M4.P05): a replay's JSON parsed from a fixture into shares per
program and group, the ungrouped share and the cutout draws' part of it; pass outputs tiered on
fixture targets, on their used pixels; the decision powers held (a replay A/B never closes);
`check L4` over a capture record through a stand-in for qrenderdoc; the replay script's Python 3.8
grammar; the pinned qrenderdoc on M4.P04's smallest capture where both are here (not in CI)."""

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from optilux import REPO_ROOT, l4, l4replay, record
from optilux.verbs import check

FIXTURES = Path(__file__).parent / "fixtures" / "l4"
REPLAYED = json.loads((FIXTURES / "replay.json").read_text(encoding="utf-8"))
PIN = json.loads((REPO_ROOT / "config" / "tools.json").read_text(encoding="utf-8"))["renderdoc"]
SMALLEST = "m4-capture-3"


def test_a_replays_events_parse_into_shares_per_program_and_group() -> None:
    events = l4.parse_events(REPLAYED, "fixture")
    assert len(events) == 12 and events[1] == l4.Event(
        10, "glDrawArrays(6)", "draw", ("Sky",), "sky_basic", 0.4
    )
    found = l4.attribution(events)
    assert found["power"] == "explain"
    assert found["frameMs"] == pytest.approx(10.0)
    assert (found["events"], found["draws"]) == (12, 8)
    programs = {r["name"]: r["share"] for r in found["programs"]}
    assert programs == pytest.approx(
        {
            "sodium_terrain_solid": 0.30,
            "sodium_terrain_cutout": 0.25,
            "composite6": 0.12,
            "shadow_sodium_terrain_cutout": 0.10,
            "(copies)": 0.05,
            "(blits)": 0.05,
            "sky_basic": 0.04,
            "final": 0.04,
            "(mipmaps)": 0.03,
            "(clears)": 0.01,
            "Program 428": 0.01,
        }
    )
    assert found["programs"][0]["name"] == "sodium_terrain_solid"  # largest first
    groups = {r["name"]: r["share"] for r in found["groups"]}
    assert groups == pytest.approx(
        {
            "Terrain solid": 0.50,
            l4.UNGROUPED: 0.17,
            "composite": 0.15,
            "Shadow Terrain solid": 0.10,
            "Sky": 0.04,
            "final": 0.04,
        }
    )
    paths = {r["name"]: r["share"] for r in found["paths"]}
    assert paths["composite / composite6"] == pytest.approx(0.15)
    assert sum(r["share"] for r in found["programs"]) == pytest.approx(1.0)
    assert found["unlabelled"] == pytest.approx(0.01)


def test_the_ungrouped_share_and_the_cutout_draws_part_of_it() -> None:
    found = l4.attribution(l4.parse_events(REPLAYED, "fixture"))
    outside = found["ungrouped"]
    assert outside["share"] == pytest.approx(0.17)
    assert [r["name"] for r in outside["entries"]] == [
        "(blits)",
        "(copies)",
        "sodium_terrain_cutout",
        "(clears)",
        "Program 428",
    ]
    cut = found["cutout"]
    # The main pass's and the shadow pass's cutout programs (P10), wherever they lie.
    assert (cut["draws"], cut["ms"], cut["share"]) == (3, pytest.approx(3.5), pytest.approx(0.35))
    assert {r["name"]: r["share"] for r in cut["groups"]} == pytest.approx(
        {"Terrain solid": 0.20, "Shadow Terrain solid": 0.10, l4.UNGROUPED: 0.05}
    )
    assert cut["ungroupedMs"] == pytest.approx(0.5)
    assert cut["ofUngrouped"] == pytest.approx(0.5 / 1.7)
    grouped = {**REPLAYED, "events": [e for e in REPLAYED["events"] if e["groups"]]}
    assert l4.attribution(l4.parse_events(grouped, "fixture"))["cutout"]["ofUngrouped"] is None


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"event": 10}, "event id 10 is no int or comes twice"),
        ({"ms": -0.1}, "duration -0.1 is no number"),
        ({"ms": True}, "duration True is no number"),
        ({"groups": "Sky"}, "groups is no list of names"),
        ({"kind": "clear"}, "a clear runs no program, yet names sky_basic"),
        ({"program": 7}, "program 7 is no label or null"),
    ],
)
def test_a_replays_events_are_refused_when_malformed(change: dict, match: str) -> None:
    events = [dict(e) for e in REPLAYED["events"]]
    events[2] = {**events[1], **change} if "event" in change else events[2]
    if "event" not in change:
        events[1] = {**events[1], **change}
    with pytest.raises(l4.L4Error, match=match):
        l4.parse_events({"events": events}, "fixture")
    with pytest.raises(l4.L4Error, match="holds no timed events"):
        l4.parse_events({"events": []}, "fixture")


# Pass outputs on fixture targets: 4x2 pixels, the sky in the first row's two left pixels.

WIDTH, HEIGHT = 4, 2
SKY = [0, 1]  # flat pixel indices the depth leaves at the far value


def depth_image(far: float, near: float) -> bytes:
    values = np.full(WIDTH * HEIGHT, near, dtype="<f4")
    values[SKY] = far
    return values.tobytes()


def integer_image(seed: int, sky: int) -> bytes:
    """RGBA16UI: covered pixels from `seed`, the sky's pixels from `sky` (Iris's float clear
    leaves an integer target undefined there: D75)."""
    values = np.arange(WIDTH * HEIGHT * 4, dtype="<u2").reshape(-1, 4) + seed
    values[SKY] = sky
    return values.tobytes()


def unorm_image(sky: int) -> bytes:
    values = np.full((WIDTH * HEIGHT, 4), 200, dtype=np.uint8)
    values[SKY] = sky
    return values.tobytes()


FORMATS = {
    "integer": {
        "name": "R16G16B16A16_UINT",
        "type": "Regular",
        "compType": "UInt",
        "compCount": 4,
        "compByteWidth": 2,
    },
    "unorm": {
        "name": "R8G8B8A8_UNORM",
        "type": "Regular",
        "compType": "UNorm",
        "compCount": 4,
        "compByteWidth": 1,
    },
    "depth": {
        "name": "D32",
        "type": "Regular",
        "compType": "Depth",
        "compCount": 1,
        "compByteWidth": 4,
    },
}


def written(folder: Path, program: str, targets: list[tuple[str, str, str, bytes]]) -> dict:
    """A pass as the replay writes it, its targets' bytes under folder/targets/."""
    (folder / "targets").mkdir(parents=True, exist_ok=True)
    found = []
    for slot, texture, kind, data in targets:
        name = f"targets/{program}-{slot}.bin"
        (folder / name).write_bytes(data)
        found.append(
            {
                "slot": slot,
                "resource": f"ResourceId::{len(found)}",
                "texture": texture,
                "width": WIDTH,
                "height": HEIGHT,
                "mip": 0,
                "slice": 0,
                "format": FORMATS[kind],
                "bytes": len(data),
                "file": name,
            }
        )
    return {"program": program, "event": 1, "groups": ["Terrain solid"], "targets": found}


def gbuffer_pass(folder: Path, seed: int, sky: int, far: float = 0.0) -> dict:
    return written(
        folder,
        "sodium_terrain_solid",
        [
            ("color0", "colortex1 main", "integer", integer_image(seed, sky)),
            ("depth", "Texture 196", "depth", depth_image(far, 0.002 if far == 0.0 else 0.9)),
        ],
    )


def test_an_integer_target_is_compared_only_where_its_pass_depth_shows_geometry(
    tmp_path: Path,
) -> None:
    for far in (0.0, 1.0):  # 26.3's reversed depth, and forward depth
        base, cand = tmp_path / f"a{far}", tmp_path / f"b{far}"
        found = l4.compare_passes(
            (base, [gbuffer_pass(base, 0, sky=7, far=far)]),
            (cand, [gbuffer_pass(cand, 0, sky=9, far=far)]),
        )
        (row,) = found
        assert row["tier"] == l4.IDENTICAL, row
        colour = row["targets"][0]
        assert (colour["differing"], colour["used"], colour["pixels"]) == (0, 6, 8)
        assert row["targets"][1]["used"] == 8  # the depth itself: every pixel
        assert l4.closure(l4.OUTPUTS, row)["verdict"] == l4.IDENTICAL
    moved = l4.compare_passes(
        (base, [gbuffer_pass(base, 0, sky=7)]), (cand, [gbuffer_pass(cand, 1, sky=7)])
    )
    assert moved[0]["tier"] == l4.DIFFERS
    assert (moved[0]["targets"][0]["differing"], moved[0]["targets"][0]["used"]) == (6, 6)
    with pytest.raises(l4.L4Error, match="sodium_terrain_solid differs: only identical closes"):
        l4.closure(l4.OUTPUTS, moved[0])


def test_a_float_target_counts_every_pixel_and_unknowns_stay_undecided(tmp_path: Path) -> None:
    base, cand = tmp_path / "a", tmp_path / "b"
    sky_moved = l4.compare_passes(
        (base, [written(base, "final", [("color0", "Texture 195", "unorm", unorm_image(0))])]),
        (cand, [written(cand, "final", [("color0", "Texture 195", "unorm", unorm_image(5))])]),
    )
    assert sky_moved[0]["tier"] == l4.DIFFERS
    assert (sky_moved[0]["targets"][0]["differing"], sky_moved[0]["targets"][0]["used"]) == (2, 8)
    # An integer target whose pass binds no depth: its used pixels are unknown.
    alone = [("color0", "colortex1 main", "integer", integer_image(0, 7))]
    undecided = l4.compare_passes(
        (base, [written(base, "deferred1", alone)]), (cand, [written(cand, "deferred1", alone)])
    )
    assert undecided[0]["tier"] == l4.UNDECIDED
    assert "binds no depth" in undecided[0]["why"]
    both = np.zeros(WIDTH * HEIGHT, dtype="<f4")
    both[-1] = 1.0
    with pytest.raises(l4.L4Error, match="holds both 0 and 1"):
        l4.covered(both)
    assert l4.covered(np.full(4, 0.5, dtype="<f4")).all()
    empty = {"program": "final", "event": 9, "groups": [], "targets": []}
    nothing = l4.compare_passes((base, [empty]), (cand, [empty]))
    assert (nothing[0]["tier"], nothing[0]["why"]) == (l4.UNDECIDED, "no target read back")
    only = l4.compare_passes((base, [gbuffer_pass(base, 0, 7)]), (cand, []))
    assert only == [
        {"program": "sodium_terrain_solid", "tier": "only in the baseline", "targets": []}
    ]
    with pytest.raises(l4.L4Error, match="format R32G32_UINT"):
        l4.depth_values(b"\0" * 64, {**FORMATS["integer"], "name": "R32G32_UINT"}, 4, 2)


def test_a_replay_ab_predicts_and_never_closes() -> None:
    found = l4.ab_summary(REPLAYED["ab"][0])
    assert found["power"] == "predict"
    assert found["medians"]["noop"]["share"] == pytest.approx(0.125)
    assert found["medians"]["candidate"]["share"] == pytest.approx(0.10)
    assert found["predicted"] == pytest.approx(-0.025)
    assert found["noise"] == pytest.approx(-0.001)
    assert l4.ab_summary(REPLAYED["ab"][1])["notDrawn"] is True
    with pytest.raises(
        l4.L4Error, match=r"a replay A/B only predicts \(.*\), so it closes nothing"
    ):
        l4.closure(l4.REPLAY_AB, {**found, "tier": l4.IDENTICAL})
    attribution = l4.attribution(l4.parse_events(REPLAYED, "fixture"))
    with pytest.raises(l4.L4Error, match=r"an? attribution only explains"):
        l4.closure(l4.ATTRIBUTION, attribution)


def test_pass_outputs_pair_each_capture_with_the_first_of_its_pack_family() -> None:
    variants = {
        "hello": {"id": "hello", "pack": "optilux-a.zip", "build": {"ref": "HEAD"}},
        "unbound": {"id": "unbound", "pack": "Unbound.zip", "build": None},
        "noshadow": {"id": "noshadow", "pack": "Unbound.zip", "build": None},
        "again": {"id": "again", "pack": "optilux-a.zip", "build": {"ref": "HEAD"}},
    }
    captures = [{"view": "underwater", "variant": v} for v in variants]
    captures.append({"view": "cave", "variant": "hello"})
    assert l4.pairs(captures, variants) == [
        ("underwater", "unbound", "noshadow"),
        ("underwater", "hello", "again"),
    ]


def test_the_replay_script_keeps_to_python_3_8() -> None:
    source = Path(l4replay.__file__).read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 8))
    for later in (".removeprefix(", ".removesuffix(", "strict=", "match ", " | None"):
        assert later not in source, later


# `check L4` through a stand-in for qrenderdoc.


PERF = ("underwater", "cave")  # the fixture views file's perf views


def capture_root(tmp_path: Path, views: tuple[str, ...] = ("underwater",)) -> Path:
    """A capture record of three captures per view (two hello builds and Unbound), each .rdc a few
    bytes hashed into the record, and an invalid fourth; its views file lists PERF."""
    root = tmp_path / "repo"
    raw = root / "results" / "raw" / "m4-capture-test"
    captures: list[dict] = []
    for view in views:
        for vid in ("hello", "unbound", "again"):
            data = f"RDOC {view} {vid}".encode()
            path = f"rdc/{view}/{vid}/java_frame{len(captures)}.rdc"
            (raw / path).parent.mkdir(parents=True)
            (raw / path).write_bytes(data)
            rdc = {
                "path": path,
                "name": Path(path).name,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            captures.append({"view": view, "variant": vid, "rdc": rdc, "valid": True})
    captures.append({"view": views[0], "variant": "late", "valid": False})
    (root / record.VIEWS).mkdir(parents=True)
    listed = {"id": "bench_test", "views": [{"id": v} for v in PERF]}
    (root / record.VIEWS / "bench_test.json").write_text(json.dumps(listed), "utf-8")
    found = {
        "name": "m4-capture-test",
        "kind": record.CAPTURE,
        "spec": {"views": "bench_test"},
        "status": "ok",
        "raw": "results/raw/m4-capture-test",
        "variants": [
            {"id": "hello", "pack": "optilux-a.zip", "build": {"ref": "HEAD"}},
            {"id": "unbound", "pack": "Unbound.zip", "build": None},
            {"id": "again", "pack": "optilux-a.zip", "build": {"ref": "HEAD"}},
        ],
        "captures": captures,
    }
    (root / record.RECORDS).mkdir(parents=True)
    (root / record.RECORDS / "m4-capture-test.json").write_text(json.dumps(found), "utf-8")
    return root


def stand_in_replay(monkeypatch: pytest.MonkeyPatch, moved: tuple[str, str] | None = None):
    """qrenderdoc's stand-in: the fixture's events, and for a capture whose outputs are asked a
    G-buffer pass; its covered pixels moved at the capture `moved` (view, variant)."""
    jobs: list[tuple[str, str, dict]] = []

    def replay(exe: Path, rdc: Path, out: Path, job: dict, version: str) -> dict:
        view, vid = rdc.parent.parent.name, rdc.parent.name
        jobs.append((view, vid, job))
        found = {k: v for k, v in REPLAYED.items() if k != "ab"}
        if job.get("outputs"):
            found["outputs"] = [gbuffer_pass(out, int((view, vid) == moved), sky=len(jobs))]
        return found

    monkeypatch.setattr(check, "renderdoc_pin", lambda root_: PIN)
    monkeypatch.setattr(l4, "qrenderdoc", lambda root_, pin: Path("qrenderdoc.exe"))
    monkeypatch.setattr(l4, "replay", replay)
    return jobs


def test_check_l4_prints_each_captures_shares_and_closes_nothing_short_of_the_perf_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = capture_root(tmp_path)
    jobs = stand_in_replay(monkeypatch)
    found = check.run_l4(root, "m4-capture-test", [], [], keep=False)
    assert [(vid, job["outputs"]) for _, vid, job in jobs] == [
        ("hello", True),
        ("unbound", False),  # alone in its pack family at the view
        ("again", True),
    ]
    assert found["skipped"] == ["underwater/late"]
    (comp,) = found["comparisons"]
    assert (comp["baseline"], comp["candidate"]) == ("hello", "again")
    assert [p["tier"] for p in comp["passes"]] == [l4.IDENTICAL]
    # Identical at one view of two perf views: the tier there, no closure (decision powers).
    assert found["closures"] == []
    assert found["heldBack"] == [
        "again against hello: compared at 1 views, not at 1 of the 2 perf views"
    ]
    folder = root / found["captures"][0]["folder"]
    assert not (folder / "targets").exists()  # read back, then removed
    assert (root / "results/raw/m4-capture-test/l4/l4.json").is_file()
    check.print_l4(found)
    said = capsys.readouterr().out
    assert "ungrouped: 17.00 % ((blits) 5.00 %, (copies) 5.00 %" in said
    assert "cutout draws: 3, 35.00 % of the frame, in Terrain solid 20.00 %" in said
    assert "their part of the ungrouped share: 29.41 %" in said
    assert "pass outputs at underwater, again against hello: 1 of 1 passes identical" in said
    assert "no closure: again against hello: compared at 1 views" in said
    (root / "results/raw/m4-capture-test/rdc/underwater/unbound/java_frame1.rdc").write_bytes(b"x")
    with pytest.raises(l4.L4Error, match="is not the record's capture"):
        check.run_l4(root, "m4-capture-test", [], [], keep=False)
    with pytest.raises(l4.L4Error, match="--capture cave/hello: no valid capture"):
        check.run_l4(root, "m4-capture-test", [], ["cave/hello"], keep=False)
    with pytest.raises(l4.L4Error, match=r"PROGRAM\.STAGE=FILE"):
        check.ab_items(["final.geom=x"])
    candidate = tmp_path / "final.fsh"
    candidate.write_text("void main() {}\n", "utf-8")
    with pytest.raises(l4.L4Error, match="--ab replays one capture"):
        check.run_l4(root, "m4-capture-test", [f"final.frag={candidate}"], [], keep=False)


def test_check_l4_closes_a_pass_identical_at_every_perf_view_of_an_ok_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = capture_root(tmp_path, PERF)
    stand_in_replay(monkeypatch)
    found = check.run_l4(root, "m4-capture-test", [], [], keep=False)
    assert [(c["view"], c["candidate"]) for c in found["comparisons"]] == [
        ("underwater", "again"),
        ("cave", "again"),
    ]
    (closed,) = found["closures"]
    assert closed == {
        "method": l4.OUTPUTS,
        "power": "close",
        "verdict": l4.IDENTICAL,
        "pass": "sodium_terrain_solid",
        "baseline": "hello",
        "candidate": "again",
        "views": 2,
    }
    check.print_l4(found)
    assert "CLOSED (pass outputs): sodium_terrain_solid's visual tier identical" in (
        capsys.readouterr().out
    )
    stand_in_replay(monkeypatch, moved=("cave", "again"))  # differs at one perf view
    assert check.run_l4(root, "m4-capture-test", [], [], keep=False)["closures"] == []
    path = root / record.RECORDS / "m4-capture-test.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "status": "failed"}), "utf-8")
    stand_in_replay(monkeypatch)
    found = check.run_l4(root, "m4-capture-test", [], [], keep=False)
    assert (found["closures"], found["heldBack"]) == (
        [],
        ["again against hello: the record ended failed"],
    )


def test_check_l4_refuses_a_record_of_another_kind(tmp_path: Path) -> None:
    root = capture_root(tmp_path)
    path = root / record.RECORDS / "m4-capture-test.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "kind": "visual"}), "utf-8")
    with pytest.raises(l4.L4Error, match="is no capture record"):
        check.capture_record(root, "m4-capture-test")


# The pinned qrenderdoc on M4.P04's smallest capture (the End, the hello pack), where both exist.


def smallest() -> tuple[Path, str] | None:
    path = REPO_ROOT / record.RECORDS / f"{SMALLEST}.json"
    if not path.is_file():
        return None
    found = json.loads(path.read_text(encoding="utf-8"))
    capture = next(c for c in found["captures"] if c["view"] == "end_dragon")
    return REPO_ROOT / found["raw"] / capture["rdc"]["path"], capture["rdc"]["sha256"]


SMALL = smallest()
QRENDERDOC = REPO_ROOT / "runtime" / "tools" / PIN["unpack"] / Path(PIN["exe"]).parent
needs_capture = pytest.mark.skipif(
    SMALL is None or not SMALL[0].is_file() or not (QRENDERDOC / "qrenderdoc.exe").is_file(),
    reason="no qrenderdoc under runtime/tools/ or no M4.P04 capture under results/raw/",
)


@needs_capture
def test_the_pinned_qrenderdoc_replays_the_ends_hello_capture(tmp_path: Path) -> None:
    assert SMALL is not None
    rdc, sha256 = SMALL
    l4.held(rdc, sha256)
    exe = l4.qrenderdoc(REPO_ROOT, PIN)
    found = l4.replay(exe, rdc, tmp_path, {"outputs": True}, PIN["version"])
    assert found["api"] == "OpenGL" and found["spotChecked"] > 0
    shares = l4.attribution(l4.parse_events(found, rdc.name))
    assert shares["draws"] == 279
    assert [r["name"] for r in shares["cutout"]["groups"]] == ["Terrain solid"]
    terrain = next(p for p in found["outputs"] if p["program"] == "sodium_terrain_solid")
    meta, data = l4.pass_depth(tmp_path, terrain) or (None, b"")
    assert meta is not None and meta["format"]["name"] == "D32"
    depth = l4.depth_values(data, meta["format"], meta["width"], meta["height"])
    assert 0 < l4.covered(depth).sum() < depth.size  # reversed: the sky at 0
