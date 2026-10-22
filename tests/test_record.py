"""The run record (docs/run-record.md, docs/plans/m1.md 0.01.08 and 0.01.09, docs/plans/m2.md
M2.P01): the tree hash on a fixture tree, the run spec's checks on fixtures (every refusal naming
its fix), the views file, the identity and the record writer against the identity key list, the
system facts on a fake machine and the D3DKMT reader on a fake gdi32, the settings' unwritten
keys, the measured modules' closure and PresentMon's arguments, the launch held against the
identity built before it; `run --check` on a fixture root; run's readers: the jcmd outputs and
the broken-pack writer on a fixture zip."""

import copy
import ctypes
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from conftest import copy_config, git

from optilux import (
    REPO_ROOT,
    acceptance,
    cli,
    launch,
    modclient,
    platform,
    presentmon,
    record,
    session,
)
from optilux.verbs import install
from optilux.verbs import run as run_verb

PLAT = platform.load(REPO_ROOT)
SUITE = json.loads((REPO_ROOT / platform.SUITE).read_text(encoding="utf-8"))
PACK = launch.reference_pack(PLAT).file
VIEWS = REPO_ROOT / record.VIEWS / "provisional.json"
# The session's resource-pack set as launch writes its files, bottom to top.
PINNED = {p.slug: p.file for p in PLAT.tier_files("bench") if p.kind == "resourcePack"}
FILES = [PINNED.get(s, install.STATIC_FILE) for s in SUITE["resourcePacks"][record.PACK_SET]]


# The tree hash.


