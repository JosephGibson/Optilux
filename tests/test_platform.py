"""optilux.platform on the committed platform file and the saved 26.3 JSONs: every tier resolves
through `extends` with well-formed pins; the digests; Mojang's rules for Windows x64; the launch
spec built from Mojang's republished JSON equals the committed spec byte for byte, and the one
built from the first JSON differs in exactly the asset index and the version JSON's sha1 and URL
(docs/plans/m1.md P6, D20). Nothing here reads runtime/ or the network."""

import hashlib
import json
from pathlib import Path

import pytest

from optilux import REPO_ROOT, platform

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mc-26.3"
# Mojang's two 26.3 version JSONs: released 2026-09-15, republished 2026-10-06 (P6).
OLD = "4fe1aa1ef8da1cb95c5bad1fb98890ca56dd8ca3"
NEW = "702fe59163c6ee6578607daa85811d9bc9c7cc40"
PACKAGES = "https://piston-meta.mojang.com/v1/packages/{sha1}/26.3.json"
PROFILE_URL = "https://meta.fabricmc.net/v2/versions/loader/26.3/0.19.5/profile/json"
# Maven's .sha1 for fabric-loader 0.19.5, the one library the profile lists without a sha1.
LOADER_SHA1 = "ff9e65cffca4a67f31523e1807fe0855940fcbfa"
OLD_INDEX = "abfaa525f923f807df8b4e4d29c1b5e3a104adbe"
NEW_INDEX = "1e4e4a68dece1c0f51b8f93b45da8fe8da51bcd3"


def version_json(sha1: str) -> dict:
    path = FIXTURES / f"26.3-{sha1[:8]}.json"
    assert platform.sha1(path) == sha1  # the fixture is Mojang's file, byte for byte
    return json.loads(path.read_text(encoding="utf-8"))


def profile() -> dict:
    found = json.loads((FIXTURES / "fabric-loader-0.19.5-26.3.json").read_text(encoding="utf-8"))
    for library in found["libraries"]:
        library.setdefault("sha1", LOADER_SHA1)
    return found


def source(sha1: str) -> dict:
    return {"id": "26.3", "url": PACKAGES.format(sha1=sha1), "sha1": sha1}


def build(sha1: str) -> dict:
    return platform.build_spec("mc-26.3", version_json(sha1), source(sha1), profile(), PROFILE_URL)


def test_the_current_platform_file_loads() -> None:
    assert platform.current_id(REPO_ROOT) == "mc-26.3"
    plat = platform.load(REPO_ROOT)
    assert (plat.id, plat.minecraft, plat.loader) == ("mc-26.3", "26.3", ("fabric", "0.19.5"))
    assert plat.path == REPO_ROOT / "config" / "platforms" / "mc-26.3.json"


def test_every_tier_resolves_through_extends() -> None:
    plat = platform.load(REPO_ROOT)
    assert plat.tiers == ["bench", "played", "debug", "dev", "lod", "jvm"]
    counts = {tier: len(plat.tier_files(tier)) for tier in plat.tiers}
    assert counts == {"bench": 5, "played": 14, "debug": 6, "dev": 6, "lod": 5, "jvm": 8}
    bench = plat.tier_files("bench")
    assert [pinned.file for pinned in bench] == [
        "fabric-api-0.161.0+26.3.jar",
        "sodium-fabric-0.9.2+mc26.3.jar",
        "iris-fabric-1.11.7+mc26.3.jar",
        "Faithful 64x - Release 15.zip",
        "ComplementaryUnbound_r5.9.3.zip",
    ]
    assert [pinned.kind for pinned in bench] == ["mod"] * 3 + ["resourcePack", "referencePack"]
    assert [pinned.game_folder for pinned in bench[2:]] == [
        None,
        "game/resourcepacks",
        "game/shaderpacks",
    ]
    assert plat.chain("dev") == ["bench", "dev"]
    dev = plat.tier_files("dev")
    assert dev[:4] == bench[:4] and dev[5] == bench[4]
    assert (dev[4].slug, dev[4].tier, dev[4].modrinth_version_id) == (
        "viewfinder",
        "dev",
        "udfs9W2z",
    )
    for pinned in plat.tier_files("played"):
        assert len(pinned.sha512) == platform.SHA512_DIGITS
        assert pinned.tier in ("bench", "played", "referencePacks")
    assert plat.pending("lod") == ["voxy: latest 0.2.19-beta targets 26.2 (2026-08-29)"]
    assert plat.pending("bench") == []


def write_platform(root: Path, data: dict, platform_id: str = "mc-fixture") -> None:
    (root / "config" / "platforms").mkdir(parents=True, exist_ok=True)
    (root / "config" / "suite.json").write_text(json.dumps({"platform": platform_id}))
    (root / "config" / "platforms" / f"{platform_id}.json").write_text(json.dumps(data))


def fixture_platform(**tiers: dict) -> dict:
    return {
        "id": "mc-fixture",
        "minecraft": "26.3",
        "loader": {"name": "fabric", "version": "0.19.5"},
        "tiers": tiers,
        "referencePacks": [],
    }


