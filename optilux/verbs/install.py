"""`optilux install [--tier bench] [--refresh] [--json]` (docs/platform.md#install-and-launch).

Fills runtime/<platform>/ from the network and re-hashes every file on every run: Minecraft and
the Fabric profile through minecraft-launcher-lib, then install's own pass over every classpath
jar, the asset index, every asset and the log config; the tier's Modrinth files into the store
runtime/<platform>/files/ by sha512, resource and shader packs copied into their game folders;
Temurin and PresentMon by sha256. The launch spec is built from Mojang's and Fabric's JSON and
compared with the committed one: a difference exits 1 naming it, and --refresh rewrites the file.
A hash that differs from its pin is refused with the file named, never repaired
(docs/plans/m1.md#7-stop-conditions). game/saves/ and the game's option files are never touched.
"""

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from minecraft_launcher_lib.exceptions import InvalidChecksum, VersionNotFound
from minecraft_launcher_lib.install import install_minecraft_version

from optilux import REPO_ROOT, platform
from optilux.verbs import Verb

PREFIX = "optilux install"
DEFAULT_TIER = "bench"
# The layout under runtime/ (AGENTS.md Layout, docs/platform.md#install-and-launch).
RUNTIME = "runtime"
STORE = "files"
JAVA_DIR = "runtime/java"
TOOLS_DIR = "runtime/tools"
JAVA_PROFILE = "config/java/bench.json"
TOOLS = "config/tools.json"
# The sources (docs/platform.md#install-and-launch): Mojang's manifest names the version JSON
# and its sha1; Fabric's meta serves the profile; Modrinth's version endpoint gives a file's URL
# and sha512; Adoptium's assets endpoint gives the archive's link and checksum.
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_PROFILE = "https://meta.fabricmc.net/v2/versions/loader/{game}/{loader}/profile/json"
MODRINTH_VERSION = "https://api.modrinth.com/v2/version/{id}"
ADOPTIUM = (
    "https://api.adoptium.net/v3/assets/release_name/eclipse/{release}"
    "?os=windows&architecture=x64&image_type=jdk&jvm_impl=hotspot&heap_size=normal&project=jdk"
)
# Modrinth refuses a request without a User-Agent that names the client and a contact.
USER_AGENT = "optilux (https://github.com/JosephGibson/Optilux)"
# A socket silent for this long is dead: the spike's whole install took 30 s.
TIMEOUT = 60
# The lib's progress callback names every file it fetches as `Download <name>`; these two are
# section headers, not files.
DOWNLOAD = "Download "
HEADERS = {"Download Libraries", "Download Assets"}
# The outcomes of the launch-spec check.
EQUAL, WRITTEN, REFRESHED, DIFFERS = "equal", "written", "refreshed", "differs"
# The fix a spec difference names: nothing is calibrated yet in M1, but from M2 on a changed spec
# is a platform change (docs/platform.md#install-and-launch).
REFRESH_FIX = (
    "`optilux install --refresh` rewrites it, then commit it (a changed spec is a platform "
    "change: recalibrate, platform.md#install-and-launch)"
)
# A hash that differs from its pin is a stop condition (docs/plans/m1.md#7-stop-conditions).
MISMATCH_FIX = "never work around it: re-pin from the source, or delete the file and rerun"


class InstallError(RuntimeError):
    """An install that cannot proceed; the message names the problem and the fix."""


@dataclass
class Outcome:
    """What one install found: the counts, each section's facts and the spec's state."""

    platform: str
    tier: str
    hashes: int = 0  # every digest compared with its pin
    downloaded: int = 0  # files fetched this run, the lib's included
    minecraft: dict = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    java: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    spec: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.spec.get("state") != DIFFERS

    def as_json(self) -> dict:
        return {"ok": self.ok, **asdict(self), "problem": None}


Say = Callable[[str], None]


def shown(path: Path, root: Path) -> str:
    """A path as printed: relative to the repo when inside it, forward slashes."""
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


