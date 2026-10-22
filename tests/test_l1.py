"""L1 (optilux/l1.py, plans/m3.md D69): dump equality and took-effect, the premise check on fixture
dumps, the impact matrix and the audit on the hello pack, a record's closures re-judged by
`verify records`."""

import json
from pathlib import Path

import pytest

from optilux import REPO_ROOT, l1, offline, record
from optilux.verbs import check, verify

PIPELINE = json.loads((REPO_ROOT / "config" / "pipeline.json").read_text(encoding="utf-8"))
PASSES = PIPELINE["passes"]
DIMS = record.DIMENSIONS
HELLO = offline.from_folder("shader/", REPO_ROOT / "shader")
GBUFFERS = [p["name"] for p in PASSES if p["stage"] == "gbuffers"]


# The GLSL reader.

STAGE = """#version 330 core
// a comment with a brace {
uniform float far;
struct Light { vec3 color; };
float ramp(float d) { if (d < far) { return 0.0; } return 1.0; }
float unused(float d) { return ramp(d) * 2.0; }
vec3 lit(vec3 c) {
#ifdef BENCH
    return c * ramp(1.0);
#else
    return c;
#endif
}
void main() { vec3 x = lit(vec3(1.0)); }
"""


def test_the_reader_finds_each_function_and_what_main_reaches() -> None:
    unit = l1.glsl_unit(STAGE)
    assert unit.balanced and sorted(unit.functions) == ["lit", "main", "ramp", "unused"]
    # A constructor reads as a call; no function of its name is defined, so none is reached.
    assert unit.calls["main"] == {"lit", "vec3"} and unit.calls["lit"] == {"ramp"}
    assert l1.reachable(unit) == {"main", "lit", "ramp"}  # unused is kept, never reached
    assert l1.reachable(l1.glsl_unit("float f() { return 1.0; }")) == set()  # no main
    assert not l1.glsl_unit("void main() { if (true) { }").balanced


# Dump equality.


def files(**overrides: str) -> dict[str, str]:
    found = {
        "patched_shaders/001_final.fsh": "a" * 64,
        "patched_shaders/001_final.vsh": "b" * 64,
        "patched_shaders/002_basic.fsh": "c" * 64,
        "patched_shaders/entity.properties": "d" * 64,
        "preprocessed.properties": "e" * 64,
    }
    found.update(overrides)
    return {k: v for k, v in found.items() if v}


def test_prints_compare_stage_by_stage_without_iris_counter() -> None:
    same = l1.compare_prints(files(), files())
    assert same == {
        "equal": True,
        "changed": [],
        "baselineOnly": [],
        "candidateOnly": [],
        "renumbered": False,
    }
    moved = l1.compare_prints(files(), files(**{"patched_shaders/002_basic.fsh": "f" * 64}))
    assert not moved["equal"] and moved["changed"] == ["patched_shaders/basic.fsh"]
    renumbered = {k.replace("002_", "003_"): v for k, v in files().items()}
    found = l1.compare_prints(files(), renumbered)
    assert not found["equal"] and found["renumbered"] and found["changed"] == []
    fewer = l1.compare_prints(files(), files(**{"patched_shaders/entity.properties": ""}))
    assert fewer["baselineOnly"] == ["patched_shaders/entity.properties"]
    with pytest.raises(l1.L1Error, match=r"two files of the print are patched_shaders/final.fsh"):
        l1.keyed({"patched_shaders/001_final.fsh": "a", "patched_shaders/002_final.fsh": "b"})


def dump_record(prints: dict[tuple[str, str], dict[str, str]], ids: list[str]) -> dict:
    """A dump record's fields L1 reads, from (variant, dimension) -> files."""
    captures, dumps = [], {}
    for n, ((vid, dim), found) in enumerate(prints.items(), start=1):
        manifest = record.dump_manifest(found)
        dumps[manifest] = found
        dump = {"folder": f"dumps/{n}", "files": len(found), "manifest": manifest, "dated": {}}
        captures.append(
            {"index": n, "view": "v", "dimension": dim, "variant": vid, "dump": dump, "valid": True}
        )
    variants = [{"id": vid} for vid in ids]
    return {"status": "ok", "variants": variants, "captures": captures, "dumps": dumps}


