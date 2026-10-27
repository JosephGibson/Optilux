"""`optilux check L0 [<pack>] [--json]` (docs/offline.md#levels, plans/m3.md M3.P04): an Optilux
pack's variant matrix preprocessed, compiled and linked by glslang (optilux/offline.py), `verify
similarity` on its GLSL, and the profile check of every config/profiles/*.json against its pack's
declared options: Optilux's (optilux-<id>.json) against the pack checked, the reference pack's
against the studied copy under reference/, read once its tree hash matches its pin.

<pack> is a folder holding shaders/, a pack's .zip, or - for a zip on stdin, as `run` hands it an
Optilux variant's zip in a child process (plans/m3.md D63); by default the working tree's shader/,
as `pack build` zips it. Exit 0 when all three pass. CI has neither glslang nor the reference copy,
so it runs the tests, never this verb.
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from optilux import REPO_ROOT, expressions, l1, l2, l3, offline, packzip, platform, record
from optilux.verbs import Verb, verify
from optilux.verbs.install import REFERENCE, RUNTIME, STORE, TOOLS, TOOLS_DIR, shown

PREFIX = "optilux check L0"
PIPELINE = "config/pipeline.json"
PROFILES = "config/profiles"
# Optilux's own profiles: config/profiles/optilux-<id>.json, judged against the pack checked.
OPTILUX_PROFILE = "optilux-"
STDIN = "-"
BENCH = "bench"


def configure(parser: argparse.ArgumentParser) -> None:
    levels = parser.add_subparsers(dest="level", metavar="<level>", title="levels")
    levels.required = True
    l0 = levels.add_parser(
        "L0",
        help="glslang over the variant matrix, the similarity check, the profile check",
        description=(
            "Preprocess, compile and link every program of the pack in each dimension at its "
            "defaults and with each option switched alone, under Iris's macros; run verify "
            "similarity on its GLSL; check every config/profiles/*.json against its pack's "
            "options (docs/offline.md#levels)."
        ),
    )
    l0.add_argument(
        "pack",
        nargs="?",
        help="a folder holding shaders/, a pack's .zip, or - for a zip on stdin; default: shader/",
    )
    l0.add_argument("--json", action="store_true", help="print JSON instead of text")
    l1_parser = levels.add_parser(
        "L1",
        help="a dump run's prints: dump equality, the premise check, impact matrix, audit",
        description=(
            "Judge each candidate of a dump record against its baseline (docs/offline.md#levels, "
            "plans/m3.md D69): dump equality and took-effect per dimension, the premise check, the "
            "impact matrix and the pipeline audit; the closures as the record's `offline` holds "
            "them, held against the record's own."
        ),
    )
    l1_parser.add_argument(
        "record", metavar="run", help="a dump record's run name, or - for a record on stdin"
    )
    l1_parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    l2_parser = levels.add_parser(
        "L2",
        help="RGA (gfx1101) on a dump run's every program: registers, ISA, live registers, CFG",
        description=(
            "Build each distinct program of a dump record's prints with RGA in OpenGL mode for "
            "gfx1101 (docs/offline.md#levels, plans/m3.md D70), its outputs under "
            "results/raw/<run>/l2/; print each stage's VGPRs, or name it a known offline "
            "failure. Explains only: it never gates."
        ),
    )
    l2_parser.add_argument("record", metavar="run", help="a dump record's run name")
    l2_parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    l3_parser = levels.add_parser(
        "L3",
        help="function tests: the pack's includes run on the GPU against numpy goldens",
        description=(
            "Run each include under the pack's shaders/lib/ that has a test file under tests/l3/ "
            "on the GPU (moderngl, GL 3.3 core): its functions over each test's cases, held to "
            "numpy goldens within the test's tolerance; evaluate each custom uniform of "
            "shaders.properties in Iris's own expression engine and hold it to the GLSL it "
            "replaces (tests/l3/uniforms.py) (docs/offline.md#levels)."
        ),
    )
    l3_parser.add_argument(
        "pack",
        nargs="?",
        help="a folder holding shaders/, a pack's .zip, or - for a zip on stdin; default: shader/",
    )
    l3_parser.add_argument("--json", action="store_true", help="print JSON instead of text")


def load_pack(root: Path, named: str | None) -> offline.Pack:
    """The pack L0 checks: the working tree's shader/ (with its zip's sha512), a zip read from
    stdin, a .zip file, or a folder holding shaders/."""
    if named is None:
        try:
            sources = packzip.tree_sources(root)
        except packzip.PackError as error:
            raise offline.L0Error(str(error)) from None
        digest = hashlib.sha512(packzip.zip_bytes(sources)).hexdigest()
        return offline.from_sources(f"{packzip.PACK_DIR}/", sources, digest)
    if named == STDIN:
        return offline.from_zip("the zip on stdin", sys.stdin.buffer.read())
    path = Path(named)
    if path.is_file():
        return offline.from_zip(named, path.read_bytes())
    if path.is_dir():
        return offline.from_folder(named, path)
    raise offline.L0Error(f"{named} is no folder or zip; fix: a pack folder, its .zip or -")


def glslang_exe(root: Path) -> tuple[Path, str]:
    """glslang as config/tools.json pins it under runtime/tools/, and the version it prints, held
    against the pin."""
    pins = json.loads((root / TOOLS).read_text(encoding="utf-8"))
    pin = pins.get("glslang")
    if not isinstance(pin, dict) or not pin.get("unpack") or not pin.get("exe"):
        raise offline.L0Error(f"{TOOLS} pins no glslang with unpack and exe; fix: restore it")
    exe = root / TOOLS_DIR / pin["unpack"] / pin["exe"]
    version = offline.glslang_version(exe)
    if version != pin["version"]:
        raise offline.L0Error(
            f"{TOOLS_DIR}/{pin['unpack']}/{pin['exe']} prints {version}, the pin says "
            f"{pin['version']}; fix: `uv run optilux install`"
        )
    return exe, version


def macros(root: Path) -> list[tuple[str, str | None]]:
    """Iris's macros on the bench tier (offline.iris_macros), refused when the pins under them
    moved: the bench tier's Iris is no longer the jar they were read in, it gains a mod that adds a
    define, or iris.properties allows unknown shaders."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    mods = [p for p in plat.tier_files(BENCH) if p.kind == "mod"]
    iris = next((p for p in mods if p.slug == "iris"), None)
    if iris is None or iris.sha512 != offline.IRIS_SHA512:
        pinned = iris.file if iris else "no Iris"
        raise offline.L0Error(
            f"the bench tier pins {pinned}, and L0's macros and option rules were read in "
            f"{offline.IRIS_JAR}; fix: read them again in the new jar with javap and update "
            "optilux/offline.py"
        )
    adding = [p.slug for p in mods if p.slug in offline.MACRO_MODS]
    display = suite["display"]
    if adding or display["irisProperties"].get("allowUnknownShaders") == "true":
        raise offline.L0Error(
            f"the bench tier's {', '.join(adding) or 'allowUnknownShaders'} adds an Iris define L0 "
            "leaves out; fix: model it in optilux/offline.py"
        )
    return offline.iris_macros(plat.minecraft, iris.version, display["optionsTxt"]["mipmapLevels"])