def pin(slug: str, digest: str = "ab" * 64) -> dict:
    return {
        "slug": slug,
        "version": "1",
        "file": f"{slug}.jar",
        "modrinthVersionId": "xxxxxxxx",
        "sha512": digest,
    }


def test_refuses_a_bad_file_tier_or_pin(tmp_path: Path) -> None:
    with pytest.raises(platform.PlatformError, match="config/suite.json names no platform"):
        platform.current_id(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "suite.json").write_text('{"platform": "mc-fixture"}')
    with pytest.raises(
        platform.PlatformError, match="no platform file config/platforms/mc-fixture"
    ):
        platform.load(tmp_path)
    write_platform(tmp_path, {"id": "other"})
    with pytest.raises(platform.PlatformError, match="says id 'other'; fix: make it 'mc-fixture'"):
        platform.load(tmp_path)
    (tmp_path / "config" / "platforms" / "mc-fixture.json").write_text("{not json")
    with pytest.raises(platform.PlatformError, match="is not JSON"):
        platform.load(tmp_path)
    write_platform(
        tmp_path,
        fixture_platform(
            bench={"extends": None, "mods": [pin("a")]},
            loop={"extends": "loop", "mods": []},
            twice={"extends": "bench", "mods": [pin("a")]},
            short={"extends": "bench", "mods": [pin("b", "abc")]},
            blank={"extends": "bench", "mods": [{"slug": "c", "file": "c.jar"}]},
        ),
    )
    plat = platform.load(tmp_path)
    assert [p.file for p in plat.tier_files("bench")] == ["a.jar"]
    with pytest.raises(platform.PlatformError, match="tier 'nope' is not in mc-fixture.json; fix"):
        plat.tier_files("nope")
    with pytest.raises(platform.PlatformError, match="tier 'loop' extends itself"):
        plat.tier_files("loop")
    with pytest.raises(platform.PlatformError, match="lists a file twice: a.jar"):
        plat.tier_files("twice")
    with pytest.raises(platform.PlatformError, match="sha512 is not 128 hex digits"):
        plat.tier_files("short")
    with pytest.raises(
        platform.PlatformError, match="blank mod c in mc-fixture.json has no version"
    ):
        plat.tier_files("blank")


def test_digests(tmp_path: Path) -> None:
    file = tmp_path / "file.bin"
    file.write_bytes(b"optilux" * 300_000)  # over one chunk, so the loop runs twice
    for name, read in (
        ("sha1", platform.sha1),
        ("sha256", platform.sha256),
        ("sha512", platform.sha512),
    ):
        assert read(file) == hashlib.new(name, file.read_bytes()).hexdigest()
        assert platform.digest(file, name) == read(file)


def test_rules_allow_for_windows_x64_without_features() -> None:
    allow = {"action": "allow"}
    assert platform.rules_allow(None) and platform.rules_allow([])
    assert platform.rules_allow([{**allow, "os": {"name": "windows"}}])
    assert not platform.rules_allow([{**allow, "os": {"name": "osx"}}])
    assert not platform.rules_allow([{**allow, "os": {"name": "linux"}}])
    assert not platform.rules_allow([{**allow, "os": {"arch": "x86"}}])
    assert platform.rules_allow([{**allow, "os": {"arch": "x86_64"}}])
    assert not platform.rules_allow([{**allow, "features": {"is_demo_user": True}}])
    assert not platform.rules_allow([{"action": "disallow", "os": {"name": "windows"}}])
    # The last matching rule decides: allowed everywhere, then disallowed on osx only.
    assert platform.rules_allow([allow, {"action": "disallow", "os": {"name": "osx"}}])
    assert not platform.rules_allow([allow, {"action": "disallow", "os": {"name": "windows"}}])


def test_maven_path() -> None:
    assert (
        platform.maven_path("net.fabricmc:fabric-loader:0.19.5")
        == "net/fabricmc/fabric-loader/0.19.5/fabric-loader-0.19.5.jar"
    )
    assert (
        platform.maven_path("com.mojang:jtracy:1.14.38:natives-windows")
        == "com/mojang/jtracy/1.14.38/jtracy-1.14.38-natives-windows.jar"
    )
    with pytest.raises(platform.PlatformError, match="is not group:artifact:version"):
        platform.maven_path("just-a-name")


def test_arguments_from_mojangs_json() -> None:
    version = version_json(NEW)
    jvm = platform.flatten_arguments(version["arguments"]["jvm"])
    assert jvm[0].startswith("-XX:HeapDumpPath=")  # the windows-only rule
    assert "-XstartOnFirstThread" not in jvm and "-Xss1M" not in jvm  # osx, 32-bit
    assert jvm[-2:] == ["-cp", "${classpath}"]
    game = version["arguments"]["game"]
    assert platform.flatten_arguments(game) == platform.flatten_arguments(game)[:20]
    assert "--demo" not in platform.flatten_arguments(game)
    assert platform.feature_arguments(game, "is_quick_play_singleplayer") == [
        "--quickPlaySingleplayer",
        "${quickPlaySingleplayer}",
    ]
    assert platform.feature_arguments(game, "is_demo_user") == ["--demo"]
    with pytest.raises(platform.PlatformError, match="gates no argument on nothing"):
        platform.feature_arguments(game, "nothing")


