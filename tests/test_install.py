"""`optilux install` in a throwaway root with the network and minecraft-launcher-lib replaced by a
fake world: the first install writes the store, the copies, Temurin, PresentMon and the launch
spec; a second one re-hashes everything and downloads nothing; a tier adds its files; Mojang
republishing the version JSON makes the spec differ in P6's four facts until --refresh; a hash
that differs from its pin is refused with the file named; game/saves/ and options.txt are never
touched. Nothing here reads runtime/ or the network (docs/workflow.md#testing)."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from optilux import cli, platform
from optilux.verbs import install

PLATFORM = "mc-fixture"
PROFILE_ID = "fabric-loader-0.19.5-26.3"
PROFILE_URL = install.FABRIC_PROFILE.format(game="26.3", loader="0.19.5")
MAVEN = "https://maven.fabricmc.net/"
LOADER = "net.fabricmc:fabric-loader:0.19.5"
ASM = "org.ow2.asm:asm:9.10.1"
JDK_BUILD = "jdk-fixture"
JDK_ARCHIVE = "jdk-fixture.zip"
PRESENTMON = "PresentMon-fixture.exe"


def sha1(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()  # Mojang's file sums


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha512(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def zipped(folder: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{folder}/bin/java.exe", b"MZ fake java")
        archive.writestr(f"{folder}/release", b"JAVA_VERSION=fixture\n")
    return buffer.getvalue()


class World:
    """The fake network and the files the fake minecraft-launcher-lib writes: one Fabric library
    with a sha1 and one (fabric-loader) without, one Mojang library allowed on Windows and one
    osx-only, the client jar, two assets, the log config; three Modrinth files, a JDK zip and a
    PresentMon. `republish` moves the asset index as Mojang did on 2026-10-06 (P6)."""

    def __init__(self) -> None:
        self.jars = {
            f"libraries/{platform.maven_path(ASM)}": b"asm jar",
            f"libraries/{platform.maven_path(LOADER)}": b"loader jar",
            "libraries/at/yawk/lz4/lz4-java/1.10.1/lz4-java-1.10.1.jar": b"lz4 jar",
            "versions/26.3/26.3.jar": b"client jar",
        }
        self.osx_jar = b"osx only jar"
        self.assets = {"minecraft/one.png": b"asset one", "minecraft/two.ogg": b"asset two"}
        self.log = b"<Configuration/>\n"
        self.modrinth = {
            "AAAAAAAA": ("mod-a.jar", b"mod a jar"),
            "BBBBBBBB": ("mod-b.jar", b"mod b jar"),
            "PPPPPPPP": ("Pack 1.zip", b"PK resource pack"),
            "RRRRRRRR": ("Ref.zip", b"PK shader pack"),
        }
        self.jdk = zipped(JDK_BUILD)
        self.presentmon = b"MZ fake presentmon"
        self.profile = {
            "id": PROFILE_ID,
            "inheritsFrom": "26.3",
            "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
            "arguments": {"game": [], "jvm": ["-DFabricMcEmu= net.minecraft.client.main.Main "]},
            "libraries": [
                {"name": ASM, "url": MAVEN, "sha1": sha1(b"asm jar")},
                {"name": LOADER, "url": MAVEN},
            ],
        }
        self.profile_bytes = json.dumps(self.profile).encode()
        self.downloads: list[str] = []
        self.lib_calls: list[tuple[str, Path]] = []
        # A Modrinth listing that reports another sha512 than the served file's (a lie).
        self.listed_sha512: dict[str, str] = {}
        self.publish()

    def publish(self) -> None:
        """Mojang's version JSON and asset index from the current assets."""
        objects = {
            name: {"hash": sha1(data), "size": len(data)} for name, data in self.assets.items()
        }
        self.index_bytes = json.dumps({"objects": objects}).encode()
        index_sha1 = sha1(self.index_bytes)
        lz4 = "at/yawk/lz4/lz4-java/1.10.1/lz4-java-1.10.1.jar"
        self.version = {
            "id": "26.3",
            "type": "release",
            "mainClass": "net.minecraft.client.main.Main",
            "assetIndex": {
                "id": "34",
                "sha1": index_sha1,
                "url": f"https://piston-meta.test/{index_sha1}/34.json",
                "totalSize": sum(len(data) for data in self.assets.values()),
            },
            "downloads": {"client": {"sha1": sha1(b"client jar"), "url": "https://piston.test/c"}},
            "libraries": [
                {
                    "name": "at.yawk.lz4:lz4-java:1.10.1",
                    "downloads": {"artifact": {"path": lz4, "sha1": sha1(b"lz4 jar"), "url": "u"}},
                },
                {
                    "name": "ca.weblite:java-objc-bridge:1.1",
                    "downloads": {"artifact": {"path": "ca/objc.jar", "sha1": sha1(self.osx_jar)}},
                    "rules": [{"action": "allow", "os": {"name": "osx"}}],
                },
            ],
            "logging": {
                "client": {
                    "argument": "-Dlog4j.configurationFile=${path}",
                    "file": {"id": "client.xml", "sha1": sha1(self.log), "url": "u"},
                }
            },
            "arguments": {
                "jvm": [
                    {"rules": [{"action": "allow", "os": {"name": "osx"}}], "value": ["-Xosx"]},
                    "-cp",
                    "${classpath}",
                ],
                "game": [
                    "--username",
                    "${auth_player_name}",
                    {
                        "rules": [{"action": "allow", "features": {"has_custom_resolution": True}}],
                        "value": ["--width", "${resolution_width}"],
                    },
                    {
                        "rules": [
                            {"action": "allow", "features": {"is_quick_play_singleplayer": True}}
                        ],
                        "value": ["--quickPlaySingleplayer", "${quickPlaySingleplayer}"],
                    },
                ],
            },
            "javaVersion": {"component": "java-runtime-epsilon", "majorVersion": 25},
        }
        self.version_bytes = json.dumps(self.version).encode()
        self.version_sha1 = sha1(self.version_bytes)
        self.version_url = f"https://piston-meta.test/{self.version_sha1}/26.3.json"

    def republish(self) -> None:
        self.assets["minecraft/three.json"] = b"a third asset"
        self.publish()

    # The fake network.

    def fetch(self, url: str) -> bytes:
        if url == install.MANIFEST:
            entry = {"id": "26.3", "url": self.version_url, "sha1": self.version_sha1}
            return json.dumps(
                {"versions": [{"id": "26.4", "url": "x", "sha1": "y"}, entry]}
            ).encode()
        if url == PROFILE_URL:
            return self.profile_bytes
        if url == f"{MAVEN}{platform.maven_path(LOADER)}.sha1":
            return (sha1(b"loader jar") + "\n").encode()
        for version_id, (name, data) in self.modrinth.items():
            if url == install.MODRINTH_VERSION.format(id=version_id):
                files = [
                    {
                        "filename": name,
                        "url": f"https://cdn.test/{version_id}",
                        "hashes": {"sha512": self.listed_sha512.get(version_id, sha512(data))},
                    }
                ]
                return json.dumps({"files": files}).encode()
        if url.startswith("https://api.adoptium.net/"):
            assert "jdk-fixture" in url
            package = {
                "name": JDK_ARCHIVE,
                "link": "https://github.test/jdk.zip",
                "checksum": sha256(self.jdk),
            }
            return json.dumps({"binaries": [{"package": package}]}).encode()
        raise AssertionError(f"unexpected fetch of {url}")

    def download(self, url: str, dest: Path) -> int:
        self.downloads.append(url)
        if url == self.version_url:
            data = self.version_bytes
        elif url == "https://github.test/jdk.zip":
            data = self.jdk
        elif url == "https://github.test/presentmon.exe":
            data = self.presentmon
        else:
            version_id = url.rsplit("/", 1)[-1]
            assert url.startswith("https://cdn.test/"), f"unexpected download of {url}"
            data = self.modrinth[version_id][1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return len(data)

    def install_minecraft_version(self, version: str, directory: Path, callback: dict) -> None:
        """Like the lib: reads the local JSONs, writes a sha1-carrying file when it is missing or
        differs, a Fabric library (no sha1 in its download) only when missing."""
        self.lib_calls.append((version, Path(directory)))
        assert version == PROFILE_ID
        local = json.loads((directory / "versions" / version / f"{version}.json").read_bytes())
        assert local == self.profile
        parent = directory / "versions" / "26.3" / "26.3.json"
        assert sha1(parent.read_bytes()) == self.version_sha1
        status = callback["setStatus"]
        status("Download Libraries")
        for relative, data in self.jars.items():
            path = directory / relative
            fabric = relative.split("/")[1] in ("org", "net")
            if path.is_file() and (fabric or path.read_bytes() == data):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            status(f"Download {path.name}")
        status("Download Assets")
        objects = [(directory / "assets" / "indexes" / "34.json", self.index_bytes)]
        objects += [
            (directory / "assets" / "objects" / sha1(data)[:2] / sha1(data), data)
            for data in self.assets.values()
        ]
        objects.append((directory / "assets" / "log_configs" / "client.xml", self.log))
        for path, data in objects:
            if path.is_file() and path.read_bytes() == data:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            status(f"Download {path.name}")
        status("Installation complete")


def write_config(root: Path, world: World) -> None:
    config = root / "config"
    (config / "platforms").mkdir(parents=True)
    (config / "java").mkdir()
    (config / "suite.json").write_text(json.dumps({"platform": PLATFORM}))

    def pin(version_id: str, slug: str) -> dict:
        name, data = world.modrinth[version_id]
        return {
            "slug": slug,
            "version": "1",
            "file": name,
            "modrinthVersionId": version_id,
            "sha512": sha512(data),
        }

    data = {
        "id": PLATFORM,
        "minecraft": "26.3",
        "loader": {"name": "fabric", "version": "0.19.5"},
        "tiers": {
            "bench": {
                "extends": None,
                "mods": [pin("AAAAAAAA", "mod-a")],
                "resourcePacks": [pin("PPPPPPPP", "pack")],
            },
            "dev": {"extends": "bench", "mods": [pin("BBBBBBBB", "mod-b")]},
            "lod": {"extends": "bench", "mods": [{"slug": "voxy", "status": "pending"}]},
        },
        "referencePacks": [pin("RRRRRRRR", "ref")],
    }
    (config / "platforms" / f"{PLATFORM}.json").write_text(json.dumps(data))
    java = {
        "runtime": {"build": JDK_BUILD, "archive": JDK_ARCHIVE, "archiveSha256": sha256(world.jdk)}
    }
    (config / "java" / "bench.json").write_text(json.dumps(java))
    tools = {
        "schema": 1,
        "presentmon": {
            "file": PRESENTMON,
            "sha256": sha256(world.presentmon),
            "source": "https://github.test/presentmon.exe",
        },
    }
    (config / "tools.json").write_text(json.dumps(tools))


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """A fake world wired into optilux.verbs.install, with the root's config written and the
    game folder holding a world and options the harness must never touch."""
    found = World()
    monkeypatch.setattr(install, "fetch", found.fetch)
    monkeypatch.setattr(install, "download", found.download)
    monkeypatch.setattr(install, "install_minecraft_version", found.install_minecraft_version)
    monkeypatch.setattr(install, "REPO_ROOT", tmp_path)
    write_config(tmp_path, found)
    game = tmp_path / "runtime" / PLATFORM / "game"
    (game / "saves" / "spike").mkdir(parents=True)
    (game / "saves" / "spike" / "level.dat").write_bytes(b"level")
    (game / "options.txt").write_bytes(b"version:5023\n")
    return found


def untouched(root: Path) -> tuple[bytes, bytes]:
    game = root / "runtime" / PLATFORM / "game"
    return (game / "saves" / "spike" / "level.dat").read_bytes(), (
        game / "options.txt"
    ).read_bytes()


def quiet(text: str) -> None:
    pass


def test_the_first_install_writes_everything(tmp_path: Path, world: World) -> None:
    said: list[str] = []
    outcome = install.install(tmp_path, "bench", False, said.append)
    assert outcome.ok and (outcome.platform, outcome.tier) == (PLATFORM, "bench")
    # The version JSON, 4 jars (the osx one excluded), the index, 2 assets, the log; 3 store
    # files; the archive; the tool. Fresh copies are written, not hashed.
    assert outcome.hashes == 1 + 4 + 1 + 2 + 1 + 3 + 1 + 1
    assert outcome.downloaded == 1 + 8 + 3 + 1 + 1  # the lib fetched 4 jars, index, 2 assets, log
    assert outcome.minecraft == {
        "version": "26.3",
        "profile": PROFILE_ID,
        "directory": f"runtime/{PLATFORM}",
        "jars": 4,
        "assetIndex": "34",
        "assets": 2,
    }
    store = tmp_path / "runtime" / PLATFORM / "files"
    assert sorted(p.name for p in store.iterdir()) == ["Pack 1.zip", "Ref.zip", "mod-a.jar"]
    assert (store / "mod-a.jar").read_bytes() == b"mod a jar"
    game = tmp_path / "runtime" / PLATFORM / "game"
    assert (game / "resourcepacks" / "Pack 1.zip").read_bytes() == b"PK resource pack"
    assert (game / "shaderpacks" / "Ref.zip").read_bytes() == b"PK shader pack"
    assert not (game / "mods").exists()  # mods are placed by launch (0.01.03)
    assert [(f["file"], f["state"], f["copyState"]) for f in outcome.files] == [
        ("mod-a.jar", "downloaded", None),
        ("Pack 1.zip", "downloaded", "copied"),
        ("Ref.zip", "downloaded", "copied"),
    ]
    assert outcome.files[1]["copy"] == f"runtime/{PLATFORM}/game/resourcepacks/Pack 1.zip"
    assert (tmp_path / "runtime" / "java" / JDK_ARCHIVE).read_bytes() == world.jdk
    assert (
        tmp_path / "runtime" / "java" / JDK_BUILD / "bin" / "java.exe"
    ).read_bytes() == b"MZ fake java"
    assert outcome.java == {
        "build": JDK_BUILD,
        "archive": JDK_ARCHIVE,
        "home": f"runtime/java/{JDK_BUILD}",
        "unpacked": "unpacked",
    }
    assert (tmp_path / "runtime" / "tools" / PRESENTMON).read_bytes() == world.presentmon
    assert outcome.tools == [{"tool": "presentmon", "file": PRESENTMON, "state": "downloaded"}]
    spec_file = tmp_path / "config" / "platforms" / f"{PLATFORM}.launch.json"
    assert outcome.spec == {
        "path": f"config/platforms/{PLATFORM}.launch.json",
        "state": "written",
        "diff": [],
    }
    spec = json.loads(spec_file.read_bytes())
    assert spec["sources"]["versionJson"] == {
        "id": "26.3",
        "url": world.version_url,
        "sha1": world.version_sha1,
    }
    assert [entry["path"] for entry in spec["classpath"]] == list(world.jars)
    assert spec["classpath"][1]["sha1"] == sha1(b"loader jar")  # from Maven's .sha1 file
    assert spec["jvmOptions"] == [
        "-cp",
        "${classpath}",
        "-DFabricMcEmu= net.minecraft.client.main.Main ",
    ]
    assert spec["featureArguments"]["has_custom_resolution"] == ["--width", "${resolution_width}"]
    assert spec_file.read_bytes() == platform.spec_text(spec).encode()
    # The profile was written for the lib before it ran, and the lib ran once for the profile.
    assert world.lib_calls == [(PROFILE_ID, tmp_path / "runtime" / PLATFORM)]
    assert said[:2] == [
        "minecraft: fetching the version JSON of 26.3 (" + world.version_sha1[:8] + ")",
        f"minecraft: installing 26.3 and {PROFILE_ID} into runtime/{PLATFORM}",
    ]
    assert said[2:] == [
        "files: fetching mod-a.jar from Modrinth (AAAAAAAA)",
        "files: fetching Pack 1.zip from Modrinth (PPPPPPPP)",
        "files: fetching Ref.zip from Modrinth (RRRRRRRR)",
        f"java: fetching {JDK_ARCHIVE} from the Adoptium API",
        f"java: unpacking {JDK_ARCHIVE} into runtime/java/{JDK_BUILD}",
        f"tools: fetching {PRESENTMON}",
    ]
    assert untouched(tmp_path) == (b"level", b"version:5023\n")


def test_a_second_install_rehashes_everything_and_downloads_nothing(
    tmp_path: Path, world: World
) -> None:
    install.install(tmp_path, "bench", False, quiet)
    world.downloads.clear()
    said: list[str] = []
    outcome = install.install(tmp_path, "bench", False, said.append)
    assert outcome.ok and outcome.downloaded == 0 and world.downloads == []
    assert outcome.hashes == 1 + 4 + 1 + 2 + 1 + 3 + 2 + 1 + 1  # the two copies hashed too
    assert {f["state"] for f in outcome.files} == {"equal"}
    assert {f["copyState"] for f in outcome.files if f["copy"]} == {"equal"}
    assert outcome.java["unpacked"] == "present" and outcome.tools[0]["state"] == "equal"
    assert outcome.spec["state"] == "equal" and outcome.spec["diff"] == []
    assert said == [f"minecraft: installing 26.3 and {PROFILE_ID} into runtime/{PLATFORM}"]
    # A differing game copy is replaced from the store, a missing one re-copied.
    game = tmp_path / "runtime" / PLATFORM / "game"
    (game / "resourcepacks" / "Pack 1.zip").write_bytes(b"edited")
    (game / "shaderpacks" / "Ref.zip").unlink()
    outcome = install.install(tmp_path, "bench", False, quiet)
    assert [f["copyState"] for f in outcome.files if f["copy"]] == ["copied", "copied"]
    assert (game / "resourcepacks" / "Pack 1.zip").read_bytes() == b"PK resource pack"
    assert untouched(tmp_path) == (b"level", b"version:5023\n")


def test_a_tier_adds_its_files_and_reports_pending_mods(tmp_path: Path, world: World) -> None:
    outcome = install.install(tmp_path, "dev", False, quiet)
    assert [f["file"] for f in outcome.files] == ["mod-a.jar", "Pack 1.zip", "mod-b.jar", "Ref.zip"]
    assert outcome.files[2]["tier"] == "dev" and outcome.pending == []
    assert (tmp_path / "runtime" / PLATFORM / "files" / "mod-b.jar").read_bytes() == b"mod b jar"
    outcome = install.install(tmp_path, "lod", False, quiet)
    assert [f["file"] for f in outcome.files] == ["mod-a.jar", "Pack 1.zip", "Ref.zip"]
    assert outcome.pending == ["voxy: pending"]
    with pytest.raises(
        install.InstallError,
        match=r"no tier 'nope' in mc-fixture.json; fix: one of bench, dev, lod",
    ):
        install.install(tmp_path, "nope", False, quiet)


def test_a_republished_version_json_differs_until_refresh(tmp_path: Path, world: World) -> None:
    """P6 and D20: Mojang moved the asset index; the spec differs in four facts, exits 1, and
    --refresh rewrites it."""
    install.install(tmp_path, "bench", False, quiet)
    spec_file = tmp_path / "config" / "platforms" / f"{PLATFORM}.launch.json"
    before = spec_file.read_bytes()
    old_sha1, old_index = world.version_sha1, world.version["assetIndex"]["sha1"]
    world.republish()
    assert world.version_sha1 != old_sha1
    outcome = install.install(tmp_path, "bench", False, quiet)
    assert not outcome.ok and outcome.spec["state"] == "differs"
    assert [d["path"] for d in outcome.spec["diff"]] == [
        "sources.versionJson.url",
        "sources.versionJson.sha1",
        "assetIndex.sha1",
        "assetIndex.url",
    ]
    assert outcome.spec["diff"][1] == {
        "path": "sources.versionJson.sha1",
        "committed": old_sha1,
        "built": world.version_sha1,
    }
    assert outcome.spec["diff"][2]["committed"] == old_index
    assert spec_file.read_bytes() == before  # nothing rewritten without --refresh
    assert (
        outcome.minecraft["assets"] == 3 and outcome.downloaded == 1 + 2
    )  # the JSON, the index, the asset
    outcome = install.install(tmp_path, "bench", True, quiet)
    assert outcome.ok and outcome.spec["state"] == "refreshed" and len(outcome.spec["diff"]) == 4
    assert spec_file.read_bytes() != before
    assert (
        json.loads(spec_file.read_bytes())["assetIndex"]["sha1"]
        == world.version["assetIndex"]["sha1"]
    )
    outcome = install.install(tmp_path, "bench", True, quiet)
    assert outcome.spec["state"] == "equal"
    assert untouched(tmp_path) == (b"level", b"version:5023\n")


def test_a_hash_that_differs_from_its_pin_is_refused(tmp_path: Path, world: World) -> None:
    install.install(tmp_path, "bench", False, quiet)
    base = tmp_path / "runtime" / PLATFORM
    # A Fabric library the lib never checks: install's own pass does.
    asm = base / "libraries" / platform.maven_path(ASM)
    asm.write_bytes(b"tampered")
    with pytest.raises(install.InstallError) as caught:
        install.install(tmp_path, "bench", False, quiet)
    assert str(caught.value).startswith(
        f"classpath jar runtime/{PLATFORM}/libraries/org/ow2/asm/asm/9.10.1/asm-9.10.1.jar: sha1 "
    )
    assert "differs from its pin " + sha1(b"asm jar") in str(caught.value)
    assert str(caught.value).endswith(f"; fix: {install.MISMATCH_FIX}")
    asm.write_bytes(b"asm jar")
    # A store file.
    (base / "files" / "mod-a.jar").write_bytes(b"not the pinned jar")
    with pytest.raises(
        install.InstallError, match=f"mod runtime/{PLATFORM}/files/mod-a.jar: sha512 .* differs"
    ):
        install.install(tmp_path, "bench", False, quiet)
    (base / "files" / "mod-a.jar").unlink()
    # Modrinth listing another hash than the pin: refused before any download.
    world.listed_sha512["AAAAAAAA"] = sha512(b"other")
    with pytest.raises(
        install.InstallError,
        match=r"Modrinth lists mod-a.jar with sha512 .* and the platform file pins",
    ):
        install.install(tmp_path, "bench", False, quiet)
    # Modrinth listing the pin but serving other bytes: refused, nothing left in the store.
    world.listed_sha512["AAAAAAAA"] = sha512(b"mod a jar")
    world.modrinth["AAAAAAAA"] = ("mod-a.jar", b"served wrong")
    with pytest.raises(install.InstallError, match=r"mod runtime/.*/files/mod-a.jar: sha512"):
        install.install(tmp_path, "bench", False, quiet)
    assert not (base / "files" / "mod-a.jar").exists()
    world.listed_sha512.clear()
    world.modrinth["AAAAAAAA"] = ("mod-a.jar", b"mod a jar")
    # A file still missing after the lib ran (here: a lib that did nothing): named, the rerun
    # as the fix; the restored lib then heals it.
    install.install_minecraft_version = lambda version, directory, callback: None
    asset = base / "assets" / "objects" / sha1(b"asset one")[:2] / sha1(b"asset one")
    asset.unlink()
    with pytest.raises(
        install.InstallError, match=r"asset runtime/.*/assets/objects/.* is missing"
    ):
        install.install(tmp_path, "bench", False, quiet)
    install.install_minecraft_version = world.install_minecraft_version
    assert install.install(tmp_path, "bench", False, quiet).ok and asset.is_file()


def test_java_and_tool_pins_are_checked(tmp_path: Path, world: World) -> None:
    install.install(tmp_path, "bench", False, quiet)
    archive = tmp_path / "runtime" / "java" / JDK_ARCHIVE
    archive.write_bytes(b"not the archive")
    with pytest.raises(
        install.InstallError, match=f"java archive runtime/java/{JDK_ARCHIVE}: sha256 .* differs"
    ):
        install.install(tmp_path, "bench", False, quiet)
    archive.unlink()
    world.jdk = zipped("other-folder")  # Adoptium now lists a checksum the pin does not match
    with pytest.raises(
        install.InstallError,
        match=r"Adoptium lists jdk-fixture.zip with sha256 .* and bench.json pins",
    ):
        install.install(tmp_path, "bench", False, quiet)
    world.jdk = zipped(JDK_BUILD)
    tool = tmp_path / "runtime" / "tools" / PRESENTMON
    tool.write_bytes(b"tampered")
    with pytest.raises(
        install.InstallError, match=f"tool presentmon runtime/tools/{PRESENTMON}: sha256 .* differs"
    ):
        install.install(tmp_path, "bench", False, quiet)
    tool.unlink()
    world.presentmon = b"served wrong"
    with pytest.raises(install.InstallError, match=r"tool presentmon runtime/tools/.*: sha256"):
        install.install(tmp_path, "bench", False, quiet)
    assert not tool.exists()


def test_an_archive_with_another_top_folder_is_refused(tmp_path: Path, world: World) -> None:
    world.jdk = zipped("elsewhere")
    (tmp_path / "config" / "java" / "bench.json").write_text(
        json.dumps(
            {
                "runtime": {
                    "build": JDK_BUILD,
                    "archive": JDK_ARCHIVE,
                    "archiveSha256": sha256(world.jdk),
                }
            }
        )
    )
    with pytest.raises(
        install.InstallError, match=r"jdk-fixture.zip unpacks to elsewhere, not jdk-fixture; fix"
    ):
        install.install(tmp_path, "bench", False, quiet)


def test_cli_text_json_and_exit_codes(
    tmp_path: Path, world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["install"]) == 0
    out, err = capsys.readouterr()
    assert err == ""
    lines = out.splitlines()
    assert lines[0] == f"minecraft: fetching the version JSON of 26.3 ({world.version_sha1[:8]})"
    assert (
        f"minecraft: 26.3 and {PROFILE_ID} in runtime/{PLATFORM}/: 4 jars, asset index 34, "
        "2 assets and the log config sha1-equal"
    ) in lines
    assert (
        "files (bench): 3 sha512-equal in the store: mod-a.jar (downloaded), "
        "Pack 1.zip (downloaded), Ref.zip (downloaded)"
    ) in lines
    assert (
        f"copies: runtime/{PLATFORM}/game/resourcepacks/Pack 1.zip (copied); "
        f"runtime/{PLATFORM}/game/shaderpacks/Ref.zip (copied)"
    ) in lines
    assert (
        f"java: {JDK_BUILD}: {JDK_ARCHIVE} sha256-equal, unpacked at runtime/java/{JDK_BUILD}"
        in lines
    )
    assert f"tools: {PRESENTMON} sha256-equal (downloaded)" in lines
    assert (
        f"launch spec: written to config/platforms/{PLATFORM}.launch.json (the first install)"
        in lines
    )
    assert lines[-1] == "optilux install: ok; 14 hashes checked, 14 files downloaded"
    assert cli.main(["install", "--tier", "lod", "--json"]) == 0
    out, err = capsys.readouterr()
    found = json.loads(out)
    assert found["ok"] is True and found["tier"] == "lod" and found["pending"] == ["voxy: pending"]
    assert found["spec"]["state"] == "equal" and found["problem"] is None and err == ""
    world.republish()
    assert cli.main(["install"]) == 1
    out, err = capsys.readouterr()
    assert "launch spec: differs from config/platforms/mc-fixture.launch.json in 4 facts:" in out
    assert out.count("\n  ") == 4 and '  assetIndex.sha1: "' in out
    assert err == (
        "optilux install: the launch spec moved; 17 hashes checked, 3 files downloaded; "
        f"fix: {install.REFRESH_FIX}\n"
    )
    assert cli.main(["install", "--json"]) == 1
    out, err = capsys.readouterr()
    assert json.loads(out)["spec"]["state"] == "differs" and json.loads(out)["ok"] is False
    assert cli.main(["install", "--refresh"]) == 0
    out, err = capsys.readouterr()
    assert "launch spec: refreshed config/platforms/mc-fixture.launch.json (4 facts changed)" in out
    assert cli.main(["install", "--tier", "nope"]) == 1
    out, err = capsys.readouterr()
    assert (
        err == "optilux install: no tier 'nope' in mc-fixture.json; fix: one of bench, dev, lod\n"
    )
    assert cli.main(["install", "--tier", "nope", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "problem": "no tier 'nope' in mc-fixture.json; fix: one of bench, dev, lod",
    }
    assert "install" in [verb.name for verb in cli.VERBS]
    assert untouched(tmp_path) == (b"level", b"version:5023\n")


def test_shown_and_the_lib_version_pin() -> None:
    assert install.shown(Path("C:/elsewhere/x.jar"), Path("C:/repo")) == "C:/elsewhere/x.jar"
    assert install.shown(Path("C:/repo/runtime/a"), Path("C:/repo")) == "runtime/a"
    import minecraft_launcher_lib.utils

    assert minecraft_launcher_lib.utils.get_library_version() == "8.0"  # docs/plans/m1.md P20


def test_a_name_from_the_network_or_a_config_stays_under_runtime(
    tmp_path: Path, world: World
) -> None:
    """Fabric's profile id and a tools.json file name are joined under runtime/: a separator or
    `..` in either is refused before anything is written there."""
    world.profile_bytes = json.dumps({**world.profile, "id": "../escaped"}).encode()
    with pytest.raises(install.InstallError, match=r"names id '../escaped'"):
        install.install(tmp_path, "bench", False, quiet)
    assert not (tmp_path / "runtime" / "mc-fixture" / "escaped").exists()
    world.profile_bytes = json.dumps(world.profile).encode()
    tools = tmp_path / "config" / "tools.json"
    pins = json.loads(tools.read_text(encoding="utf-8"))
    pins["presentmon"]["file"] = "../PresentMon.exe"
    tools.write_text(json.dumps(pins), encoding="utf-8")
    with pytest.raises(install.InstallError, match="no plain file name"):
        install.install(tmp_path, "bench", False, quiet)
