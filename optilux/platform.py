"""The platform file, its tiers, the file hashes and the launch spec (docs/platform.md).

config/platforms/<id>.json pins everything that changes with the Minecraft version: the loader,
the mod tiers (each a list of Modrinth files with their sha512, extending another tier) and the
reference packs. `install` fills runtime/<id>/ from it and builds the launch spec,
config/platforms/<id>.launch.json, from Mojang's version JSON and Fabric's profile JSON alone; the
spec's hash is run identity (docs/run-record.md#identity), so `build_spec` is deterministic and
pure, and `spec_diff` names every fact that moved.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PLATFORMS = "config/platforms"
# config/suite.json names the one platform in use (AGENTS.md: one platform at a time).
SUITE = "config/suite.json"
SPEC = "{id}.launch.json"
# Hash digests are read in 1 MiB chunks: the client jar is 41 MB and the JDK archive 141 MB, so
# read_bytes() would hold them whole for nothing.
CHUNK = 1 << 20
# The tier lists that pin files, with the kind recorded on each file and the game folder a copy
# of that kind goes to (None: mods are placed by `launch` per tier, docs/platform.md#mod-tiers).
LISTS = {"mods": "mod", "resourcePacks": "resourcePack"}
REFERENCE_PACKS = "referencePacks"
GAME_FOLDERS = {"resourcePack": "game/resourcepacks", "referencePack": "game/shaderpacks"}
# Modrinth publishes sha512 and the platform file pins it (pinSource); 128 hex digits.
SHA512_DIGITS = 128

# The launch spec (docs/platform.md#install-and-launch). The three note keys are documentation:
# `spec_diff` compares every other key, so a changed fact is caught and a reworded note is not.
SPEC_SCHEMA = 1
NOTE_KEYS = ("writtenBy", "classpathRule", "gameArgumentsNote")
WRITTEN_BY = (
    "optilux install from Mojang's and Fabric's JSON; install --refresh rewrites it "
    "(platform.md#install-and-launch)"
)
CLASSPATH_RULE = (
    "paths relative to runtime/{id}/; order: Fabric profile libraries, then Mojang libraries "
    "allowed on Windows x64, then the client jar"
)
GAME_ARGUMENTS_NOTE = (
    "template with Mojang placeholders; feature-gated arguments (demo, resolution, quickPlay) "
    "are listed separately"
)
# The feature-gated game arguments the harness uses, in the spec's order: quickPlay joins the
# world, the resolution is written for the display (docs/platform.md#install-and-launch).
FEATURES = ("is_quick_play_singleplayer", "has_custom_resolution")
# Mojang's rules are evaluated for the one bench machine, never for the host running `install`:
# Windows x64, no launcher feature (docs/platform.md#install-and-launch, classpathRule).
OS_NAME = "windows"
OS_ARCHES = {"x86_64", "x64"}
# Fabric's profile lists libraries by Maven coordinates with no download path.
FABRIC, MOJANG, CLIENT = "fabric", "mojang", "client"


class PlatformError(RuntimeError):
    """A platform file, tier or spec input that cannot be used; the message names the fix."""


@dataclass(frozen=True)
class Pinned:
    """One pinned file: a mod, resource pack or reference pack with its Modrinth version and
    sha512, and the tier (or `referencePacks`) that lists it."""

    slug: str
    version: str
    file: str
    kind: str
    modrinth_version_id: str
    sha512: str
    tier: str

    @property
    def game_folder(self) -> str | None:
        """The folder under runtime/<id>/ a copy goes to; None for a mod."""
        return GAME_FOLDERS.get(self.kind)


@dataclass(frozen=True)
class Platform:
    """A loaded platform file."""

    id: str
    path: Path
    data: dict

    @property
    def minecraft(self) -> str:
        return self.data["minecraft"]

    @property
    def loader(self) -> tuple[str, str]:
        """(name, version) of the mod loader."""
        return self.data["loader"]["name"], self.data["loader"]["version"]

    @property
    def tiers(self) -> list[str]:
        return list(self.data["tiers"])

    def chain(self, tier: str) -> list[str]:
        """The tiers a tier is made of, the root (bench) first."""
        found: list[str] = []
        name: str | None = tier
        while name is not None:
            if name not in self.data["tiers"]:
                fix = f"one of {', '.join(self.tiers)}"
                raise PlatformError(f"tier {name!r} is not in {self.path.name}; fix: {fix}")
            if name in found:
                raise PlatformError(f"tier {name!r} extends itself in {self.path.name}; fix: cut")
            found.append(name)
            name = self.data["tiers"][name].get("extends")
        found.reverse()
        return found

    def tier_files(self, tier: str) -> list[Pinned]:
        """Every pinned file a tier needs: its chain's mods and resource packs, then the reference
        packs; PlatformError on a malformed pin or a file name listed twice."""
        files = [
            self._pinned(entry, kind, name)
            for name in self.chain(tier)
            for key, kind in LISTS.items()
            for entry in self.data["tiers"][name].get(key, [])
            if "file" in entry
        ]
        files += [
            self._pinned(entry, "referencePack", REFERENCE_PACKS)
            for entry in self.data.get(REFERENCE_PACKS, [])
        ]
        names = [pinned.file for pinned in files]
        twice = sorted({name for name in names if names.count(name) > 1})
        if twice:
            raise PlatformError(
                f"tier {tier!r} lists a file twice: {', '.join(twice)}; fix: pin it once"
            )
        return files

    def pending(self, tier: str) -> list[str]:
        """The mods of a tier's chain pinned without a file (no build for this version yet)."""
        return [
            f"{entry['slug']}: {entry.get('why', entry.get('status', ''))}"
            for name in self.chain(tier)
            for entry in self.data["tiers"][name].get("mods", [])
            if "file" not in entry
        ]

    def _pinned(self, entry: dict, kind: str, tier: str) -> Pinned:
        where = f"{tier} {kind} {entry.get('slug', '?')} in {self.path.name}"
        for key in ("slug", "version", "file", "modrinthVersionId", "sha512"):
            if not entry.get(key):
                raise PlatformError(f"{where} has no {key}; fix: pin it from Modrinth")
        if not plain_name(entry["file"]):
            raise PlatformError(
                f"{where}: file {entry['file']!r} is not a plain file name; fix: name the file "
                "alone (it is joined under runtime/)"
            )
        digest = entry["sha512"]
        if len(digest) != SHA512_DIGITS or any(ch not in "0123456789abcdef" for ch in digest):
            raise PlatformError(f"{where}: sha512 is not {SHA512_DIGITS} hex digits; fix: re-pin")
        return Pinned(
            slug=entry["slug"],
            version=entry["version"],
            file=entry["file"],
            kind=kind,
            modrinth_version_id=entry["modrinthVersionId"],
            sha512=digest,
            tier=tier,
        )