def test_the_spec_from_the_republished_json_is_the_committed_spec() -> None:
    built = build(NEW)
    committed = (REPO_ROOT / "config" / "platforms" / "mc-26.3.launch.json").read_bytes()
    assert platform.spec_text(built).encode("utf-8") == committed
    assert len(built["classpath"]) == 82 and built["classpath"][-1]["from"] == "mojang:client"
    assert [entry["from"].split(":")[0] for entry in built["classpath"][:8]] == ["fabric"] * 7 + [
        "mojang"
    ]
    assert built["classpath"][6]["sha1"] == LOADER_SHA1
    assert (len(built["jvmOptions"]), len(built["gameArguments"])) == (14, 20)
    assert built["jvmOptions"][-1] == "-DFabricMcEmu= net.minecraft.client.main.Main "
    assert built["mainClass"] == "net.fabricmc.loader.impl.launch.knot.KnotClient"
    assert built["assetIndex"] == {
        "id": "34",
        "sha1": NEW_INDEX,
        "url": PACKAGES.format(sha1=NEW_INDEX).replace("26.3.json", "34.json"),
    }
    assert platform.spec_diff(platform.load_spec(REPO_ROOT, "mc-26.3"), built) == []


def test_mojangs_republished_json_moved_only_the_asset_index() -> None:
    """P6, D20: the refresh of 0.01.02 changed the asset index and the version JSON's sha1."""
    old, new = build(OLD), build(NEW)
    diff = platform.spec_diff(old, new)
    assert [difference.path for difference in diff] == [
        "sources.versionJson.url",
        "sources.versionJson.sha1",
        "assetIndex.sha1",
        "assetIndex.url",
    ]
    assert (diff[1].committed, diff[1].built) == (OLD, NEW)
    assert (diff[2].committed, diff[2].built) == (OLD_INDEX, NEW_INDEX)
    assert diff[2].text() == f'assetIndex.sha1: "{OLD_INDEX}" -> "{NEW_INDEX}"'
    for key in ("classpath", "jvmOptions", "gameArguments", "featureArguments", "logging"):
        assert old[key] == new[key]
    assert (
        version_json(OLD)["assetIndex"]["totalSize"] + 105_275
        == version_json(NEW)["assetIndex"]["totalSize"]
    )


def test_spec_diff_skips_notes_and_names_added_and_removed_facts() -> None:
    old = {"schema": 1, "writtenBy": "spike", "classpath": [{"path": "a.jar", "sha1": "1"}]}
    new = {
        "schema": 1,
        "writtenBy": "install",
        "classpath": [{"path": "a.jar", "sha1": "2"}, {"path": "b.jar", "sha1": "3"}],
    }
    assert [d.path for d in platform.spec_diff(old, new)] == [
        "classpath[0].sha1",
        "classpath[1].path",
        "classpath[1].sha1",
    ]
    assert platform.spec_diff(old, new)[1] == platform.Difference(
        "classpath[1].path", None, "b.jar"
    )
    assert [d.path for d in platform.spec_diff(new, old)] == [
        "classpath[0].sha1",
        "classpath[1].path",
        "classpath[1].sha1",
    ]
    assert platform.spec_diff(new, old)[1].built is None
    assert platform.spec_diff(old, {**old, "writtenBy": "reworded"}) == []
    assert platform.spec_text({"a": [1]}) == '{\n "a": [\n  1\n ]\n}\n'


def test_build_spec_refuses_a_bad_profile() -> None:
    bare = json.loads((FIXTURES / "fabric-loader-0.19.5-26.3.json").read_text(encoding="utf-8"))
    with pytest.raises(platform.PlatformError, match="fabric-loader:0.19.5 carries no sha1; fix"):
        platform.build_spec("mc-26.3", version_json(NEW), source(NEW), bare, PROFILE_URL)
    other = {**profile(), "inheritsFrom": "26.4"}
    with pytest.raises(platform.PlatformError, match="inherits from '26.4', not version '26.3'"):
        platform.build_spec("mc-26.3", version_json(NEW), source(NEW), other, PROFILE_URL)


def test_load_spec(tmp_path: Path) -> None:
    assert platform.load_spec(tmp_path, "mc-fixture") is None
    path = platform.spec_path(tmp_path, "mc-fixture")
    assert path == tmp_path / "config" / "platforms" / "mc-fixture.launch.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken")
    with pytest.raises(platform.PlatformError, match="is not JSON .*; fix: `install --refresh`"):
        platform.load_spec(tmp_path, "mc-fixture")
    path.write_text(platform.spec_text({"schema": 1}))
    assert platform.load_spec(tmp_path, "mc-fixture") == {"schema": 1}