def studied_pack(root: Path) -> tuple[offline.Pack, str]:
    """The studied copy's GLSL as a pack, read once its tree hash matches its pin, and the name
    its profiles give it: the platform file's reference pack of its slug, whose slug and version
    its folder must spell (<slug>-<version>), so a moved reference pack never judges a profile by
    the old copy."""
    config = verify.similarity_config(root)
    pin = config["studied"]
    plat = platform.load(root)
    reference = next(
        (
            p
            for p in plat.data.get(platform.REFERENCE_PACKS, [])
            if p.get("slug") == pin.get("slug")
        ),
        None,
    )
    if reference is None or pin["folder"] != f"{reference['slug']}-{reference['version']}":
        named = f"{reference['slug']} {reference['version']}" if reference else "none"
        raise offline.L0Error(
            f"{REFERENCE}/{pin['folder']}/ is not the copy of {plat.path.name}'s reference pack "
            f"of slug {pin.get('slug')!r} ({named}); fix: pin that pack's copy in "
            "config/similarity.json, then `uv run optilux install`"
        )
    texts = verify.reference_texts(root, pin)
    home = f"{REFERENCE}/{pin['folder']}/"
    pack = offline.from_sources(
        home, [(name.removeprefix(home), data.encode("utf-8")) for name, data in texts.items()]
    )
    return pack, f"{reference['slug']} {reference['version']}"


def check_profiles(root: Path, pack: offline.Pack) -> list[dict]:
    """Every config/profiles/*.json against its pack's options (offline.check_profile): Optilux's
    against `pack`, the reference pack's (named by the studied copy's slug) against the copy."""
    studied: tuple[offline.Pack, str] | None = None
    slug = verify.similarity_config(root)["studied"].get("slug", "")
    found = []
    for path in sorted((root / PROFILES).glob("*.json")):
        shown = f"{PROFILES}/{path.name}"
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=str, parse_int=str)
        if path.name.startswith(OPTILUX_PROFILE):
            against, label, problems = pack, pack.label, []
        elif slug and path.name.startswith(f"{slug}-"):
            try:
                studied = studied or studied_pack(root)
            except (verify.SimilarityError, offline.L0Error) as error:
                found.append({"profile": shown, "pack": None, "keys": 0, "problems": [str(error)]})
                continue
            against, label = studied[0], studied[0].label
            problems = (
                []
                if data.get("pack") == studied[1]
                else [
                    f"{shown}: pack {data.get('pack')!r}, the copy is {studied[1]}; fix: its pack"
                ]
            )
        else:
            found.append(
                {
                    "profile": shown,
                    "pack": None,
                    "keys": 0,
                    "problems": [
                        f"{shown}: no pack of its name ({OPTILUX_PROFILE}<id> or {slug}-<id>); "
                        "fix: rename it"
                    ],
                }
            )
            continue
        keys, more = offline.check_profile(shown, data, offline.declared(against))
        found.append({"profile": shown, "pack": label, "keys": keys, "problems": problems + more})
    return found