def tree(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def test_the_tree_hash_is_the_sha256_of_the_sorted_manifest(tmp_path: Path) -> None:
    folder = tree(tmp_path / "w", {"level.dat": b"L", "region/r.0.0.mca": b"R", "a/b": b"B"})
    (folder / "empty").mkdir()  # an empty folder holds no file and adds nothing
    lines = [
        f"{hashlib.sha256(b'B').hexdigest()}  a/b\n",
        f"{hashlib.sha256(b'L').hexdigest()}  level.dat\n",
        f"{hashlib.sha256(b'R').hexdigest()}  region/r.0.0.mca\n",
    ]
    expected = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    assert record.tree_hash(folder) == (expected, 3)
    assert record.tree_text(record.tree_files(folder)) == "".join(lines)


def test_the_tree_hash_moves_with_a_content_a_name_or_a_new_file(tmp_path: Path) -> None:
    files = {"level.dat": b"L", "players/data/u.dat": b"P"}
    base = record.tree_hash(tree(tmp_path / "a", files))[0]
    assert record.tree_hash(tree(tmp_path / "b", files))[0] == base  # another folder, same tree
    assert record.tree_hash(tree(tmp_path / "c", {**files, "level.dat": b"M"}))[0] != base
    renamed = {"level.dat": b"L", "players/data/v.dat": b"P"}
    assert record.tree_hash(tree(tmp_path / "d", renamed))[0] != base
    assert record.tree_hash(tree(tmp_path / "e", {**files, "session.lock": b"x"}))[0] != base


def test_a_missing_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(record.RecordError, match="fix:"):
        record.tree_hash(tmp_path / "absent")


# The run spec.


def spec() -> dict:
    return {
        "name": "m1-acceptance-test",
        "kind": "acceptance",
        "views": "provisional",
        "world": "spike",
        "variants": [{"pack": PACK, "profile": None}],
        "tier": "bench",
        "resourcePacks": record.PACK_SET,
        "items": ["A10", "A1", "A2", "A3"],
        "notes": "a fixture",
    }


@pytest.fixture
def fixture_root(tmp_path: Path) -> tuple[Path, Path]:
    """A root with the views file, its snapshot and a saves folder holding the world."""
    views = tmp_path / record.VIEWS
    views.mkdir(parents=True)
    shutil.copyfile(VIEWS, views / VIEWS.name)
    (tmp_path / record.SNAPSHOTS / "provisional").mkdir(parents=True)
    saves = tmp_path / "saves"
    tree(saves / "spike", {"level.dat": b"L"})
    return tmp_path, saves


def check(root: Path, saves: Path, data) -> record.Spec:
    return record.check_spec(root, data, PLAT, SUITE, saves, PACK)


def test_a_valid_spec_is_taken_with_its_items_in_run_order(fixture_root) -> None:
    root, saves = fixture_root
    found = check(root, saves, spec())
    assert (found.name, found.kind, found.views, found.world) == (
        "m1-acceptance-test",
        "acceptance",
        "provisional",
        "spike",
    )
    assert found.items == ("A1", "A2", "A3", "A10")
    assert (found.pack, found.tier, found.resource_packs) == (PACK, "bench", record.PACK_SET)


def drop(key: str):
    def change(data: dict) -> None:
        del data[key]

    return change


def put(key: str, value):
    def change(data: dict) -> None:
        data[key] = value

    return change


REFUSALS = [
    (drop("world"), "lacks world"),
    (put("seed", 1), "unknown seed"),
    (put("name", "Bad Name"), "is not"),
    (put("name", "x" * 41), "is not"),
    (put("kind", "measurement"), "measures a mode's schedule"),
    (put("kind", "smoke"), "one of measurement"),
    (put("mode", "quick"), "takes A8, A11, each once"),
    (put("mode", "slow"), "one of quick, full"),
    (put("calibration", None), "calibration is for measured runs"),
    (put("heap", True), "heap is for measured runs"),
    (put("treatment", "mods"), "declared treatments come with the JVM track"),
    (put("tier", "dev"), "bench tier"),
    (put("views", "final"), "no views file"),
    (put("views", "../x"), "names no views file"),
    (put("world", "absent"), "no folder"),
    (put("world", "../spike"), "no folder"),
    (put("variants", [{"pack": "other.zip", "profile": None}]), "one variant"),
    (put("variants", [{"pack": PACK, "profile": "played"}]), "without a mode has one variant"),
    (put("variants", [{"pack": "optilux", "profile": "played"}]), "at its pack's defaults"),
    (put("variants", [{"pack": "optilux@-x", "profile": None}]), "no ref a spec may name"),
    (put("variants", [{"pack": "optilux@no-such-ref", "profile": None}]), "names no commit"),
    (put("items", ["A8"]), "runs on a measured schedule"),
    (put("resourcePacks", "standard"), "every session runs the deterministic set"),
    (put("resourcePacks", "nope"), "no set of suite.json"),
    (put("items", []), "no acceptance item"),
    (put("items", ["A1", "A1"]), "twice"),
    (put("items", ["A13"]), "no acceptance item"),
    (put("items", ["A5"]), "later milestone"),
    (put("reloads", 15), "multiple of 10"),
    (put("reloads", -10), "multiple of 10"),
    (put("reloads", True), "multiple of 10"),
    (put("reloads", 290), "over capture.reloadCap 20"),
    (put("notes", 3), "notes must be text"),
]


@pytest.mark.parametrize(("change", "says"), REFUSALS)
def test_each_refusal_names_its_fix(fixture_root, change, says: str) -> None:
    root, saves = fixture_root
    data = spec()
    change(data)
    with pytest.raises(record.RecordError) as refused:
        check(root, saves, data)
    assert says in str(refused.value)
    assert "fix:" in str(refused.value)


def test_an_acceptance_run_takes_the_optilux_pack_from_the_tree_or_a_commit(fixture_root) -> None:
    """plans/m3.md D63: `optilux` (the working tree) and `optilux@<ref>` (the commit the ref names
    when the spec is checked); A4 breaks the reference pack's own program, so it is refused."""
    root, saves = fixture_root
    found = check(root, saves, {**spec(), "variants": [{"pack": "optilux", "profile": None}]})
    assert found.optilux == {"variant": "optilux", "ref": None, "commit": None}
    assert check(root, saves, spec()).optilux is None  # the reference pack
    git(root, "init", "-q", "-b", "m3")
    git(
        root,
        "-c",
        "user.name=F",
        "-c",
        "user.email=f@x.invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "chore: a commit",
    )
    sha = git(root, "rev-parse", "HEAD").stdout.strip()
    found = check(root, saves, {**spec(), "variants": [{"pack": "optilux@HEAD", "profile": None}]})
    assert found.optilux == {"variant": "optilux@HEAD", "ref": "HEAD", "commit": sha}
    data = {**spec(), "variants": [{"pack": "optilux", "profile": None}], "items": ["A4", "A10"]}
    with pytest.raises(record.RecordError, match="A4 breaks the reference pack's own program"):
        check(root, saves, data)


def test_a_spec_that_is_no_object_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    with pytest.raises(record.RecordError, match="fix:"):
        check(root, saves, ["not", "an", "object"])


def test_a_used_run_name_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    (root / record.RAW / "m1-acceptance-test").mkdir(parents=True)
    with pytest.raises(record.RecordError, match="single-use"):
        check(root, saves, spec())


def test_a_views_file_without_its_snapshot_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    (root / record.SNAPSHOTS / "provisional").rmdir()
    with pytest.raises(record.RecordError, match="no snapshot snapshots/provisional/; fix:"):
        check(root, saves, spec())


def test_the_reload_budget_is_checked(fixture_root) -> None:
    root, saves = fixture_root
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 1
    with pytest.raises(record.RecordError, match="reloadCap 1; fix:"):
        record.check_spec(root, spec(), PLAT, suite, saves, PACK)


def test_the_0_01_09_items_and_f4s_reloads_are_taken(fixture_root) -> None:
    root, saves = fixture_root
    data = {**spec(), "items": ["A9", "A10", "A7", "A4"], "reloads": 50}
    # The session's reloads: two at the start, A4's two, F4's fifty; over plans/m2.md D43's 20.
    with pytest.raises(record.RecordError, match=r"plans 54 reloads, over capture\.reloadCap 20"):
        check(root, saves, data)
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 54
    found = record.check_spec(root, data, PLAT, suite, saves, PACK)
    assert found.items == ("A4", "A7", "A9", "A10") and found.reloads == 50
    assert check(root, saves, spec()).reloads == 0
    suite["capture"]["reloadCap"] = 53
    with pytest.raises(record.RecordError, match="plans 54 reloads"):
        record.check_spec(root, data, PLAT, suite, saves, PACK)


# The views file.


def test_the_committed_views_file_holds_one_view_per_dimension() -> None:
    data, path = record.load_views(REPO_ROOT, "provisional")
    assert path == VIEWS
    assert [view["dim"] for view in data["views"]] == list(record.DIMENSIONS)


def test_the_bench_views_file_holds_the_suite_roles_in_order() -> None:
    # 0.01.11: one view per suite.json view role, in its order, with the role's dimension, time
    # and weather; the world's seed is set beside it.
    dims = dict(zip(("overworld", "nether", "end"), record.DIMENSIONS, strict=True))
    data, _ = record.load_views(REPO_ROOT, "bench_263")
    roles = SUITE["viewRoles"]
    assert [view["id"] for view in data["views"]] == [role["id"] for role in roles]
    for view, role in zip(data["views"], roles, strict=True):
        assert view["dim"] == dims[role["dim"]], view["id"]
        assert (view["time"], view["weather"]) == (role["time"], role["weather"]), view["id"]
    assert SUITE["world"]["seed"] == 263


def views_with(change) -> dict:
    data = json.loads(VIEWS.read_text(encoding="utf-8"))
    change(data["views"])
    return data


BAD_VIEWS = [
    (lambda views: views[0].update(dim="minecraft:moon"), "dim"),
    (lambda views: views[0].update(pitch=91.0), "outside -90..90"),
    (lambda views: views[0].update(x=float("nan")), "finite"),
    (lambda views: views[0].update(time=1.5), "no tick count"),
    (lambda views: views[0].update(weather="snow"), "weather"),
    (lambda views: views[1].update(id=views[0]["id"]), "listed twice"),
    (lambda views: views[0].pop("yaw"), "missing"),
    (lambda views: views[0].update(roll=0), "unknown"),
]


@pytest.mark.parametrize(("change", "says"), BAD_VIEWS)
def test_a_bad_view_is_refused(tmp_path: Path, change, says: str) -> None:
    folder = tmp_path / record.VIEWS
    folder.mkdir(parents=True)
    (folder / "provisional.json").write_text(json.dumps(views_with(change)), encoding="utf-8")
    with pytest.raises(record.RecordError) as refused:
        record.load_views(tmp_path, "provisional")
    assert says in str(refused.value) and "fix:" in str(refused.value)


# The identity and the record.


def doc_identity_keys() -> list[str]:
    """The record keys run-record.md#identity lists, one bullet each, in order."""
    text = (REPO_ROOT / "docs/run-record.md").read_text(encoding="utf-8")
    section = text.split("## Identity", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- `(\w+)`:", section, flags=re.MULTILINE)


def test_the_identity_keys_are_the_docs() -> None:
    assert doc_identity_keys() == list(record.IDENTITY_KEYS)


class FakeMachine(record.Machine):
    def __init__(self, width: int = 3840, height: int = 2160, caps: int = 0b1011) -> None:
        self.size = (width, height)
        self.caps = caps  # P15's reading: supported, enabled, not by default, VSync control

    def hags(self, name: str) -> tuple[int, str]:
        assert name == "\\\\.\\DISPLAY2"  # the primary's adapter
        return self.caps, "0x11d94"

    def displays(self) -> list[dict]:
        return [
            {"name": "\\\\.\\DISPLAY1", "adapter": "GPU X", "flags": 0x1},
            {"name": "\\\\.\\DISPLAY2", "adapter": "GPU X", "flags": 0x5},
        ]

    def display_mode(self, name: str) -> dict:
        assert name == "\\\\.\\DISPLAY2"  # the primary
        return {"width": self.size[0], "height": self.size[1], "hz": 240, "dpiAware": True}

    def registry(self, key: str, value: str):
        return {"HwSchMode": 2, "UBR": 9457}[value]

    def driver(self, adapter: str) -> str | None:
        return "1.2.3" if adapter == "GPU X" else None

    def windows_build(self) -> int:
        return 26200


def options() -> dict[str, str]:
    return launch.written_options(SUITE["display"], {}, FILES)


def test_the_system_facts_come_from_the_primary_display() -> None:
    found, recorded = record.system_facts(FakeMachine(), options(), SUITE["display"])
    assert found == {
        "gpu": "GPU X",
        "hags": True,
        "resolution": "3840x2160",
        "windowMode": "exclusive fullscreen",
        "windowsBuild": 26200,
    }
    assert recorded["driver"] == "1.2.3" and recorded["windowsRevision"] == 9457
    assert recorded["display"] == {"name": "\\\\.\\DISPLAY2", "hz": 240, "displays": 2}
    assert recorded["hags"] == {
        "caps": 0b1011,
        "supported": True,
        "enabledByDefault": False,
        "adapterLuid": "0x11d94",
    }
    assert recorded["hwSchMode"] == 2  # requested, recorded, never matched (id6)


def test_hags_is_the_applied_state_and_hwschmode_only_recorded() -> None:
    """D38: the caps' HwSchEnabled bit, whatever the registry requests; an unset HwSchMode is
    recorded as None, never read as off, and a failed read as unread, never as unset."""

    class Requested(FakeMachine):
        def __init__(self, error: OSError, caps: int) -> None:
            super().__init__(caps=caps)
            self.error = error

        def registry(self, key: str, value: str):
            if value == "HwSchMode":
                raise self.error
            return super().registry(key, value)

    absent = Requested(FileNotFoundError(2, "absent"), 0b1001)
    found, recorded = record.system_facts(absent, options(), SUITE["display"])
    assert found["hags"] is False and recorded["hwSchMode"] is None
    assert recorded["hags"]["supported"] is True
    denied = Requested(PermissionError(5, "denied"), 0b1011)
    found, recorded = record.system_facts(denied, options(), SUITE["display"])
    assert found["hags"] is True and recorded["hwSchMode"].startswith("unread: ")
    on, _ = record.system_facts(FakeMachine(caps=0b0011), options(), SUITE["display"])
    assert on["hags"] is True


def test_a_display_or_window_mode_off_the_suite_is_refused() -> None:
    with pytest.raises(record.RecordError, match=r"runs 2560x1440.*never changes system"):
        record.system_facts(FakeMachine(2560, 1440), options(), SUITE["display"])
    windowed = {**options(), "fullscreen": "false"}
    with pytest.raises(record.RecordError, match=r"give windowed.*fix:"):
        record.system_facts(FakeMachine(), windowed, SUITE["display"])


RELEASE = b'IMPLEMENTOR="Eclipse Adoptium"\nJAVA_RUNTIME_VERSION="25.0.4.1+1-LTS"\n'
JAVA_PROFILE = json.loads((REPO_ROOT / "config/java/bench.json").read_text(encoding="utf-8"))


def test_the_java_identity_is_read_before_the_launch(tmp_path: Path) -> None:
    """The release file read and hashed before the launch (id7); the running game's version is
    held against it after (launch_differences)."""
    home = tree(tmp_path / "jdk", {"release": RELEASE})
    found = record.java_identity(home, JAVA_PROFILE)
    assert found["version"] == "25.0.4.1+1-LTS" and found["heap"]["xmx"] == 6144
    assert found["release"] == hashlib.sha256(RELEASE).hexdigest()
    (home / "release").write_bytes(RELEASE.replace(b"Eclipse", b"Other"))
    assert record.java_identity(home, JAVA_PROFILE)["release"] != found["release"]
    (home / "release").write_bytes(b'IMPLEMENTOR="x"\n')
    with pytest.raises(record.RecordError, match=r"names no JAVA_RUNTIME_VERSION.*install"):
        record.java_identity(home, JAVA_PROFILE)
    with pytest.raises(record.RecordError, match=r"no release file.*install"):
        record.java_identity(tmp_path / "absent", JAVA_PROFILE)


def built_identity(**changes) -> dict:
    system, _ = record.system_facts(FakeMachine(), options(), SUITE["display"])
    pre = launch.prelaunch(SUITE["display"], "bench", PACK, {}, FILES)
    settings = record.settings_identity(
        launch.settings_facts(pre, True), {"sha256": "e" * 64, "unwritten": {"ao": "true"}}
    )
    found = {
        "plat": PLAT,
        "tier": "bench",
        "spec_path": platform.spec_path(REPO_ROOT, PLAT.id),
        "mods": ["b" * 128, "a" * 128],
        "world": {"snapshot": "snapshots/provisional", "treeSha256": "c" * 64, "files": 3},
        "views_path": VIEWS,
        "packs": [{"file": "Faithful.zip", "sha512": "d" * 128}],
        "settings": settings,
        "suite": SUITE,
        "java": {"runtime": "jdk", "version": "25", "heap": {}, "args": []},
        "system": system,
        "harness": {"modules": {"optilux/record.py": "f" * 64}, "presentMon": {}},
    }
    return record.identity(**{**found, **changes})


def test_the_identity_holds_exactly_the_key_list() -> None:
    found = built_identity()
    assert tuple(found) == record.IDENTITY_KEYS
    record.check_identity(found)
    assert found["mods"] == ["a" * 128, "b" * 128]  # sorted
    assert found["platform"]["tiers"] == ["bench"]


def test_a_note_never_moves_the_suite_hash_and_a_value_does() -> None:
    base = record.suite_identity(SUITE)["sha256"]
    noted = copy.deepcopy(SUITE)
    noted["capture"]["why"] = "another note"
    noted["capture"]["settleWhy"] = "another"
    noted["modes"]["quick"]["estMinutes"] = 99
    assert record.suite_identity(noted)["sha256"] == base
    moved = copy.deepcopy(SUITE)
    moved["capture"]["gpuWarmupS"] = 31
    assert record.suite_identity(moved)["sha256"] != base


def test_the_platform_hash_covers_the_loaded_tiers_only() -> None:
    base = record.platform_identity(PLAT, "bench")["sha256"]
    other = platform.Platform(PLAT.id, PLAT.path, copy.deepcopy(PLAT.data))
    other.data["tiers"]["dev"]["purpose"] = "changed"
    assert record.platform_identity(other, "bench")["sha256"] == base
    other.data["tiers"]["bench"]["purpose"] = "changed"
    assert record.platform_identity(other, "bench")["sha256"] != base


def test_the_platform_identity_leaves_out_the_reference_pack_and_world_prep() -> None:
    """D39: a re-pinned reference pack or a changed prep mod never forces a recalibration."""
    base = record.platform_identity(PLAT, "bench")
    other = platform.Platform(PLAT.id, PLAT.path, copy.deepcopy(PLAT.data))
    other.data["referencePacks"][0]["sha512"] = "0" * 128
    other.data["worldPrep"]["mods"][0]["version"] = "9.9.9"
    assert record.platform_identity(other, "bench") == base
    other.data["gamerules"]["spawnMobs"] = not other.data["gamerules"]["spawnMobs"]
    assert record.platform_identity(other, "bench") != base


# The settings (D37, D39): options.txt's unwritten keys as the game reads them, no shaderPack.


def planned_settings(game: Path, pack: str = PACK) -> dict:
    pre = launch.prelaunch(SUITE["display"], "bench", pack, {}, FILES)
    _, options_file = launch.planned_options(game, pre)
    return record.settings_identity(launch.settings_facts(pre, True), options_file)


def test_a_changed_unwritten_key_changes_the_identity_and_the_pack_does_not(
    tmp_path: Path,
) -> None:
    game = tree(tmp_path / "game", {"options.txt": b"version:4892\nao:true\nparticles:0\r\n"})
    settings = planned_settings(game)
    assert settings["unwritten"] == {"ao": "true", "particles": "0"}
    assert "shaderPack" not in settings["iris"] and settings["iris"]["enableShaders"] == "true"
    assert not (game / "config").exists()  # planned, never written
    base = built_identity(settings=settings)
    assert built_identity(settings=planned_settings(game, "Other.zip")) == base
    (game / "options.txt").write_bytes(b"version:4892\nao:false\nparticles:0\n")
    moved = built_identity(settings=planned_settings(game))
    assert moved["settings"]["unwritten"]["ao"] == "false"
    assert record.sha256_of(moved) != record.sha256_of(base)
    # A written key's old value never reaches the identity: the harness's value wins.
    (game / "options.txt").write_bytes(b"ao:false\nparticles:0\nrenderDistance:2\n")
    assert planned_settings(game)["options"]["renderDistance"] == "16"


# The harness (D36).

MEASURED = {
    "optilux",
    "optilux.acceptance",
    "optilux.launch",
    "optilux.measure",
    "optilux.modclient",
    "optilux.packzip",
    "optilux.platform",
    "optilux.presentmon",
    "optilux.record",
    "optilux.repo",
    "optilux.sendinput",
    "optilux.session",
    "optilux.stats",
    "optilux.verbs",
    "optilux.verbs.install",
    "optilux.verbs.run",
    "optilux.winpipe",
    "optilux.world",
}


def test_the_measured_modules_are_the_runners_import_closure() -> None:
    """Read with ast from optilux/verbs/run.py: winpipe arrives only through a deferred import
    inside a function; the CLI's registry and the other verbs are outside."""
    found = record.module_closure(REPO_ROOT)
    assert set(found) == MEASURED
    assert found["optilux.verbs"] == REPO_ROOT / "optilux" / "verbs" / "__init__.py"


def test_the_closure_follows_relative_and_deferred_imports(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "optilux/__init__.py": b"",
            "optilux/a.py": b"import json\n\ndef f():\n    from optilux import b, NAME\n",
            "optilux/b.py": b"from . import c\nfrom .sub import d\n",
            "optilux/c.py": b"",
            "optilux/sub/__init__.py": b"",
            "optilux/sub/d.py": b"from .. import e\n",
            "optilux/e.py": b"",
            "optilux/unread.py": b"",
        },
    )
    found = record.module_closure(root, "optilux.a")
    assert set(found) == {f"optilux{n}" for n in ("", ".a", ".b", ".c", ".sub", ".sub.d", ".e")}
    with pytest.raises(record.RecordError, match=r"no module optilux\.absent.*fix:"):
        record.module_closure(root, "optilux.absent")


@pytest.fixture
def harness_root(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of the package and a stand-in PresentMon."""
    shutil.copytree(
        REPO_ROOT / "optilux", tmp_path / "optilux", ignore=shutil.ignore_patterns("__pycache__")
    )
    exe = tree(tmp_path / "runtime" / "tools", {"PresentMon.exe": b"MZ"}) / "PresentMon.exe"
    return tmp_path, exe


def test_a_measured_module_or_presentmon_moves_the_harness_and_status_does_not(
    harness_root, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, exe = harness_root
    base = record.harness_identity(root, exe)
    assert sorted(base["modules"]) == sorted(
        record.module_path(root, name).relative_to(root).as_posix()  # type: ignore[union-attr]
        for name in MEASURED
    )
    assert base["presentMon"] == {
        "file": "PresentMon.exe",
        "sha256": hashlib.sha256(b"MZ").hexdigest(),
        "arguments": [
            "--process_id",
            "<pid>",
            "--output_file",
            "<csv>",
            "--qpc_time_ms",
            "--v2_metrics",
            "--session_name",
            "optilux-<run>",
            "--stop_existing_session",
            "--no_console_stats",
        ],
    }
    status = root / "optilux" / "verbs" / "status.py"
    status.write_bytes(status.read_bytes() + b"\n# an edit outside the measured session\n")
    assert record.harness_identity(root, exe) == base
    measured = root / "optilux" / "presentmon.py"
    measured.write_bytes(measured.read_bytes() + b"\n# an edit inside it\n")
    moved = record.harness_identity(root, exe)
    assert moved["modules"]["optilux/presentmon.py"] != base["modules"]["optilux/presentmon.py"]
    assert record.sha256_of(built_identity(harness=moved)) != record.sha256_of(
        built_identity(harness=base)
    )
    measured.write_bytes(measured.read_bytes()[: -len(b"\n# an edit inside it\n")])
    assert record.harness_identity(root, exe) == base
    monkeypatch.setattr(presentmon, "FLAGS", ("--qpc_time_ms",))  # --v2_metrics dropped
    assert record.harness_identity(root, exe)["presentMon"] != base["presentMon"]
    monkeypatch.undo()
    exe.write_bytes(b"MZ2")
    changed = record.harness_identity(root, exe)["presentMon"]["sha256"]
    assert changed != base["presentMon"]["sha256"]


# HAGS as applied: the D3DKMT reader on a fake gdi32 (D38).


class FakeKmt:
    """gdi32's three D3DKMT calls: the adapter opened by its GDI name, the caps written where
    the query points, the adapter closed; each call logged, a status given per call."""

    def __init__(self, caps: int = 0b1011, opened: int = 0, queried: int = 0) -> None:
        self.caps, self.opened, self.queried = caps, opened, queried
        self.calls: list[tuple] = []

    def D3DKMTOpenAdapterFromGdiDisplayName(self, arg) -> int:
        found = arg._obj
        self.calls.append(("open", found.DeviceName))
        if self.opened:
            return self.opened
        found.hAdapter, found.AdapterLuid.LowPart, found.AdapterLuid.HighPart = 7, 0x11D94, 1
        return 0

    def D3DKMTQueryAdapterInfo(self, arg) -> int:
        query = arg._obj
        self.calls.append(("query", query.hAdapter, query.Type, query.PrivateDriverDataSize))
        if self.queried:
            return self.queried
        ctypes.c_uint32.from_address(query.pPrivateDriverData).value = self.caps
        return 0

    def D3DKMTCloseAdapter(self, arg) -> int:
        self.calls.append(("close", arg._obj.hAdapter))
        return 0


class UnreadHags(FakeMachine):
    """A machine whose D3DKMT query fails."""

    def hags(self, name: str) -> tuple[int, str]:
        return record.wddm27_caps(name, FakeKmt(queried=1))


def test_the_d3dkmt_reader_queries_the_wddm_2_7_caps_of_the_displays_adapter() -> None:
    kmt = FakeKmt()
    assert record.wddm27_caps("\\\\.\\DISPLAY2", kmt) == (0b1011, "0x100011d94")
    assert kmt.calls == [("open", "\\\\.\\DISPLAY2"), ("query", 7, 70, 4), ("close", 7)]


def test_a_failed_d3dkmt_call_refuses_the_run_and_closes_what_it_opened() -> None:
    kmt = FakeKmt(queried=-1073741811)  # STATUS_INVALID_PARAMETER
    with pytest.raises(record.RecordError, match=r"QueryAdapterInfo.*0xc000000d.*D38.*fix:"):
        record.wddm27_caps("\\\\.\\DISPLAY2", kmt)
    assert kmt.calls[-1] == ("close", 7)
    kmt = FakeKmt(opened=-1073741811)
    with pytest.raises(record.RecordError, match=r"OpenAdapterFromGdiDisplayName.*fix:"):
        record.wddm27_caps("\\\\.\\DISPLAY9", kmt)
    assert kmt.calls == [("open", "\\\\.\\DISPLAY9")]  # nothing opened, nothing to close
    with pytest.raises(record.RecordError, match="HAGS as applied is unread"):
        record.system_facts(UnreadHags(), options(), SUITE["display"])


# The launch held against the identity built before it (id7, id9).


def launch_facts(identity: dict, unwritten: dict | None = None) -> dict:
    pre = launch.prelaunch(SUITE["display"], "bench", PACK, {}, FILES)
    return {
        "hashes": {
            "packs": [
                {"file": "Faithful.zip", "kind": "resourcePack", "sha512": "d" * 128},
                {"file": PACK, "kind": "referencePack", "sha512": "9" * 128},
            ]
        },
        "mods": {"sha512": list(reversed(identity["mods"]))},
        "settings": launch.settings_facts(pre, True),
        "optionsFile": {"sha256": "e" * 64, "unwritten": unwritten or {"ao": "true"}},
    }


def test_the_launch_is_held_against_the_identity_built_before_it() -> None:
    found = built_identity()
    assert record.launch_differences(found, launch_facts(found)) == []
    moved = launch_facts(found, {"ao": "false"})
    moved["mods"]["sha512"] = ["0" * 128]
    moved["hashes"]["packs"][0]["sha512"] = "1" * 128
    assert record.launch_differences(found, moved) == ["mods", "resourcePacks", "settings"]


def a_record(**changes) -> dict:
    found = {
        "schema": 1,
        "name": "m1-acceptance-test",
        "kind": "acceptance",
        "status": "ok",
        "identity": built_identity(),
        "acceptance": [{"item": "A10", "pass": True, "evidence": {"selftest": {}}}],
    }
    found.update(changes)
    return found


def test_the_writer_writes_once_lf(tmp_path: Path) -> None:
    path = record.write_record(tmp_path, a_record())
    assert path == tmp_path / record.RECORDS / "m1-acceptance-test.json"
    data = path.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    assert json.loads(data)["identity"]["system"]["gpu"] == "GPU X"
    with pytest.raises(record.RecordError, match="never overwritten"):
        record.write_record(tmp_path, a_record())


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (lambda i: i.pop("world"), "lacks \\['world'\\]"),
        (lambda i: i.update(seed=1), "adds \\['seed'\\]"),
        (lambda i: i.update(system=None), "leaves \\['system'\\] empty"),
        (lambda i: i.update(mods=[]), "leaves \\['mods'\\] empty"),
    ],
)
def test_the_writer_refuses_an_identity_off_the_key_list(tmp_path: Path, change, says) -> None:
    found = a_record()
    change(found["identity"])
    with pytest.raises(record.RecordError, match=says):
        record.write_record(tmp_path, found)
    assert not (tmp_path / record.RECORDS).exists()


def test_a_failed_session_may_lack_its_identity_an_ok_one_never(tmp_path: Path) -> None:
    record.write_record(tmp_path, a_record(status="failed", identity=None))
    with pytest.raises(record.RecordError, match="identity is no object"):
        record.write_record(tmp_path, a_record(name="m1-other", identity=None))


def test_the_writer_checks_status_and_items(tmp_path: Path) -> None:
    with pytest.raises(record.RecordError, match="status"):
        record.write_record(tmp_path, a_record(status="fine"))
    with pytest.raises(record.RecordError, match="a pass neither boolean nor null"):
        record.write_record(
            tmp_path, a_record(acceptance=[{"item": "A2", "pass": "yes", "evidence": {}}])
        )
    with pytest.raises(record.RecordError, match="holds no item"):
        record.write_record(tmp_path, a_record(acceptance=[]))


# run's readers.


def test_thread_names_come_from_a_jcmd_dump() -> None:
    dump = (
        "2026-10-07 00:00:00\nFull thread dump OpenJDK 64-Bit Server VM (25.0.4.1+1-LTS):\n\n"
        '"Render thread" #1 [1234] prio=5 os_prio=0 cpu=1.00ms\n'
        "   java.lang.Thread.State: RUNNABLE\n"
        '"optilux-pipe" #40 daemon prio=5\n'
        '"Server thread" #50 prio=5\n'
    )
    assert acceptance.thread_names(dump) == ["Render thread", "optilux-pipe", "Server thread"]


def test_the_helpers_lines_are_sorted_by_kind() -> None:
    log = "\n".join(
        [
            "[00:00:01] [main/INFO]: optilux-helper: inert (no token): no pipe, no thread, no "
            "mixin",
            "[00:00:01] [main/INFO]: optilux-helper: mixin optilux.helper.mixin.X not applied to "
            "net.minecraft.Y: inert (no token)",
            "[00:00:02] [main/INFO]: optilux-helper: mixin optilux.helper.mixin.X applied to "
            "net.minecraft.Y",
            "[00:00:02] [main/INFO]: optilux-helper: active: frame clock on "
            "QueryPerformanceCounter",
            "[00:00:03] [main/INFO]: unrelated",
        ]
    )
    found = acceptance.helper_lines(log)
    assert [len(found[key]) for key in ("inert", "declined", "applied", "active")] == [1, 1, 1, 1]


def test_a_pngs_size_comes_from_its_header() -> None:
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (3840).to_bytes(4, "big")
    assert acceptance.png_size(header + (2160).to_bytes(4, "big")) == (3840, 2160)
    assert acceptance.png_size(b"GIF89a") is None


def test_tp_literals_keep_an_integer_integer() -> None:
    # /tp centres integer x and z only (+0.5): the command text must keep the JSON's kind.
    found = [acceptance.literal(v) for v in (-525, 91.0, -79.5, 495.0)]
    assert found == ["-525", "91.0", "-79.5", "495.0"]


class FakeClient:
    """`command` answers as 26.3's /time set does."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures

    def command(self, text: str, timeout: float, check: bool = True) -> dict:
        # Run in the overworld: 26.3 sets the sender's dimension's clock, the Nether has none.
        assert text == "/execute in minecraft:overworld run time set 6000" and check is False
        return {"succeeded": not self.failures, "messages": [], "failures": self.failures}


def test_time_already_at_the_views_value_counts_as_set() -> None:
    already = ["Clock minecraft:overworld is already set to 6000 tick(s)"]
    assert session.set_time(FakeClient([]), 6000)["succeeded"] is True
    assert session.set_time(FakeClient(already), 6000)["failures"] == already
    with pytest.raises(modclient.ModError, match="time set 6000"):
        session.set_time(FakeClient(["Unknown or incomplete command"]), 6000)
    with pytest.raises(modclient.ModError):
        session.set_time(
            FakeClient(["Clock minecraft:overworld is already set to 600 tick(s)"]), 6000
        )


# F4: GC.heap_info as Temurin 25 prints it (tests/fixtures/run/gc-heap-info.txt, a JVM started with
# the bench heap, 2026-10-07), and the older line without a committed size.


def test_the_heap_after_gc_comes_from_gc_heap_info() -> None:
    text = (REPO_ROOT / "tests" / "fixtures" / "run" / "gc-heap-info.txt").read_text("utf-8")
    assert acceptance.heap_info(text) == {
        "heap": "garbage-first heap",
        "reservedKiB": 6291456,
        "committedKiB": 6291456,
        "usedKiB": 23182,
    }
    older = (
        "1234:\r\n garbage-first heap   total 6291456K, used 725195K [0x0000000680000000, "
        "0x0000000800000000)\n Metaspace       used 151234K, committed 152000K, reserved "
        "1179648K\n"
    )
    found = acceptance.heap_info(older)
    assert (found["usedKiB"], found["committedKiB"], found["metaspaceUsedKiB"]) == (
        725195,
        None,
        151234,
    )
    with pytest.raises(session.RunError, match="no heap line"):
        acceptance.heap_info("1234:\nCommand executed successfully\n")


# A4: the broken copy of a fixture zip.


def fixture_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as out:
        out.writestr(zipfile.ZipInfo("shaders/", (2024, 1, 2, 3, 4, 6)), b"")
        entry = zipfile.ZipInfo("shaders/world0/final.fsh", (2024, 1, 2, 3, 4, 6))
        entry.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(entry, b'#version 130\n#include "/program/final.glsl"\n')
        stored = zipfile.ZipInfo("shaders/shaders.properties", (2023, 5, 6, 7, 8, 10))
        out.writestr(stored, b"sliders=A B\n" * 40)
        deflated = zipfile.ZipInfo("shaders/program/final.glsl", (2023, 5, 6, 7, 8, 12))
        deflated.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(deflated, b"void main() {}\n" * 50)
    return path


def test_the_broken_pack_differs_in_its_program_alone(tmp_path: Path) -> None:
    source = fixture_zip(tmp_path / "Pack.zip")
    before = source.read_bytes()
    packs = tmp_path / "shaderpacks"
    packs.mkdir()
    target = packs / f"{acceptance.A4_PREFIX}Pack.zip"
    facts = acceptance.write_broken_pack(source, target, acceptance.A4_PROGRAM, acceptance.A4_BODY)
    assert source.read_bytes() == before
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target) as new:
        assert new.namelist() == old.namelist()
        for a, b in zip(old.infolist(), new.infolist(), strict=True):
            assert (b.date_time, b.compress_type) == (a.date_time, a.compress_type)
            wanted = acceptance.A4_BODY if a.filename == acceptance.A4_PROGRAM else old.read(a)
            assert new.read(b) == wanted
    assert facts["entries"] == 4 and facts["program"] == acceptance.A4_PROGRAM
    assert facts["brokenSha256"] == hashlib.sha256(acceptance.A4_BODY).hexdigest()
    assert acceptance.A4_IDENTIFIER.encode() in acceptance.A4_BODY
    with pytest.raises(session.RunError, match="exists"):
        acceptance.write_broken_pack(source, target, acceptance.A4_PROGRAM, acceptance.A4_BODY)
    with pytest.raises(session.RunError, match="holds no shaders/world9"):
        acceptance.write_broken_pack(source, packs / "x.zip", "shaders/world9/final.fsh", b"")
    game = tmp_path
    assert [p.name for p in acceptance.broken_copies(game)] == [target.name]
    assert acceptance.remove_broken(game) == {"removed": [target.name], "kept": []}
    assert acceptance.broken_copies(game) == [] and source.is_file()


def test_a_note_in_the_platform_file_is_not_identity() -> None:
    """As for the suite: editing a `why` never forces a recalibration."""
    plat = platform.load(REPO_ROOT)
    edited = platform.Platform(plat.id, plat.path, {**plat.data, "why": "a reworded note"})
    edited.data["tiers"] = {
        name: {**tier, "why": "another note"} for name, tier in plat.data["tiers"].items()
    }
    assert record.platform_identity(edited, "bench") == record.platform_identity(plat, "bench")
    moved = platform.Platform(plat.id, plat.path, {**plat.data, "minecraft": "26.4"})
    assert record.platform_identity(moved, "bench") != record.platform_identity(plat, "bench")


def test_a_driver_or_display_mode_that_cannot_be_read_refuses_the_run() -> None:
    """The record notes the driver version (AGENTS.md); a mode read without DPI awareness may be
    scaled (D22): neither is passed on as a reading."""

    class NoDriver(FakeMachine):
        def driver(self, adapter: str) -> str | None:
            return None

    class Unaware(FakeMachine):
        def display_mode(self, name: str) -> dict:
            return {**super().display_mode(name), "dpiAware": False}

    with pytest.raises(record.RecordError, match="driver"):
        record.system_facts(NoDriver(), options(), SUITE["display"])
    with pytest.raises(record.RecordError, match="DPI"):
        record.system_facts(Unaware(), options(), SUITE["display"])


def test_the_system_and_tree_refusals() -> None:
    class TwoPrimaries(FakeMachine):
        def displays(self) -> list[dict]:
            return [{"name": "a", "adapter": "GPU X", "flags": 0x5}] * 2

    with pytest.raises(record.RecordError, match="2 primary displays"):
        record.system_facts(TwoPrimaries(), options(), SUITE["display"])
    # The suite's exclusive fullscreen (0.01.13: borderless presents as Composed: Copy with GPU
    # GDI); written options that give another mode are refused.
    assert record.window_mode(options()) == "exclusive fullscreen"
    borderless = {**options(), "exclusiveFullscreen": "false"}
    assert record.window_mode(borderless) == "borderless fullscreen"
    with pytest.raises(record.RecordError, match="borderless fullscreen"):
        record.system_facts(FakeMachine(), borderless, SUITE["display"])


def test_the_presentmon_pin_and_the_spec_file_are_checked_before_a_launch(tmp_path: Path) -> None:
    pin = {"presentmon": {"file": "PresentMon.exe", "sha256": "ab" * 32}}
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "tools.json").write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(record.RecordError, match="install"):
        session.check_presentmon(tmp_path)
    (tmp_path / "runtime" / "tools").mkdir(parents=True)
    (tmp_path / "runtime" / "tools" / "PresentMon.exe").write_bytes(b"MZ")
    with pytest.raises(record.RecordError, match="its pin"):
        session.check_presentmon(tmp_path)
    with pytest.raises(record.RecordError, match="cannot read"):
        session.load_spec(tmp_path / "absent.json")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(record.RecordError, match="JSON"):
        session.load_spec(tmp_path / "bad.json")