# S310 in fetch and download: every URL comes from the committed platform file or the pinned
# version JSON, never from input.
def fetch(url: str) -> bytes:
    """The body of a GET; InstallError names the URL and the reason. The tests replace it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return response.read()
    except (urllib.error.URLError, OSError) as error:
        raise InstallError(f"GET {url} failed: {error}; fix: check the network") from None


def download(url: str, dest: Path) -> int:
    """Stream a GET into dest through dest.part, replacing dest when complete; the byte count.
    Nothing partial is left behind. The tests replace it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, part.open("wb") as out:  # noqa: S310
            while chunk := response.read(platform.CHUNK):
                out.write(chunk)
                size += len(chunk)
    except (urllib.error.URLError, OSError) as error:
        part.unlink(missing_ok=True)
        raise InstallError(f"GET {url} failed: {error}; fix: check the network") from None
    os.replace(part, dest)
    return size


def check_hash(
    path: Path, algorithm: str, pin: str, what: str, outcome: Outcome, root: Path
) -> None:
    """Hash a file and compare it with its pin; InstallError naming the file on a mismatch or
    when it is missing."""
    if not path.is_file():
        raise InstallError(f"{what} {shown(path, root)} is missing; fix: rerun `optilux install`")
    actual = platform.digest(path, algorithm)
    outcome.hashes += 1
    if actual != pin:
        raise InstallError(
            f"{what} {shown(path, root)}: {algorithm} {actual} differs from its pin {pin}; "
            f"fix: {MISMATCH_FIX}"
        )


def minecraft(
    root: Path, plat: platform.Platform, outcome: Outcome, say: Say
) -> tuple[dict, dict, dict, str]:
    """Minecraft and the Fabric profile into runtime/<id>/ through minecraft-launcher-lib:
    (version JSON, its manifest entry, the profile with every library's sha1, the profile URL).

    The lib installs a version from its local JSON when one exists, so the manifest is read
    here and the JSON re-fetched when Mojang republished it (docs/plans/m1.md P6); the lib then
    installs the profile, and 26.3 through its inheritsFrom, repairing any SHA-1 mismatch."""
    mcdir = root / RUNTIME / plat.id
    manifest = json.loads(fetch(MANIFEST))
    entry = next((v for v in manifest["versions"] if v["id"] == plat.minecraft), None)
    if entry is None:
        raise InstallError(
            f"Mojang's manifest lists no version {plat.minecraft}; fix: check the platform "
            "file's `minecraft`"
        )
    version_path = mcdir / "versions" / plat.minecraft / f"{plat.minecraft}.json"
    if not version_path.is_file() or platform.sha1(version_path) != entry["sha1"]:
        say(f"minecraft: fetching the version JSON of {plat.minecraft} ({entry['sha1'][:8]})")
        download(entry["url"], version_path)
        outcome.downloaded += 1
    check_hash(version_path, "sha1", entry["sha1"], "version JSON", outcome, root)
    version = json.loads(version_path.read_text(encoding="utf-8"))
    loader, loader_version = plat.loader
    if loader != platform.FABRIC:
        raise InstallError(f"loader {loader!r} is not fabric; fix: install knows Fabric only")
    profile_url = FABRIC_PROFILE.format(game=plat.minecraft, loader=loader_version)
    profile_bytes = fetch(profile_url)
    profile = json.loads(profile_bytes)
    if not platform.plain_name(str(profile.get("id", ""))):
        raise InstallError(f"{profile_url} names id {profile.get('id')!r}; fix: check Fabric meta")
    profile_path = mcdir / "versions" / profile["id"] / f"{profile['id']}.json"
    if not profile_path.is_file() or profile_path.read_bytes() != profile_bytes:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_bytes(profile_bytes)
    say(f"minecraft: installing {plat.minecraft} and {profile['id']} into {shown(mcdir, root)}")
    fetched: list[str] = []

    def status(text: str) -> None:
        if text.startswith(DOWNLOAD) and text not in HEADERS:
            fetched.append(text)

    try:
        install_minecraft_version(profile["id"], mcdir, {"setStatus": status})
    except InvalidChecksum as error:
        raise InstallError(f"minecraft-launcher-lib: {error}; fix: {MISMATCH_FIX}") from None
    except (VersionNotFound, OSError) as error:
        raise InstallError(
            f"minecraft-launcher-lib failed: {error}; fix: check the network"
        ) from None
    outcome.downloaded += len(fetched)
    for library in profile["libraries"]:
        if not library.get("sha1"):
            url = f"{library['url'].rstrip('/')}/{platform.maven_path(library['name'])}.sha1"
            library["sha1"] = fetch(url).decode("ascii").split()[0]
    source = {"id": entry["id"], "url": entry["url"], "sha1": entry["sha1"]}
    return version, source, profile, profile_url