def run_l0(root: Path, named: str | None) -> dict:
    """`check L0`'s whole result: the pack, the matrix with every failure, the similarity check,
    the profiles, and whether all passed."""
    started = time.perf_counter()
    pack = load_pack(root, named)
    exe, version = glslang_exe(root)
    spec = (root / PIPELINE).read_bytes()
    passes = json.loads(spec.decode("utf-8"))["passes"]
    matrix = offline.build_matrix(pack, passes, macros(root), exe)
    texts = {f"{pack.label.rstrip('/')}/{offline.SHADERS}/{p}": t for p, t in pack.files.items()}
    try:
        similar = verify.check_similarity(root, texts)
        similarity = {
            "line": (
                f"{similar.files} GLSL files of {pack.label} ({similar.tokens} tokens) against "
                f"{similar.references} of {similar.reference} (k {similar.k}, t {similar.t}): "
                f"{len(similar.flagged)} matches of {similar.t} tokens or more"
            ),
            "flagged": [verify.flagged_text(m, similar.t) for m in similar.flagged],
        }
    except verify.SimilarityError as error:
        similarity = {"line": str(error), "flagged": [str(error)]}
    profiles = check_profiles(root, pack)
    failures = [failure_entry(c, matrix) for c in matrix.failed]
    problems = [
        *matrix.problems,
        *(f"{f['program']}: {f['stage']} ({f['step']}): {f['lines'][0]}" for f in failures),
        *similarity["flagged"],
        *(problem for p in profiles for problem in p["problems"]),
    ]
    return {
        "ok": not problems,
        "pack": pack.label,
        "files": len(pack.files),
        "sha512": pack.sha512,
        "glslang": version,
        "pipeline": {"file": PIPELINE, "sha256": hashlib.sha256(spec).hexdigest()},
        "options": {
            name: {"kind": o.kind, "default": o.default, "values": list(o.values)}
            for name, o in matrix.options.found.items()
        },
        "macros": offline.define_flags(matrix.macros),
        "matrix": {
            "programs": len({b.program for b in matrix.builds}),
            "dimensions": len({b.dimension for b in matrix.builds}),
            "variants": [v.label for v in matrix.variants],
            "builds": len(matrix.builds),
            "compiled": len(matrix.compiled),
            "glslangRuns": matrix.runs,
            "seconds": round(matrix.seconds, 2),
            "problems": matrix.problems,
            "failures": failures,
        },
        "similarity": similarity,
        "profiles": profiles,
        "problems": problems,
        "seconds": round(time.perf_counter() - started, 2),
    }


def failure_entry(done: offline.Compiled, matrix: offline.Matrix) -> dict:
    """One failed stage of a distinct build: its program, stage file and stage, the step, the
    option values it was built at and the dimensions that take it, glslang's lines."""
    key = (done.folder, done.program, done.variant)
    taken = {b.dimension for b in matrix.builds if (b.folder, b.program, b.variant) == key}
    values = offline.settings(matrix.options, done.variant)
    failure = done.failures[0]
    ending = failure.stage.rsplit(".", 1)[-1]
    return {
        "program": done.program,
        "stage": failure.stage,
        "stageName": offline.STAGE_NAMES.get(ending, "link"),
        "step": failure.step,
        "variant": done.variant.label,
        "options": values,
        "dimensions": [d for d in offline.WORLD_FOLDERS if d in taken],
        "lines": [line for f in done.failures for line in f.lines],
        "failures": [{"step": f.step, "stage": f.stage, "lines": f.lines} for f in done.failures],
    }


def print_text(found: dict) -> None:
    matrix = found["matrix"]
    digest = f", zip sha512 {found['sha512'][:12]}..." if found["sha512"] else ""
    print(f"{PREFIX}: {found['pack']}: {found['files']} files{digest}; glslang {found['glslang']}")
    for name, option in found["options"].items():
        values = "on/off" if option["kind"] == "bool" else " ".join(option["values"])
        print(f"option: {name} ({values}; default {option['default']})")
    print(f"macros: Iris 1.11.7's {len(found['macros'])} defines: {' '.join(found['macros'])}")
    variants = matrix["variants"]
    shared = (
        f"; {matrix['compiled']} compiled, as the dimensions share their programs' folder"
        if matrix["compiled"] < matrix["builds"]
        else ""
    )
    print(
        f"matrix: {matrix['programs']} programs x {matrix['dimensions']} dimensions x "
        f"{len(variants)} variants ({', '.join(variants)}) = {matrix['builds']} builds{shared}; "
        f"{matrix['glslangRuns']} glslang runs in {matrix['seconds']} s"
    )
    for problem in matrix["problems"]:
        print(f"FAIL {problem}")
    for entry in matrix["failures"]:
        values = ", ".join(f"{n} {v}" for n, v in entry["options"].items()) or "no options"
        for failure in entry["failures"]:
            ending = failure["stage"].rsplit(".", 1)[-1]
            stage = offline.STAGE_NAMES.get(ending)
            named = f"its {stage} stage {failure['stage']}" if stage else failure["stage"]
            print(
                f"FAIL {entry['program']}, {named} ({failure['step']}), at {values}, in "
                f"{', '.join(entry['dimensions'])}, under the {len(found['macros'])} macros above:"
            )
            for line in failure["lines"]:
                print(f"  {line}")
    print(f"similarity: {found['similarity']['line']}")
    for flagged in found["similarity"]["flagged"]:
        print(f"FAIL {flagged}")
    for entry in found["profiles"]:
        state = "ok" if not entry["problems"] else f"{len(entry['problems'])} problems"
        print(
            f"profile: {entry['profile']}: {entry['keys']} names against {entry['pack']}: {state}"
        )
        for problem in entry["problems"]:
            print(f"FAIL {problem}")
    verdict = "pass" if found["ok"] else f"FAIL ({len(found['problems'])} problems)"
    print(f"{PREFIX}: {verdict} in {found['seconds']} s")