def plain_name(name: str) -> bool:
    """One path part that stays where it is joined: no separator, not . or .."""
    return name not in ("", ".", "..") and "/" not in name and "\\" not in name


def current_id(root: Path) -> str:
    """The platform in use, config/suite.json's `platform`."""
    suite = root / SUITE
    try:
        return json.loads(suite.read_text(encoding="utf-8"))["platform"]
    except (OSError, ValueError, KeyError) as error:
        raise PlatformError(
            f"{SUITE} names no platform ({error}); fix: set its `platform`"
        ) from None


def load(root: Path, platform_id: str | None = None) -> Platform:
    """The platform file of `platform_id` (default: suite.json's); PlatformError when it is
    missing or not JSON."""
    platform_id = platform_id or current_id(root)
    path = root / PLATFORMS / f"{platform_id}.json"
    name = f"{PLATFORMS}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise PlatformError(f"no platform file {name}; fix: add it (platform.md)") from None
    except ValueError as error:
        raise PlatformError(f"{name} is not JSON ({error}); fix: repair it") from None
    if data.get("id") != platform_id:
        raise PlatformError(f"{path.name} says id {data.get('id')!r}; fix: make it {platform_id!r}")
    return Platform(platform_id, path, data)


def digest(path: Path, algorithm: str) -> str:
    """The hex digest of a file under `algorithm` (sha1, sha256, sha512), read in chunks."""
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha512(path: Path) -> str:
    return digest(path, "sha512")