def test_a_candidate_equal_everywhere_did_not_take_effect_and_one_equal_somewhere_is_skipped() -> (
    None
):
    moved = files(**{"patched_shaders/002_basic.fsh": "f" * 64})
    prints = {}
    for dim in DIMS:
        prints[("base", dim)] = files()
        prints[("same", dim)] = files()
        prints[("nether-only", dim)] = files() if dim == DIMS[1] else moved
    found = dump_record(prints, ["base", "same", "nether-only"])
    base, judged = l1.equality(found)
    same, partly = judged
    assert base == "base" and not same["tookEffect"] and partly["tookEffect"]
    (closed,) = same["closures"]
    assert (closed["method"], closed["verdict"], closed["dimensions"]) == (
        l1.DUMP_EQUALITY,
        "no effect",
        list(DIMS),
    )
    assert closed["evidence"][DIMS[0]]["baseline"] == closed["evidence"][DIMS[0]]["candidate"]
    (skip,) = partly["closures"]
    assert (skip["verdict"], skip["dimensions"]) == ("skip", [DIMS[1]])
    assert partly["dimensions"][DIMS[0]]["changed"] == ["patched_shaders/basic.fsh"]
    # A dimension the candidate was not dumped in: it never closes as having no effect.
    del prints[("same", DIMS[2])]
    _, (short, _) = l1.equality(dump_record(prints, ["base", "same", "nether-only"]))
    assert short["undumped"] == [DIMS[2]] and short["closures"][0]["verdict"] == "skip"


def offline_of(found: dict, judged: list[dict]) -> dict:
    """The offline field run_l1 writes from l1.equality's judgment, for verify records."""
    return {
        "level": "L1",
        "baseline": found["variants"][0]["id"],
        "closures": [{"variant": e["variant"], **c} for e in judged for c in e["closures"]],
        "candidates": [
            {"variant": e["variant"], "undumped": e["undumped"], "unprinted": [], "options": []}
            for e in judged
        ],
    }


def test_verify_records_rejudges_each_candidates_closures_from_the_record() -> None:
    prints = {(vid, dim): files() for dim in DIMS for vid in ("base", "same")}
    found = dump_record(prints, ["base", "same"])
    _, judged = l1.equality(found)
    found["offline"] = offline_of(found, judged)
    assert verify.dump_problems(found) == []
    wrong = "offline: same's dump-equality closures are not its manifests'"
    forged = json.loads(json.dumps(found))
    forged["offline"]["closures"][0]["evidence"][DIMS[0]]["candidate"] = "0" * 64
    narrow = json.loads(json.dumps(found))
    narrow["offline"]["closures"][0]["dimensions"] = [DIMS[0]]
    missing = {**found, "offline": {**found["offline"], "closures": []}}
    for broken in (forged, narrow, missing):
        assert verify.dump_problems(broken) == [wrong]
    # A changed file no print shows: no dump-equality closure may stand.
    unprinted = json.loads(json.dumps(found))
    unprinted["offline"]["candidates"][0]["unprinted"] = ["textures/noise.png"]
    assert verify.dump_problems(unprinted) == [wrong]
    unprinted["offline"]["closures"] = []
    assert verify.dump_problems(unprinted) == []
    selfish = json.loads(json.dumps(found))
    selfish["offline"]["closures"][0]["variant"] = "base"
    assert "without its method or candidate" in verify.dump_problems(selfish)[0]
    premised = json.loads(json.dumps(found))
    closure = {"variant": "same", "method": l1.PREMISE, "power": "close", "verdict": "not compiled"}
    premised["offline"]["closures"].append(closure)
    assert verify.dump_problems(premised) == []
    premised["offline"]["candidates"][0]["options"] = ["BENCH"]
    assert verify.dump_problems(premised) == [
        "offline: same's premise closure despite its options or dumps"
    ]
    del found["offline"]
    assert verify.dump_problems(found) == [
        "an ok dump record without `offline`, check L1's closures"
    ]


def test_a_record_of_one_variant_has_no_candidate_to_judge() -> None:
    found = dump_record({("base", dim): files() for dim in DIMS}, ["base"])
    assert l1.equality(found) == ("base", [])


# The premise check.


def pack(**changed: str) -> offline.Pack:
    base = {
        "final.fsh": "#version 330 core\nvoid main() { }\n",
        "lib/fog.glsl": STAGE.split("\n", 1)[1],
        "shaders.properties": "screen = BENCH\n",
    }
    base.update(changed)
    return offline.Pack("fixture", {k: v for k, v in base.items() if v})


def stage(text: str) -> dict[str, dict[str, l1.Unit]]:
    """The same dumped stage in every dimension."""
    return {dim: {"patched_shaders/basic.fsh": l1.glsl_unit(text)} for dim in DIMS}


DUMPED = stage(STAGE)


def edited(old: str, new: str) -> str:
    assert old in STAGE
    return STAGE.split("\n", 1)[1].replace(old, new)


def judge(
    cand: offline.Pack,
    base: offline.Pack | None = None,
    cand_units: dict | None = None,
    base_units: dict | None = None,
) -> dict:
    """The premise check of `cand` against `base` (pack()), its changed files by their bytes."""
    base = base or pack()

    def raw(found: offline.Pack) -> dict[str, bytes]:
        return {k: v.encode("utf-8") for k, v in found.files.items()}

    paths = l1.changed_files(raw(base), raw(cand))
    units = (cand_units or DUMPED, base_units or DUMPED)
    return l1.premise(base, cand, paths, *units)