# L1 (docs/offline.md#levels, plans/m3.md D69): optilux/l1.py on a dump record.

L1_PREFIX = "optilux check L1"


def dump_record(root: Path, named: str) -> dict:
    """The dump record L1 judges: results/records/<run>.json, or - for one on stdin (the run's
    own, before it is written)."""
    if named == STDIN:
        found = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    else:
        try:
            found = record.read_record(root, named)
        except record.RecordError as error:
            raise l1.L1Error(str(error)) from None
    if not isinstance(found, dict) or found.get("kind") != record.DUMP:
        raise l1.L1Error(f"{named} is no dump record; fix: a run of kind dump (plans/m3.md D60)")
    return found


def variant_pack(root: Path, found: dict, variant: dict) -> tuple[offline.Pack, dict[str, bytes]]:
    """A variant's source as its dump loaded it: an Optilux zip kept under raw/<run>/packs/, or the
    reference pack's pinned zip in the store; each held to the variant's sha512. The pack as
    text, and its files under shaders/ as bytes (changes are judged on bytes)."""
    packs = found.get("packs") or {}
    if variant["pack"] in packs:
        path = root / found["raw"] / packs[variant["pack"]]
        fix = "the run's raw folder as it wrote it"
    else:
        path = root / RUNTIME / platform.load(root).id / STORE / variant["pack"]
        fix = "`optilux install`"
    try:
        data = path.read_bytes()
    except OSError as error:
        raise l1.L1Error(f"{path}: {error}; fix: {fix}") from None
    if hashlib.sha512(data).hexdigest() != variant["sha512"]:
        raise l1.L1Error(f"{path} is not {variant['id']}'s zip (sha512); fix: rerun the dump")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {
            info.filename.removeprefix(f"{offline.SHADERS}/"): archive.read(info)
            for info in archive.infolist()
            if info.filename.startswith(f"{offline.SHADERS}/") and not info.is_dir()
        }
    return offline.from_zip(variant["pack"], data), files


def option_changes(base: dict, cand: dict) -> list[str]:
    """The options whose effective value the candidate's reload read back unlike the baseline's."""
    bv = (base.get("effective") or {}).get("values") or {}
    cv = (cand.get("effective") or {}).get("values") or {}
    return sorted(k for k in bv.keys() | cv.keys() if bv.get(k) != cv.get(k))


def iris_pinned(root: Path) -> None:
    """L1Error unless the bench tier's Iris is the jar l1.IRIS_UNIFORMS was read in."""
    plat = platform.load(root)
    iris = next((p for p in plat.tier_files(BENCH) if p.kind == "mod" and p.slug == "iris"), None)
    if iris is None or iris.sha512 != offline.IRIS_SHA512:
        raise l1.L1Error(
            f"the bench tier pins {iris.file if iris else 'no Iris'}, and L1's uniform list was "
            f"read in {offline.IRIS_JAR}; fix: read it again in the new jar with javap and update "
            "optilux/l1.py"
        )


def premise_held_back(entry: dict, base_units: dict, cand_units: dict) -> str | None:
    """Why a closing premise verdict (not compiled, not executed) closes nothing, or None: the
    check reads the source alone, so it closes only a candidate whose options equal the
    baseline's, dumped in every dimension; not compiled only where the prints are equal too (a
    print that differs holds something it did not see); not executed where every stage that
    differs differs only in dead changed functions (l1.dead_only)."""
    found = entry["premise"]
    if entry["options"]:
        return "its options differ from the baseline's too, which the premise check does not read"
    if entry["undumped"]:
        return f"it was not dumped in {', '.join(entry['undumped'])}"
    if found["verdict"] == "not compiled" and entry["tookEffect"]:
        return "its prints differ, though none defines a changed function"
    if found["verdict"] == "not executed" and entry["tookEffect"]:
        dead = {
            fn["name"]
            for f in found["files"]
            for kind in ("functions", "removed")
            for fn in f[kind]
        }
        for dim, row in entry["dimensions"].items():
            if row is not None and not row["equal"]:
                why = l1.dead_only(base_units[dim], cand_units[dim], row, dead)
                if why is not None:
                    return f"{dim}: {why}"
    return None