# `run --check` (plans/m2.md M2.P01): the spec validated, the identity printed, nothing launched.


@pytest.fixture
def check_root(tmp_path: Path) -> tuple[Path, Path]:
    """A root holding the repo's config and package, the snapshot and its live world, the game's
    options.txt, stand-ins for the pinned PresentMon and the JDK's release file; and a spec."""
    root = tmp_path / "root"
    copy_config(root)
    shutil.copytree(
        REPO_ROOT / "optilux", root / "optilux", ignore=shutil.ignore_patterns("__pycache__")
    )
    tree(root / record.SNAPSHOTS / "provisional", {"level.dat": b"L"})
    game = root / "runtime" / PLAT.id / "game"
    tree(game, {"saves/spike/level.dat": b"L", "options.txt": b"version:4892\nao:true\n"})
    tree(root / "runtime" / "tools", {"PresentMon.exe": b"MZ"})
    tree(root / "runtime" / PLAT.id / "files", {install.STATIC_FILE: b"PK static"})
    tools = json.loads((root / "config" / "tools.json").read_text(encoding="utf-8"))
    tools["presentmon"].update(file="PresentMon.exe", sha256=hashlib.sha256(b"MZ").hexdigest())
    (root / "config" / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    tree(root / "runtime" / "java" / JAVA_PROFILE["runtime"]["build"], {"release": RELEASE})
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec()), encoding="utf-8")
    return root, path