def test_the_premise_holds_for_a_changed_function_main_reaches() -> None:
    found = judge(
        pack(**{"lib/fog.glsl": edited("return c * ramp(1.0);", "return c * ramp(2.0);")})
    )
    assert found["verdict"] == "holds" and found["undecided"] == []
    (entry,) = found["files"]
    (fn,) = entry["functions"]
    assert (fn["name"], fn["defined"], fn["reached"]) == ("lit", 3, 3)
    # A directive moved inside a function changes that function, in place.
    flipped = judge(pack(**{"lib/fog.glsl": edited("#ifdef BENCH", "#ifndef BENCH")}))
    assert flipped["verdict"] == "holds"
    assert [fn["name"] for fn in flipped["files"][0]["functions"]] == ["lit"]


def test_the_premise_fails_for_a_function_no_dump_compiles_or_main_never_reaches() -> None:
    cand = pack(**{"lib/fog.glsl": edited("return ramp(d) * 2.0;", "return ramp(d) * 3.0;")})
    assert judge(cand)["verdict"] == "not executed"
    gone = stage(STAGE.replace("float unused(float d) { return ramp(d) * 2.0; }\n", ""))
    assert judge(cand, cand_units=gone, base_units=gone)["verdict"] == "not compiled"
    removed = pack(
        **{"lib/fog.glsl": edited("float unused(float d) { return ramp(d) * 2.0; }", "")}
    )
    assert judge(removed, cand_units=gone)["verdict"] == "not executed"  # in the baseline's


MACRO = "#define SUM(n) \\\n    for (int i = 0; i < n; i++) { acc += w(i); }\n"
PREMISE_UNDECIDED = [
    ({"lib/fog.glsl": edited("// a comment", "// another")}, "a comment changed"),
    (
        {"lib/fog.glsl": edited("uniform float far;", "uniform float near;")},
        "outside its functions'",
    ),
    ({"lib/fog.glsl": edited("return 1.0; }", "return 1.0;  }")}, "only its whitespace changed"),
    ({"lib/fog.glsl": edited("void main() {", "void main() { {")}, "does not parse"),
    ({"shaders.properties": "screen = OTHER\n"}, "is no GLSL"),
    (
        {
            "lib/fog.glsl": edited("return ramp(d) * 2.0;", "return ramp(d);"),
            "x.glsl": "#define unused u2\n",
        },
        "unused is also a #define's name",
    ),
]


@pytest.mark.parametrize(("changed", "says"), PREMISE_UNDECIDED)
def test_the_premise_check_leaves_what_it_cannot_judge_undecided(changed: dict, says: str) -> None:
    found = judge(pack(**changed))
    assert found["verdict"] == "undecided" and any(says in why for why in found["undecided"])


def test_a_continued_defines_body_stays_in_its_directive() -> None:
    """A #define's body over continued lines is the directive's, never a function `for` that no
    print defines (which would read as not compiled)."""
    unit = l1.glsl_unit(MACRO + "float w(int i) { return 1.0; }\n")
    assert sorted(unit.functions) == ["w"] and unit.outside[0].startswith("#define SUM(n)")
    base = pack(**{"x.glsl": MACRO})
    cand = pack(**{"x.glsl": MACRO.replace("w(i)", "2.0 * w(i)")})
    found = judge(cand, base)
    assert found["verdict"] == "undecided" and "outside its functions'" in found["undecided"][0]


def test_a_dimension_whose_print_holds_no_stage_leaves_the_premise_undecided() -> None:
    cand = pack(**{"lib/fog.glsl": edited("return ramp(d) * 2.0;", "return ramp(d) * 3.0;")})
    empty = {**DUMPED, DIMS[2]: {}}
    found = judge(cand, cand_units=empty)
    assert found["verdict"] == "undecided" and "holds no stage" in found["undecided"][0]


def test_no_source_change_leaves_the_premise_to_the_options() -> None:
    assert judge(pack()) == {"verdict": "no source change", "files": [], "undecided": []}
    assert l1.changed_files({"a.png": b"\x89\xff"}, {"a.png": b"\x89\xfe"}) == ["a.png"]
    assert l1.printed("lib/fog.glsl") and l1.printed("entity.properties")
    assert not l1.printed("textures/noise.png") and not l1.printed("dimension.properties")