def run_l1(root: Path, named: str) -> dict:
    """`check L1`'s whole result over an ok dump record: per candidate its dump equality (no
    closure when it changes a file no print shows), premise check (closing only as
    premise_held_back allows) and impact matrix, the audit over the Optilux variants' dumps, the
    closures (the record's `offline` field) and whether the record's own agree."""
    started = time.perf_counter()
    found = dump_record(root, named)
    if found.get("status") != "ok":
        raise l1.L1Error(
            f"{named} ended {found.get('status')}; L1 closes only over an ok dump record's whole "
            "set of prints; fix: a dump run that ended ok"
        )
    invalid = [str(c["index"]) for c in found.get("captures") or [] if not c.get("valid")]
    if invalid:
        raise l1.L1Error(f"dumps {', '.join(invalid)} are not whole; fix: rerun the dump")
    raw = root / found["raw"]
    spec = (root / PIPELINE).read_bytes()
    passes = json.loads(spec.decode("utf-8"))["passes"]
    base, judged = l1.equality(found)
    variants = {v["id"]: v for v in found["variants"]}
    taken = l1.prints(found)
    sources = {vid: variant_pack(root, found, v) for vid, v in variants.items()}
    parsed: dict[str, dict[str, dict]] = {}

    def units(vid: str) -> dict[str, dict]:
        if vid not in parsed:
            parsed[vid] = {
                d: l1.stage_units(raw, taken[(vid, d)]["capture"], taken[(vid, d)]["files"])
                for d in record.DIMENSIONS
                if (vid, d) in taken
            }
        return parsed[vid]

    for entry in judged:
        vid = entry["variant"]
        changed = l1.changed_files(sources[base][1], sources[vid][1])
        entry["unprinted"] = [path for path in changed if not l1.printed(path)]
        if entry["unprinted"]:  # no print shows it: dump equality cannot speak for it
            entry["closures"] = [c for c in entry["closures"] if c["method"] != l1.DUMP_EQUALITY]
        entry["options"] = option_changes(variants[base], variants[vid])
        found_units = (units(base), units(vid)) if changed else ({}, {})
        entry["premise"] = l1.premise(
            sources[base][0], sources[vid][0], changed, found_units[1], found_units[0]
        )
        if entry["premise"]["verdict"] in l1.METHODS[l1.PREMISE]:
            why = premise_held_back(entry, *found_units)
            entry["premise"]["heldBack"] = why
            if why is None:
                entry["closures"].append(
                    {
                        "method": l1.PREMISE,
                        "power": "close",
                        "verdict": entry["premise"]["verdict"],
                        "files": [f["file"] for f in entry["premise"]["files"]],
                    }
                )
        try:
            entry["impact"] = l1.impact(sources[vid][0], changed, entry["options"], passes)
        except offline.L0Error as error:
            entry["impact"] = [
                {"change": f"none read ({error})", "programs": [], "passes": [], "views": []}
            ]
    properties = {}
    for (vid, dim), dumped in taken.items():
        name = l1.PREPROCESSED
        if variants[vid].get("build") is not None and name in dumped["files"]:
            path = raw / dumped["capture"]["dump"]["folder"] / name
            properties[(vid, dim)] = path.read_text(encoding="utf-8", errors="replace")
    problems = l1.audit(passes, properties)
    iris_pinned(root)  # the uniform list was read in that jar
    read: dict[str, dict[str, set[str]]] = {}  # per manifest: one print, read once
    for (vid, dim), dumped in sorted(taken.items()):
        if variants[vid].get("build") is None:
            continue
        manifest = dumped["capture"]["dump"]["manifest"]
        if manifest not in read:
            declared = l1.pack_uniforms(sources[vid][0])
            texts = l1.stage_texts(raw, dumped["capture"], dumped["files"])
            read[manifest] = {k: l1.read_uniforms(t, declared) for k, t in texts.items()}
        customs = {m["name"] for m in l1.CUSTOM_UNIFORM.finditer(properties.get((vid, dim), ""))}
        problems += l1.uniform_problems(f"{vid} in {dim}", read[manifest], customs)
    offline_field = {
        "level": "L1",
        "baseline": base,
        "closures": [{"variant": e["variant"], **c} for e in judged for c in e["closures"]],
        "candidates": [
            {
                "variant": e["variant"],
                "tookEffect": e["tookEffect"],
                "undumped": e["undumped"],
                "unprinted": e["unprinted"],
                "dimensions": {
                    d: None
                    if row is None
                    else {
                        "equal": row["equal"],
                        "changed": len(row["changed"]),
                        "baselineOnly": len(row["baselineOnly"]),
                        "candidateOnly": len(row["candidateOnly"]),
                    }
                    for d, row in e["dimensions"].items()
                },
                "premise": e["premise"]["verdict"],
                "options": e["options"],
            }
            for e in judged
        ],
        "pipeline": {"file": PIPELINE, "sha256": hashlib.sha256(spec).hexdigest()},
        "audit": problems,
    }
    held = found.get("offline")
    # The closures and the candidates' judgments; the audit follows pipeline.json, which may move.
    judged_keys = ("level", "baseline", "closures", "candidates")
    agrees = (
        None
        if held is None
        else all(
            record.canonical(held.get(k)) == record.canonical(offline_field[k]) for k in judged_keys
        )
    )
    return {
        "ok": True,
        "run": found["name"],
        "status": found.get("status"),
        "baseline": base,
        "candidates": judged,
        "audit": problems,
        "offline": offline_field,
        "recordAgrees": agrees,
        "seconds": round(time.perf_counter() - started, 2),
    }