def verify_minecraft(root: Path, plat: platform.Platform, spec: dict, outcome: Outcome) -> None:
    """install's own pass: every classpath jar, the asset index, every asset object and the log
    config hashed against the spec just built (the lib checks none of Fabric's libraries)."""
    mcdir = root / RUNTIME / plat.id
    for entry in spec["classpath"]:
        check_hash(mcdir / entry["path"], "sha1", entry["sha1"], "classpath jar", outcome, root)
    index_path = mcdir / "assets" / "indexes" / f"{spec['assetIndex']['id']}.json"
    check_hash(index_path, "sha1", spec["assetIndex"]["sha1"], "asset index", outcome, root)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    hashes = sorted({item["hash"] for item in index["objects"].values()})
    for digest in hashes:
        path = mcdir / "assets" / "objects" / digest[:2] / digest
        check_hash(path, "sha1", digest, "asset", outcome, root)
    log_path = mcdir / "assets" / "log_configs" / spec["logging"]["id"]
    check_hash(log_path, "sha1", spec["logging"]["sha1"], "log config", outcome, root)
    outcome.minecraft = {
        "version": plat.minecraft,
        "profile": spec["sources"]["fabricProfile"]["id"],
        "directory": shown(mcdir, root),
        "jars": len(spec["classpath"]),
        "assetIndex": spec["assetIndex"]["id"],
        "assets": len(hashes),
    }


def tier_files(root: Path, plat: platform.Platform, tier: str, outcome: Outcome, say: Say) -> None:
    """The tier's mods, resource packs and the reference packs into the store by sha512, a
    missing one fetched from Modrinth; resource and shader packs copied into their game folders
    when absent or different."""
    base = root / RUNTIME / plat.id
    store = base / STORE
    for pinned in plat.tier_files(tier):
        target = store / pinned.file
        state = EQUAL
        if not target.is_file():
            say(f"files: fetching {pinned.file} from Modrinth ({pinned.modrinth_version_id})")
            listing = json.loads(fetch(MODRINTH_VERSION.format(id=pinned.modrinth_version_id)))
            match = next(
                (f for f in listing.get("files", []) if f["filename"] == pinned.file), None
            )
            if match is None:
                raise InstallError(
                    f"Modrinth version {pinned.modrinth_version_id} ({pinned.slug} "
                    f"{pinned.version}) has no file {pinned.file}; fix: re-pin it from Modrinth"
                )
            if match["hashes"]["sha512"] != pinned.sha512:
                raise InstallError(
                    f"Modrinth lists {pinned.file} with sha512 {match['hashes']['sha512']} and "
                    f"the platform file pins {pinned.sha512}; fix: {MISMATCH_FIX}"
                )
            download(match["url"], target)
            outcome.downloaded += 1
            state = "downloaded"
        try:
            check_hash(target, "sha512", pinned.sha512, pinned.kind, outcome, root)
        except InstallError:
            if state == "downloaded":
                target.unlink()  # nothing refused stays in the store
            raise
        copy = copy_state = None
        if pinned.game_folder:
            path = base / pinned.game_folder / pinned.file
            copy = shown(path, root)
            if path.is_file() and platform.sha512(path) == pinned.sha512:
                outcome.hashes += 1
                copy_state = EQUAL
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, path)
                copy_state = "copied"
        outcome.files.append(
            {
                "file": pinned.file,
                "kind": pinned.kind,
                "tier": pinned.tier,
                "sha512": pinned.sha512,
                "state": state,
                "copy": copy,
                "copyState": copy_state,
            }
        )
    outcome.pending = plat.pending(tier)