def listing(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_the_identity_is_built_before_the_launch_and_nothing_is_written(check_root) -> None:
    root, path = check_root
    before = listing(root)
    ready = run_verb.prepare(root, path, FakeMachine())
    assert listing(root) == before
    found = ready.identity
    assert tuple(found) == record.IDENTITY_KEYS
    assert found["world"] == {
        "snapshot": "snapshots/provisional",
        "treeSha256": record.tree_hash(root / record.SNAPSHOTS / "provisional")[0],
        "files": 1,
    }
    assert found["settings"]["unwritten"] == {"ao": "true"} and found["settings"]["token"]
    assert found["mods"] == sorted(p.sha512 for p in PLAT.tier_files("bench") if p.kind == "mod")
    assert found["java"]["release"] == hashlib.sha256(RELEASE).hexdigest()
    assert found["system"]["hags"] is True
    assert set(found["harness"]["modules"]) >= {"optilux/verbs/run.py", "optilux/session.py"}
    assert ready.recorded["hwSchMode"] == 2


PREPARE_REFUSALS = [
    (lambda root: (root / "config/platforms/mc-26.3.launch.json").unlink(), "launch spec"),
    (
        lambda root: tree(
            root / "runtime" / PLAT.id / "game" / "shaderpacks",
            {f"{acceptance.A4_PREFIX}x.zip": b"Z"},
        ),
        "earlier A4",
    ),
    (lambda root: (root / "runtime/tools/PresentMon.exe").write_bytes(b"MZ2"), "its pin"),
    (
        lambda root: (
            root / "runtime" / "java" / JAVA_PROFILE["runtime"]["build"] / "release"
        ).unlink(),
        "release file",
    ),
]


@pytest.mark.parametrize(("change", "says"), PREPARE_REFUSALS)
def test_each_refusal_before_the_launch_names_its_fix(check_root, change, says: str) -> None:
    root, path = check_root
    change(root)
    with pytest.raises(record.RecordError, match="fix:") as refused:
        run_verb.prepare(root, path, FakeMachine())
    assert says in str(refused.value)
    assert not (root / record.RAW).exists() and not (root / record.RECORDS).exists()


def test_run_check_prints_the_identity_and_launches_nothing(
    check_root, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, path = check_root

    def launched(*args: object, **kwargs: object) -> None:
        raise AssertionError("--check reached a launch")

    monkeypatch.setattr(run_verb, "REPO_ROOT", root)
    monkeypatch.setattr(record, "Machine", FakeMachine)
    monkeypatch.setattr(run_verb, "perform", launched)
    monkeypatch.setattr(launch, "launch", launched)
    assert cli.main(["run", str(path), "--check", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert (found["ok"], found["launched"], found["name"]) == (True, False, "m1-acceptance-test")
    assert tuple(found["identity"]) == record.IDENTITY_KEYS
    assert found["identity"]["system"]["hags"] is True
    assert found["identity"]["harness"]["presentMon"]["file"] == "PresentMon.exe"
    assert cli.main(["run", str(path), "--check"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "nothing launched" in lines[0]
    assert [line.split(":", 1)[0] for line in lines[1:]] == list(record.IDENTITY_KEYS)
    monkeypatch.setattr(record, "Machine", UnreadHags)
    assert cli.main(["run", str(path), "--check", "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["ok"] is False and "HAGS as applied is unread" in refused["problem"]
    assert "fix:" in refused["problem"]
    assert not (root / record.RAW).exists() and not (root / record.RECORDS).exists()


# The session's launch held against the identity (perform, launch faked: nothing starts).


class Ended:
    pid = 4242


def launched_like(root: Path, facts: dict) -> launch.Launched:
    game = root / "runtime" / PLAT.id / "game"
    pre = launch.prelaunch(SUITE["display"], "bench", PACK, {}, FILES)
    found = {
        "gate": {"amd": {}, "java": []},
        "command": {"arguments": ["java"], "check": "equal"},
        **facts,
    }
    return launch.Launched(Ended(), Ended.pid, "t", game / launch.LOG, game, pre, found)


def matching_facts(ready) -> dict:
    """Launch facts that agree with the identity prepare built on check_root."""
    packs = ready.identity["resourcePacks"]["packs"]
    pre = launch.prelaunch(SUITE["display"], "bench", PACK, {}, FILES)
    return {
        "hashes": {"packs": [{**p, "kind": "resourcePack"} for p in packs]},
        "mods": {"sha512": list(ready.identity["mods"])},
        "settings": launch.settings_facts(pre, True),
        "optionsFile": {"sha256": "e" * 64, "unwritten": {"ao": "true"}},
    }


class NoGames:
    """The host as world.restore and the runner ask it before a launch: no game running, no
    process to journal."""

    def processes(self) -> list:
        return []

    def process_facts(self, pid: int) -> None:
        return None


@pytest.fixture
def faked_launch(check_root, monkeypatch: pytest.MonkeyPatch):
    """perform on check_root with launch.launch, open_mod and end faked: `then(root)` runs
    inside the fake launch, `facts(ready)` gives its facts, the ended processes are listed."""
    root, path = check_root
    ready = run_verb.prepare(root, path, FakeMachine())
    ended: list[object] = []
    plan: dict = {"facts": matching_facts, "then": lambda root: None}

    def fake_launch(*args: object, **kwargs: object) -> launch.Launched:
        plan["then"](root)
        return launched_like(root, plan["facts"](ready))

    def no_mod(*args: object, **kwargs: object):
        raise modclient.ModError("no pipe in a test")

    monkeypatch.setattr(launch, "launch", fake_launch)
    monkeypatch.setattr(launch, "open_mod", no_mod)
    monkeypatch.setattr(launch, "end", lambda process, host: ended.append(process) or "killed")

    def quiet(text: str) -> None:
        pass

    def perform() -> dict:
        return run_verb.perform(root, path, NoGames(), FakeMachine(), quiet, quiet)  # type: ignore[arg-type]

    return ready, plan, ended, perform


def test_a_launch_that_contradicts_the_identity_records_none(faked_launch) -> None:
    _, plan, ended, perform = faked_launch
    plan["facts"] = lambda ready: {**matching_facts(ready), "mods": {"sha512": ["0" * 128]}}
    found = perform()
    assert found["identity"] is None and found["status"] == "failed"
    assert "the launch's mods differ" in found["reason"] and "fix:" in found["reason"]
    assert len(ended) == 1  # the game was ended


def test_a_config_file_changed_under_the_launch_records_none(faked_launch) -> None:
    _, plan, ended, perform = faked_launch

    def edit(root: Path) -> None:
        suite = root / platform.SUITE
        data = json.loads(suite.read_text(encoding="utf-8"))
        data["capture"]["gpuWarmupS"] += 1
        suite.write_text(json.dumps(data), encoding="utf-8")

    plan["then"] = edit
    found = perform()
    assert found["identity"] is None and "the launch's suite differ" in found["reason"]
    assert len(ended) == 1


def test_a_failed_launch_records_the_identity_built_before_it(faked_launch) -> None:
    """id9: the launch agreed with the identity, then the mod's session failed; the record keeps
    the identity with status failed."""
    ready, _, ended, perform = faked_launch
    found = perform()
    assert found["identity"] == ready.identity and found["status"] == "failed"
    assert "no pipe in a test" in found["reason"] and len(ended) == 1


def test_run_restores_the_live_world_to_its_snapshot_before_the_launch(faked_launch) -> None:
    """F15, D44: a live world that moved since the snapshot is restored, not refused."""
    ready, plan, _, perform = faked_launch
    live = Path(ready.base) / launch.GAME / launch.SAVES / "spike"
    (live / "level.dat").write_bytes(b"moved")
    (live / "added.dat").write_bytes(b"A")
    seen: dict = {}
    plan["then"] = lambda root: seen.update(at_launch=record.tree_hash(live)[0])
    found = perform()
    assert seen["at_launch"] == ready.snapshot[0]
    restored = found["session"]["restore"]
    assert (restored["copied"], restored["deleted"]) == (1, 1)
    assert restored["treeSha256"] == ready.snapshot[0]