def stage_list(keys: list[str]) -> str:
    """Stage files grouped by program: `basic (fsh, json, vsh)`, without patched_shaders/."""
    grouped: dict[str, list[str]] = {}
    for key in keys:
        name = key.removeprefix(f"{l1.PATCHED}/")
        program, _, ending = name.rpartition(".")
        grouped.setdefault(program or name, []).append(ending)
    return ", ".join(f"{p} ({' '.join(sorted(e))})" for p, e in grouped.items())


def print_l1(result: dict) -> None:
    print(
        f"{L1_PREFIX}: {result['run']} ({result['status']}), baseline {result['baseline']}, "
        f"{len(result['candidates'])} candidates"
    )
    short = {d: d.removeprefix("minecraft:") for d in record.DIMENSIONS}
    for entry in result["candidates"]:
        vid, rows = entry["variant"], entry["dimensions"]
        equal = [short[d] for d, r in rows.items() if r is not None and r["equal"]]
        effect = "took effect" if entry["tookEffect"] else "did not take effect"
        same = ", ".join(equal) or "none"
        print(f"{vid} against {result['baseline']}: {effect}; dump-equal in {same}")
        shown_rows: dict[str, list[str]] = {}
        for d, row in rows.items():
            if row is None:
                print(f"  {short[d]}: not dumped")
                continue
            if row["equal"]:
                continue
            text = (
                f"{len(row['changed'])} stages differ: {stage_list(row['changed'])}"
                if row["changed"]
                else "the stages are equal"
            )
            for label, keys in (
                ("only in the baseline", row["baselineOnly"]),
                ("only in it", row["candidateOnly"]),
            ):
                if keys:
                    text += f"; {label}: {stage_list(keys)}"
            if row["renumbered"]:
                text += "; Iris's counter numbered them otherwise"
            shown_rows.setdefault(text, []).append(short[d])
        for text, dims in shown_rows.items():
            print(f"  {', '.join(dims)}: {text}")
        premise = entry["premise"]
        held = premise.get("heldBack")
        print(f"  premise: {premise['verdict']}" + (f", closing nothing: {held}" if held else ""))
        if entry["unprinted"]:
            files = ", ".join(entry["unprinted"])
            print(f"  changed, in no print (no dump-equality closure): {files}")
        for item in premise["files"]:
            for kind in ("functions", "removed"):
                for fn in item[kind]:
                    where = "; ".join(f"{short[d]} {len(v)}" for d, v in fn["reachedIn"].items())
                    said = "removed" if kind == "removed" else "changed"
                    print(
                        f"    {item['file']}: {fn['name']} {said}, defined in {fn['defined']} "
                        f"dumped stages, reached from main in {fn['reached']}"
                        + (f" ({where})" if where else "")
                    )
        for why in premise.get("undecided", []):
            print(f"    undecided: {why}")
        if entry["options"]:
            print(f"  options read back otherwise: {', '.join(entry['options'])}")
        for row in entry["impact"]:
            print(
                f"  impact: {row['change']} -> {len(row['programs'])} program files -> passes "
                f"{', '.join(row['passes']) or 'none'} -> {len(row['views'])} views"
            )
        for closure in entry["closures"]:
            dims = ", ".join(short[d] for d in closure.get("dimensions", [])) or "every dimension"
            print(f"  CLOSED ({closure['method']}): {closure['verdict']}, in {dims}")
    print(f"audit: {len(result['audit'])} problems over the dumps' passes")
    for problem in result["audit"]:
        print(f"FAIL {problem}")
    agrees = {None: "holds no offline field", True: "agrees", False: "DIFFERS"}[
        result["recordAgrees"]
    ]
    closures = result["offline"]["closures"]
    print(
        f"{L1_PREFIX}: {len(closures)} closures"
        + (
            f" ({'; '.join(c['variant'] + ' ' + c['verdict'] for c in closures)})"
            if closures
            else ""
        )
        + f"; the record's offline field {agrees}; in {result['seconds']} s"
    )


# L2 (docs/offline.md#levels, plans/m3.md D70): optilux/l2.py on a dump record.

L2_PREFIX = "optilux check L2"
L2_DIR = "l2"