def java(root: Path, outcome: Outcome, say: Say) -> None:
    """Temurin's archive by sha256 against config/java/bench.json, fetched from the Adoptium API
    when absent, and unpacked under runtime/java/<build>/ when that folder has no java.exe."""
    profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))["runtime"]
    archive = root / JAVA_DIR / profile["archive"]
    if not archive.is_file():
        say(f"java: fetching {profile['archive']} from the Adoptium API")
        release = json.loads(fetch(ADOPTIUM.format(release=urllib.parse.quote(profile["build"]))))
        packages = [binary["package"] for binary in release.get("binaries", [])]
        match = next((p for p in packages if p["name"] == profile["archive"]), None)
        if match is None:
            names = ", ".join(p["name"] for p in packages) or "none"
            raise InstallError(
                f"Adoptium serves no {profile['archive']} for {profile['build']} ({names}); "
                "fix: re-pin config/java/bench.json from the API"
            )
        if match["checksum"] != profile["archiveSha256"]:
            raise InstallError(
                f"Adoptium lists {profile['archive']} with sha256 {match['checksum']} and "
                f"bench.json pins {profile['archiveSha256']}; fix: {MISMATCH_FIX}"
            )
        download(match["link"], archive)
        outcome.downloaded += 1
    check_hash(archive, "sha256", profile["archiveSha256"], "java archive", outcome, root)
    home = root / JAVA_DIR / profile["build"]
    unpacked = (home / "bin" / "java.exe").is_file()
    if not unpacked:
        say(f"java: unpacking {profile['archive']} into {shown(home, root)}")
        with zipfile.ZipFile(archive) as zipped:
            tops = {name.split("/", 1)[0] for name in zipped.namelist()}
            if tops != {profile["build"]}:
                raise InstallError(
                    f"{profile['archive']} unpacks to {', '.join(sorted(tops))}, not "
                    f"{profile['build']}; fix: make bench.json's `build` the archive's folder"
                )
            zipped.extractall(root / JAVA_DIR)
    outcome.java = {
        "build": profile["build"],
        "archive": profile["archive"],
        "home": shown(home, root),
        "unpacked": "present" if unpacked else "unpacked",
    }


def tools(root: Path, outcome: Outcome, say: Say) -> None:
    """Every tool config/tools.json pins (a dict with `file` and `sha256`) into runtime/tools/."""
    pins = json.loads((root / TOOLS).read_text(encoding="utf-8"))
    for name, tool in pins.items():
        if not isinstance(tool, dict) or "sha256" not in tool:
            continue
        if not platform.plain_name(tool["file"]):
            raise InstallError(f"config/tools.json {name}: {tool['file']!r} is no plain file name")
        target = root / TOOLS_DIR / tool["file"]
        state = EQUAL
        if not target.is_file():
            say(f"tools: fetching {tool['file']}")
            download(tool["source"], target)
            outcome.downloaded += 1
            state = "downloaded"
        try:
            check_hash(target, "sha256", tool["sha256"], f"tool {name}", outcome, root)
        except InstallError:
            if state == "downloaded":
                target.unlink()
            raise
        outcome.tools.append({"tool": name, "file": tool["file"], "state": state})


def launch_spec(
    root: Path, plat: platform.Platform, built: dict, refresh: bool, outcome: Outcome
) -> None:
    """The built spec against the committed one: written when none exists, equal, refreshed
    (--refresh, any byte different) or differs; the facts that moved in either case."""
    path = platform.spec_path(root, plat.id)
    committed = platform.load_spec(root, plat.id)
    text = platform.spec_text(built)
    diff: list[platform.Difference] = []
    if committed is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        state = WRITTEN
    else:
        diff = platform.spec_diff(committed, built)
        if refresh and path.read_bytes() != text.encode("utf-8"):
            path.write_bytes(text.encode("utf-8"))
            state = REFRESHED
        elif diff:
            state = DIFFERS
        else:
            state = EQUAL
    outcome.spec = {
        "path": shown(path, root),
        "state": state,
        "diff": [asdict(difference) for difference in diff],
    }