def sha1(path: Path) -> str:
    return digest(path, "sha1")


def sha256(path: Path) -> str:
    return digest(path, "sha256")


# The launch spec.


def rules_allow(rules: list[dict] | None) -> bool:
    """Mojang's rule list for the bench machine (Windows x64, no feature): the last matching rule
    decides; no rule at all allows. A rule on an os.name other than windows, an arch other than
    x64 (`x86` gates -Xss1M for 32-bit JVMs) or any feature never matches."""
    if not rules:
        return True
    allowed = False
    for rule in rules:
        os_rule = rule.get("os", {})
        if "name" in os_rule and os_rule["name"] != OS_NAME:
            continue
        if "arch" in os_rule and os_rule["arch"] not in OS_ARCHES:
            continue
        if "features" in rule:
            continue
        allowed = rule["action"] == "allow"
    return allowed


def maven_path(name: str) -> str:
    """A Maven coordinate's path: group:artifact:version[:classifier] ->
    group/parts/artifact/version/artifact-version[-classifier].jar."""
    parts = name.split(":")
    if len(parts) not in (3, 4):
        raise PlatformError(f"library {name!r} is not group:artifact:version; fix: check the JSON")
    group, artifact, version = parts[:3]
    classifier = f"-{parts[3]}" if len(parts) == 4 else ""
    return "/".join([*group.split("."), artifact, version, f"{artifact}-{version}{classifier}.jar"])


def flatten_arguments(items: Iterable[str | dict]) -> list[str]:
    """A Mojang argument list without its rule-gated entries that the bench never uses; an
    allowed entry's value (string or list) is spliced in."""
    found: list[str] = []
    for item in items:
        if isinstance(item, str):
            found.append(item)
        elif rules_allow(item.get("rules")):
            value = item["value"]
            found.extend(value if isinstance(value, list) else [value])
    return found


def feature_arguments(items: Iterable[str | dict], feature: str) -> list[str]:
    """The argument list a game-argument rule gates on `feature`; PlatformError when the JSON
    has none."""
    for item in items:
        if isinstance(item, dict):
            for rule in item.get("rules", []):
                if feature in rule.get("features", {}):
                    value = item["value"]
                    return value if isinstance(value, list) else [value]
    raise PlatformError(f"the version JSON gates no argument on {feature}; fix: check the JSON")