def test_dead_only_accepts_a_print_that_differs_in_dead_functions_alone() -> None:
    base = {"patched_shaders/basic.fsh": l1.glsl_unit(STAGE)}
    dead = STAGE.replace("return ramp(d) * 2.0;", "return ramp(d) * 3.0;")
    row = {"changed": ["patched_shaders/basic.fsh"], "baselineOnly": [], "candidateOnly": []}
    cand = {"patched_shaders/basic.fsh": l1.glsl_unit(dead)}
    assert l1.dead_only(base, cand, row, {"unused"}) is None
    live = dead.replace("return c * ramp(1.0);", "return c * ramp(2.0);")
    reason = l1.dead_only(base, {"patched_shaders/basic.fsh": l1.glsl_unit(live)}, row, {"unused"})
    assert reason == "patched_shaders/basic.fsh: lit differs and is no dead changed function"
    assert l1.dead_only(base, cand, {**row, "candidateOnly": ["x.fsh"]}, {"unused"}) is not None
    json_row = {**row, "changed": ["patched_shaders/basic.json"]}
    assert l1.dead_only(base, cand, json_row, {"unused"}) == (
        "patched_shaders/basic.json is no stage, and differs"
    )


def test_a_premise_verdict_closes_only_what_the_source_alone_decides() -> None:
    """check.premise_held_back: an option change, a dimension not dumped, or a print that differs
    though no print defines a changed function each hold a closing verdict back."""
    row = {"changed": [], "baselineOnly": [], "candidateOnly": [], "equal": True}
    entry = {
        "premise": {"verdict": "not compiled", "files": []},
        "options": [],
        "undumped": [],
        "tookEffect": False,
        "dimensions": dict.fromkeys(DIMS, row),
    }
    assert check.premise_held_back(entry, {}, {}) is None
    assert "options differ" in check.premise_held_back({**entry, "options": ["BENCH"]}, {}, {})
    assert "not dumped in" in check.premise_held_back({**entry, "undumped": [DIMS[2]]}, {}, {})
    assert "prints differ" in check.premise_held_back({**entry, "tookEffect": True}, {}, {})


def test_a_dumped_stage_off_its_recorded_sha256_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "dumps" / "x" / "patched_shaders"
    folder.mkdir(parents=True)
    (folder / "001_basic.fsh").write_text(STAGE, encoding="utf-8")
    capture = {"dump": {"folder": "dumps/x"}}
    with pytest.raises(l1.L1Error, match="does not hash to its record's sha256"):
        l1.stage_units(tmp_path, capture, {"patched_shaders/001_basic.fsh": "0" * 64})


# The impact matrix and the audit on the hello pack.


def test_the_impact_matrix_follows_the_hello_packs_includes_to_its_passes_and_views() -> None:
    every = PASSES[0]["views"]
    fog, final, option = l1.impact(
        HELLO, ["lib/fog.glsl", "final.fsh"], ["BENCH_DETERMINISTIC"], PASSES
    )
    assert fog["change"] == "lib/fog.glsl" and fog["passes"] == GBUFFERS
    assert "gbuffers_basic.vsh" in fog["programs"] and "final.fsh" not in fog["programs"]
    assert fog["views"] == every and len(every) == 11
    assert (final["programs"], final["passes"]) == (["final.fsh"], ["present"])
    assert option["change"] == "option BENCH_DETERMINISTIC" and option["passes"] == GBUFFERS
    (light,) = l1.impact(HELLO, ["lib/light.glsl"], [], PASSES)
    # Iris expands includes as text before its preprocessor: surface_vertex.glsl's include of
    # light.glsl under #ifdef SURFACE_LIGHT reaches every gbuffers program; whether its code
    # compiles there is the premise check's to say.
    assert light["passes"] == GBUFFERS and "gbuffers_basic.vsh" in light["programs"]


def test_the_audit_pairs_each_buffer_with_its_producer_and_reader() -> None:
    properties = {
        (vid, dim): "screen = BENCH_DETERMINISTIC\n" for vid in ("a", "b") for dim in DIMS
    }
    assert l1.audit(PASSES, properties) == []
    off = "".join(
        f"program.{p['program']}.enabled = false\n" for p in PASSES if p["stage"] == "gbuffers"
    )
    stale = l1.audit(PASSES, {("a", DIMS[0]): off})
    (problem,) = stale
    assert problem == (
        "a in minecraft:overworld: present samples colortex0, which no enabled pass writes "
        "before it"
    )
    unread = l1.audit(PASSES, {("a", DIMS[0]): "program.final.enabled = false\n"})
    assert len(unread) == len(GBUFFERS) and unread[0].endswith(
        "which no enabled pass reads after it"
    )
    custom = [{**PASSES[-1], "inputs": {"samplers": ["colortex0"], "uniforms": ["wobble"]}}]
    uniforms = {("a", DIMS[0]): "uniform.float.wobble = 1.0\n", ("b", DIMS[0]): ""}
    passes = [*PASSES[:-1], *custom]
    assert l1.audit(passes, uniforms) == [
        "b in minecraft:overworld: present reads custom uniform wobble, undefined there"
    ]