def install(root: Path, tier: str, refresh: bool, say: Say) -> Outcome:
    """One install of the current platform's tier; InstallError or PlatformError when it cannot
    proceed, every hash checked before the spec verdict."""
    plat = platform.load(root)
    if tier not in plat.tiers:
        raise InstallError(
            f"no tier {tier!r} in {plat.path.name}; fix: one of {', '.join(plat.tiers)}"
        )
    outcome = Outcome(plat.id, tier)
    version, source, profile, profile_url = minecraft(root, plat, outcome, say)
    built = platform.build_spec(plat.id, version, source, profile, profile_url)
    verify_minecraft(root, plat, built, outcome)
    tier_files(root, plat, tier, outcome, say)
    java(root, outcome, say)
    tools(root, outcome, say)
    launch_spec(root, plat, built, refresh, outcome)
    return outcome


def report(outcome: Outcome) -> list[str]:
    """The text report, one line per section and a last line with the counts."""
    mc = outcome.minecraft
    lines = [
        f"minecraft: {mc['version']} and {mc['profile']} in {mc['directory']}/: {mc['jars']} jars, "
        f"asset index {mc['assetIndex']}, {mc['assets']:,} assets and the log config sha1-equal"
    ]
    names = ", ".join(f"{entry['file']} ({entry['state']})" for entry in outcome.files)
    lines.append(f"files ({outcome.tier}): {len(outcome.files)} sha512-equal in the store: {names}")
    copies = [f"{e['copy']} ({e['copyState']})" for e in outcome.files if e["copy"]]
    if copies:
        lines.append(f"copies: {'; '.join(copies)}")
    lines += [f"pending: {pending}" for pending in outcome.pending]
    java_facts = outcome.java
    lines.append(
        f"java: {java_facts['build']}: {java_facts['archive']} sha256-equal, "
        f"{java_facts['unpacked']} at {java_facts['home']}"
    )
    lines += [f"tools: {tool['file']} sha256-equal ({tool['state']})" for tool in outcome.tools]
    spec = outcome.spec
    count = len(spec["diff"])
    facts = f"{count} fact{'s' if count != 1 else ''}"
    if spec["state"] == EQUAL:
        lines.append(f"launch spec: equal to {spec['path']}")
    elif spec["state"] == WRITTEN:
        lines.append(f"launch spec: written to {spec['path']} (the first install)")
    elif spec["state"] == REFRESHED:
        lines.append(f"launch spec: refreshed {spec['path']} ({facts} changed)")
    else:
        lines.append(f"launch spec: differs from {spec['path']} in {facts}:")
    lines += [f"  {platform.Difference(**difference).text()}" for difference in spec["diff"]]
    verdict = "ok" if outcome.ok else "the launch spec moved"
    lines.append(
        f"{PREFIX}: {verdict}; {outcome.hashes:,} hashes checked, {outcome.downloaded:,} files "
        "downloaded"
    )
    return lines


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tier", default=DEFAULT_TIER, help=f"the mod tier to install (default {DEFAULT_TIER})"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="rewrite the launch spec from the fetched JSON"
    )


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)
    try:
        outcome = install(root, args.tier, args.refresh, say)
    except (InstallError, platform.PlatformError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(outcome.as_json()))
    else:
        lines = report(outcome)
        print("\n".join(lines[:-1]), flush=True)  # before a verdict on stderr: read in order
        if outcome.ok:
            print(lines[-1])
        else:
            print(f"{lines[-1]}; fix: {REFRESH_FIX}", file=sys.stderr)
    return 0 if outcome.ok else 1


VERB = Verb(
    name="install",
    help="install the platform hash-checked and check the launch spec",
    run=run,
    configure=configure,
    structured=True,
)