def rga_exe(root: Path) -> tuple[Path, str]:
    """RGA as config/tools.json pins it under runtime/tools/, the version it prints held to the
    pin's `printed`, exactly (`--version`: "Radeon GPU Analyzer Version: 2.15.0.30 (...)")."""
    pin = json.loads((root / TOOLS).read_text(encoding="utf-8")).get("rga")
    if not isinstance(pin, dict) or not all(pin.get(k) for k in ("unpack", "exe", "printed")):
        raise l2.L2Error(f"{TOOLS} pins no rga with unpack, exe and printed; fix: restore it")
    exe = root / TOOLS_DIR / pin["unpack"] / pin["exe"]
    try:
        done = subprocess.run(  # noqa: S603 the pinned RGA, no shell
            [str(exe), "--version"], capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise l2.L2Error(f"{exe} did not run ({error}); fix: `uv run optilux install`") from None
    found = re.search(r"Version: (\S+)", done.stdout.decode("utf-8", "replace"))
    version = found[1] if found else "nothing"
    if version != pin["printed"]:
        raise l2.L2Error(
            f"{exe} prints version {version}, the pin says {pin['printed']}; fix: `uv run "
            "optilux install`"
        )
    return exe, version


def run_l2(root: Path, named: str) -> dict:
    """`check L2`'s whole result: each distinct program of the record's prints through RGA, the
    prints that share it, its stages' figures or its failure; the results also written to
    results/raw/<run>/l2/l2.json."""
    started = time.perf_counter()
    try:
        found = dump_record(root, named)
        taken = l1.prints(found)
    except l1.L1Error as error:
        raise l2.L2Error(str(error)) from None
    if found.get("status") != "ok":
        raise l2.L2Error(
            f"{named} ended {found.get('status')}; L2 reads an ok dump record's prints, whose "
            "every stage the game compiled; fix: a dump run that ended ok"
        )
    exe, version = rga_exe(root)
    raw = root / found["raw"]
    by_manifest: dict[str, list[tuple[str, str]]] = {}
    for (vid, dim), dumped in taken.items():
        by_manifest.setdefault(dumped["capture"]["dump"]["manifest"], []).append((vid, dim))
    distinct: dict[str, l2.Program] = {}
    prints_out = []
    for manifest, shared in by_manifest.items():
        dumped = taken[shared[0]]
        found_programs, skipped = l2.programs(raw, dumped["capture"], dumped["files"])
        for program in found_programs:
            distinct.setdefault(program.digest, program)
        prints_out.append(
            {
                "manifest": manifest,
                "dumps": [{"variant": v, "dimension": d} for v, d in shared],
                "programs": [
                    {"program": p.name, "stages": list(p.stages), "digest": p.digest}
                    for p in found_programs
                ],
                "notBuilt": skipped,
            }
        )
    out = raw / L2_DIR
    out.mkdir(parents=True, exist_ok=True)

    def one(program: l2.Program) -> dict:
        return l2.analyze(exe, program, out / program.digest[:16])

    with ThreadPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) // 2))) as pool:
        results = dict(zip(distinct, pool.map(one, distinct.values()), strict=True))
    broken = [r for r in results.values() if r["tool"]]
    if broken:
        raise l2.L2Error(
            f"RGA failed on {len(broken)} of {len(results)} programs, not a shader's failure: "
            f"{broken[0]['tool']}; fix: `uv run optilux install`, then rerun"
        )
    failures = sorted(
        {
            f"{p['program']}.{ending}"
            for found_print in prints_out
            for p in found_print["programs"]
            for ending in results[p["digest"]]["failed"]
        }
    )
    result = {
        "ok": True,
        "run": found["name"],
        "rga": version,
        "asic": l2.ASIC,
        "folder": shown(out, root),
        "prints": prints_out,
        "results": results,
        "failures": failures,
        "seconds": round(time.perf_counter() - started, 2),
    }
    (out / "l2.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def print_l2(result: dict) -> None:
    results = result["results"]
    print(
        f"{L2_PREFIX}: {result['run']}: RGA {result['rga']}, {result['asic']}: {len(results)} "
        f"distinct programs in {len(result['prints'])} distinct prints, outputs under "
        f"{result['folder']}/"
    )
    short = {d: d.removeprefix("minecraft:") for d in record.DIMENSIONS}
    stages = 0
    for found in result["prints"]:
        dumps = ", ".join(f"{d['variant']} in {short[d['dimension']]}" for d in found["dumps"])
        print(f"print {found['manifest'][:12]}... ({dumps}):")
        for entry in found["programs"]:
            done = results[entry["digest"]]
            for ending in entry["stages"]:
                stages += 1
                name = f"{entry['program']}.{ending}"
                if ending in done["failed"]:
                    why = " | ".join(done["failed"][ending][:3])
                    print(f"  {name}: known offline failure: {why}")
                    continue
                stage = done["stages"][ending]
                print(
                    f"  {name}: VGPRs {stage['vgprs']}, SGPRs {stage['sgprs']}, live VGPRs "
                    f"{stage['liveVgprs']}, live SGPRs {stage['liveSgprs']}, ISA "
                    f"{stage['isaBytes']} B, spills {stage['vgprSpills']}/{stage['sgprSpills']}"
                )
        for name in found["notBuilt"]:
            print(f"  {name}: not built (a compute stage, which L2 does not build yet)")
    print(
        f"{L2_PREFIX}: {stages} stages in {len(results)} distinct programs, "
        f"{len(result['failures'])} known offline failures"
        + (f" ({', '.join(result['failures'])})" if result["failures"] else "")
        + f"; explains only; in {result['seconds']} s"
    )


# L3 (docs/offline.md#levels, plans/m4.md M4.P02): optilux/l3.py on the pack's includes.

L3_PREFIX = "optilux check L3"


def engine(root: Path) -> l3.Engine:
    """Iris's expression engine (optilux/expressions.py) as L3 calls it, its refusals L3's."""

    def evaluate(inputs: list, found: list) -> dict:
        try:
            return expressions.evaluate(root, inputs, found)
        except expressions.ExpressionError as error:
            raise l3.L3Error(str(error)) from None

    return evaluate


def run_l3(root: Path, named: str | None) -> dict:
    """`check L3`'s whole result: the pack, the context, per include its tests' functions or
    none, every problem, and whether all passed."""
    started = time.perf_counter()
    pack = load_pack(root, named)
    found_macros = macros(root)
    ctx = l3.context()
    try:
        gl = l3.renderer(ctx)
        found = l3.check(ctx, pack, root / l3.TESTS_DIR, found_macros, engine(root))
    finally:
        ctx.release()
    return {
        "ok": not found["problems"],
        "pack": pack.label,
        "files": len(pack.files),
        "sha512": pack.sha512,
        "opengl": gl,
        "tests": l3.TESTS_DIR,
        **found,
        "seconds": round(time.perf_counter() - started, 2),
    }


def print_l3(found: dict) -> None:
    digest = f", zip sha512 {found['sha512'][:12]}..." if found["sha512"] else ""
    print(
        f"{L3_PREFIX}: {found['pack']}: {found['files']} files{digest}; OpenGL {found['opengl']}; "
        f"tests under {found['tests']}/"
    )
    for entry in found["includes"]:
        functions = entry["functions"]
        if entry["test"] is None:
            print(f"{entry['include']}: no L3 test")
            continue
        cases = sum(f["cases"] for f in functions)
        print(
            f"{entry['include']} ({entry['test']}): {len(functions)} functions over {cases:,} cases"
        )
        for f in functions:
            allowed = l3.number(f["tolerance"]) + (
                f" + {l3.number(f['relative'])} x |golden|" if f["relative"] else ""
            )
            state = "ok" if not f["problems"] else "FAIL"
            print(
                f"  {state} {f['function']} at {f['options']}: {f['cases']:,} cases, "
                f"{f['failed']} failed, worst {l3.number(f['worst'])} within {allowed}"
            )
    uniforms = found["uniforms"]
    defined = ", ".join(uniforms["defined"]) or "none"
    print(
        f"custom uniforms: {uniforms['file']} defines {len(uniforms['defined'])} at the defaults "
        f"({defined}); tests: {uniforms['test'] or 'none'}"
    )
    for u in uniforms["tests"]:
        allowed = l3.number(u["tolerance"]) + (
            f" + {l3.number(u['relative'])} x |golden|" if u["relative"] else ""
        )
        reads = f" (reads {', '.join(u['reads'])})" if u["reads"] else ""
        state = "ok" if not u["problems"] else "FAIL"
        print(
            f"  {state} uniform {u['uniform']}{reads} at {u['options']}: {u['cases']:,} cases, "
            f"{u['failed']} failed, worst {l3.number(u['worst'])} within {allowed}"
        )
    for problem in found["problems"]:
        print(f"FAIL {problem}")
    tested = [e for e in found["includes"] if e["test"] is not None]
    functions = [f for e in tested for f in e["functions"]]
    verdict = "pass" if found["ok"] else f"FAIL ({len(found['problems'])} problems)"
    print(
        f"{L3_PREFIX}: {verdict}: {len(tested)} of {len(found['includes'])} includes tested, "
        f"{len(functions)} functions over {sum(f['cases'] for f in functions):,} cases, "
        f"{len(uniforms['tests'])} uniform tests over "
        f"{sum(u['cases'] for u in uniforms['tests']):,} cases, in {found['seconds']} s"
    )


def run(args: argparse.Namespace) -> int:
    if args.level == "L3":
        try:
            found = run_l3(REPO_ROOT, args.pack)
        except (l3.L3Error, offline.L0Error, platform.PlatformError, OSError) as error:
            if args.json:
                print(json.dumps({"ok": False, "error": str(error)}))
            else:
                print(f"{L3_PREFIX}: {error}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(found))
        else:
            print_l3(found)
        return 0 if found["ok"] else 1
    if args.level == "L2":
        try:
            found = run_l2(REPO_ROOT, args.record)
        except (l2.L2Error, platform.PlatformError, OSError, ValueError) as error:
            if args.json:
                print(json.dumps({"ok": False, "error": str(error)}))
            else:
                print(f"{L2_PREFIX}: {error}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(found))
        else:
            print_l2(found)
        return 0
    if args.level == "L1":
        try:
            result = run_l1(REPO_ROOT, args.record)
        except (l1.L1Error, offline.L0Error, platform.PlatformError, OSError, ValueError) as error:
            if args.json:
                print(json.dumps({"ok": False, "error": str(error)}))
            else:
                print(f"{L1_PREFIX}: {error}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result))
        else:
            print_l1(result)
        return 0 if result["recordAgrees"] is not False else 1
    try:
        found = run_l0(REPO_ROOT, args.pack)
    except (offline.L0Error, platform.PlatformError, verify.SimilarityError, OSError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(found))
    else:
        print_text(found)
    return 0 if found["ok"] else 1


VERB = Verb(
    name="check",
    help="offline levels (L0: glslang over the variant matrix, similarity, the profile check)",
    run=run,
    configure=configure,
)
