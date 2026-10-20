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
import json
import sys
import time
from pathlib import Path

from optilux import REPO_ROOT, offline, packzip, platform
from optilux.verbs import Verb, verify
from optilux.verbs.install import REFERENCE, TOOLS, TOOLS_DIR

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


def run(args: argparse.Namespace) -> int:
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