def build_spec(
    platform_id: str, version: dict, version_source: dict, profile: dict, profile_url: str
) -> dict:
    """The launch spec from Mojang's version JSON and Fabric's profile JSON (docs/platform.md
    #install-and-launch): sources, main class, asset index, logging, the classpath in order (the
    profile's libraries, Mojang's allowed on Windows x64, the client jar) with each jar's SHA-1,
    the JVM options, the game-argument template and the feature-gated arguments. Every profile
    library must carry its sha1 (the caller takes fabric-loader's from Maven's .sha1 file)."""
    if profile.get("inheritsFrom") != version.get("id"):
        raise PlatformError(
            f"profile {profile.get('id')!r} inherits from {profile.get('inheritsFrom')!r}, not "
            f"version {version.get('id')!r}; fix: fetch the profile for this version"
        )
    classpath = []
    for library in profile["libraries"]:
        if not library.get("sha1"):
            raise PlatformError(
                f"profile library {library['name']} carries no sha1; fix: take Maven's .sha1 file"
            )
        path = f"libraries/{maven_path(library['name'])}"
        classpath.append(
            {"path": path, "sha1": library["sha1"], "from": f"{FABRIC}:{library['name']}"}
        )
    for library in version["libraries"]:
        if not rules_allow(library.get("rules")):
            continue
        artifact = library["downloads"]["artifact"]
        path = f"libraries/{artifact['path']}"
        classpath.append(
            {"path": path, "sha1": artifact["sha1"], "from": f"{MOJANG}:{library['name']}"}
        )
    client = version["downloads"]["client"]
    client_path = f"versions/{version['id']}/{version['id']}.jar"
    classpath.append({"path": client_path, "sha1": client["sha1"], "from": f"{MOJANG}:{CLIENT}"})
    index = version["assetIndex"]
    logging = version["logging"]["client"]
    game = version["arguments"]["game"]
    return {
        "schema": SPEC_SCHEMA,
        "platform": platform_id,
        "writtenBy": WRITTEN_BY,
        "sources": {
            "versionJson": {
                "id": version_source["id"],
                "url": version_source["url"],
                "sha1": version_source["sha1"],
            },
            "fabricProfile": {"id": profile["id"], "url": profile_url},
        },
        "mainClass": profile["mainClass"],
        "assetIndex": {"id": index["id"], "sha1": index["sha1"], "url": index["url"]},
        "logging": {
            "id": logging["file"]["id"],
            "sha1": logging["file"]["sha1"],
            "argument": logging["argument"],
        },
        "classpathRule": CLASSPATH_RULE.format(id=platform_id),
        "classpath": classpath,
        "jvmOptions": flatten_arguments(version["arguments"]["jvm"])
        + flatten_arguments(profile.get("arguments", {}).get("jvm", [])),
        "gameArguments": flatten_arguments(game)
        + flatten_arguments(profile.get("arguments", {}).get("game", [])),
        "gameArgumentsNote": GAME_ARGUMENTS_NOTE,
        "featureArguments": {feature: feature_arguments(game, feature) for feature in FEATURES},
        "javaVersion": {
            "component": version["javaVersion"]["component"],
            "majorVersion": version["javaVersion"]["majorVersion"],
        },
    }


@dataclass(frozen=True)
class Difference:
    """One spec fact that differs: its dotted path, the committed value and the built one (None
    for a side that lacks the key)."""

    path: str
    committed: object
    built: object

    def text(self) -> str:
        return f"{self.path}: {json.dumps(self.committed)} -> {json.dumps(self.built)}"


def flatten(value: object, prefix: str = "") -> dict[str, object]:
    """{dotted path: leaf} of a JSON value; list items are indexed, `classpath[3].sha1`."""
    if isinstance(value, dict):
        found: dict[str, object] = {}
        for key, item in value.items():
            found.update(flatten(item, f"{prefix}.{key}" if prefix else key))
        return found
    if isinstance(value, list):
        found = {}
        for index, item in enumerate(value):
            found.update(flatten(item, f"{prefix}[{index}]"))
        return found
    return {prefix: value}


def spec_diff(committed: dict, built: dict) -> list[Difference]:
    """Every fact that differs between two specs, in the built spec's order then the committed
    one's; the note keys are skipped."""
    old = flatten({key: value for key, value in committed.items() if key not in NOTE_KEYS})
    new = flatten({key: value for key, value in built.items() if key not in NOTE_KEYS})
    found = [
        Difference(path, old.get(path), new[path]) for path in new if old.get(path) != new[path]
    ]
    found += [Difference(path, old[path], None) for path in old if path not in new]
    return found


def spec_text(spec: dict) -> str:
    """The spec as written: one-space indent (the Phase -1 spike's choice, kept so the refresh
    diff shows facts only), LF, one trailing newline."""
    return json.dumps(spec, indent=1) + "\n"


def spec_path(root: Path, platform_id: str) -> Path:
    return root / PLATFORMS / SPEC.format(id=platform_id)


def load_spec(root: Path, platform_id: str) -> dict | None:
    """The committed launch spec, None before the first install; PlatformError when it is not
    JSON."""
    path = spec_path(root, platform_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise PlatformError(
            f"{PLATFORMS}/{path.name} is not JSON ({error}); fix: `install --refresh`"
        ) from None
