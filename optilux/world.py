"""World snapshots, their restore and the bench world's preparation (docs/measurement.md
#baseline-suite and #session, docs/plans/m2.md M2.P04, D44, D45, D49).

A snapshot is snapshots/<id>/, a copy of the game's saves/<world>/, beside it <id>.manifest (one
`<sha256>  <path>` line per file, its sha256 the tree hash: run-record.md#identity) and <id>.json
(the hash, the file count, the bench player's uuid from players/data/, F8). `restore` makes the
live world equal to its snapshot in place (D44): files that differ copied back, files the
snapshot lacks deleted, the live tree hashed equal after. Both refuse while a game runs from
runtime/<platform>/. `prep` builds the snapshot of a views file's world: the world prep set
installed, the world restored, the data pack of view functions written (the coverage views'
too, plans/m3.md D64; an End view's setting the End's clock, D56), the game launched with
Chunky; through the mod's `command` the gamerules, /tick freeze, a torch in the main hand, the
pre-generation (D45, each task awaited in latest.log), the coverage site built and counted, then
at every view the kill of suite.json world.setup until nothing it selects is counted, the counts
and one 4K reference frame; the site counted again; the quit, then a new snapshot.
"""

import contextlib
import json
import math
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from optilux import launch, modclient, platform, record
from optilux.acceptance import helper_lines, png_size
from optilux.session import (
    OVERWORLD,
    PLACE_TIMEOUT,
    READY_TIMEOUT,
    REQUESTS,
    STABLE_FRAMES,
    WORLD_TIMEOUT,
    RunHost,
    Session,
    framebuffer_refusal,
    framebuffer_size,
    now,
    shows_hand,
    view_pose,
)
from optilux.verbs.install import RUNTIME, Say, shown

# The snapshot's files beside its folder (never inside it: the tree hash covers the folder).
MANIFEST = "{id}.manifest"
FACTS = "{id}.json"
SCHEMA = 1
# A snapshot is copied to a hidden folder first and swapped in only once it hashes equal to the
# live world; the old one waits under its own hidden name until the swap is done.
NEW = ".{id}.new"
OLD = ".{id}.old"
# restore copies a file through this name beside its target, so no half file carries the name.
PART = ".optilux-restore"

# The data pack (measurement.md#session): datapacks/optilux/, one function per view, called as
# `/function optilux:view/<id>`. A pack of data format 82 or later declares min_format and
# max_format (plans/m2.md P10); on 26.3 a function reports success only through `/return`.
PACK = "optilux"
NAMESPACE = "optilux"
FUNCTIONS = f"data/{NAMESPACE}/function/view"
FUNCTION = "{namespace}:view/{id}"

# Pre-generation (plans/m2.md D45): the views' bounding box per dimension plus the render
# distance (16 chunks, suite.json display) and a 32-block margin; one square per End view, as
# the End's two areas lie over 1,000 blocks apart.
MARGIN = 256 + 32
END = "minecraft:the_end"
# Chunky's lines (lang/en.json at 1.5.3, plans/m2.md P8): a player's commands are answered in
# chat, which the client logs as "[System] [CHAT] <text>"; the task's progress and end go to the
# server console, which the integrated server logs. Colour codes (section sign + one character)
# are stripped before matching.
CODES = re.compile("§.")
WORLD_ECHO = re.compile(r"World changed to (?P<world>\S+)\.\s*$")
STARTED = re.compile(r"Task started in (?P<world>\S+) for the ")
CONFIRM = "A task was already started for this world."
ALREADY = re.compile(r"Task already started for (?P<world>\S+)!")
UPDATE = re.compile(
    r"Task running for (?P<world>\S+)\. Processed: (?P<chunks>\d+) chunks "
    r"\((?P<percent>[\d.,]+)%\)"
)
DONE = re.compile(
    r"Task finished for (?P<world>\S+)\. Processed: (?P<chunks>\d+) chunks "
    r"\((?P<percent>[\d.,]+)%\), Total time: (?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})"
)
STOPPED = re.compile(r"Task stopped for (?P<world>\S+)\.")
NO_TASKS = "No tasks running."
NO_CONTINUE = "No tasks to continue."
# A finished line's percent ("%.2f"): a task ends when no chunk is left, at 100.00.
COMPLETE = 99.995
# A task's waits (seconds): D45's 60 s without progress, `chunky progress` asked when no update
# line came for PROGRESS_ASK, at most TASK_TIMEOUT a task; Chunky's echo of a command.
STALL = 60.0
PROGRESS_ASK = 10.0
TASK_TIMEOUT = 1800.0
ECHO_TIMEOUT = 15.0
POLL = 1.0

# The kill (suite.json world.setup): every entity but the player, the ender dragon, the end
# crystals on end_dragon's pillars and what carries the bench tag, within the render distance of
# the camera; repeated until two counts a second apart find nothing. A killed mob's body goes
# only with ticks (it dies over 20), and stepped ticks fire the block ticks world generation
# left pending (sand falls, plants pop off), which leaves debris: dropped items, experience orbs
# and falling blocks (the first prep's forest_noon and ocean_sunset). Debris dies at once, so
# ticks are stepped only after a kill that took more than debris, and a last sweep at every view
# kills, ticks frozen, what later views' ticks left near earlier ones.
TAG = "optilux_bench"
SPARED = ("minecraft:player", "minecraft:ender_dragon", "minecraft:end_crystal")
DEBRIS = ("minecraft:item", "minecraft:experience_orb", "minecraft:falling_block")
RADIUS = 256
KILL_TICKS = 40
KILL_ROUNDS = 10
CLEAR_COUNTS = 2
# The tagged mobs' entities load after their chunks: their positions are read for up to this.
POSITIONS_WAIT = 10.0
# 26.3's answers (0.01.11's reads, kept in memory as the mod's command feedback formats).
COUNT = re.compile(r"^Test passed\. Count: (?P<count>\d+)$")
NO_COUNT = "Test failed"
NO_KILL = "No entity was found"
POSITION = re.compile(
    r"^(?P<name>.+) has the following entity data: \[(?P<x>-?[\d.E-]+)d, (?P<y>-?[\d.E-]+)d, "
    r"(?P<z>-?[\d.E-]+)d\]$"
)
# What prep must count (measurement.md#baseline-suite, the views file): the entities role's seven
# tagged mobs, end_dragon's ten end crystals and no dragon (ticks were frozen before the End first
# loaded). The End's dragon fight spawns a dragon on its first tick with a player within 192
# blocks of (0, 128, 0): no tick is stepped with the camera that near (a 64-block margin).
ENTITIES = "entities"
TAGGED_MOBS = 7
END_DRAGON = "end_dragon"
END_CRYSTALS = 10
ARENA = (0.0, 128.0, 0.0)
ARENA_RADIUS = 192 + 64
# The reference frames: one per view, the display's size (suite.json display.resolution).
FRAMES = "frames"
FRAME_TIMEOUT = 60.0
# The GUI is hidden at every view but entities, which keeps the torch in frame in creative
# (plans/m2.md D49), and a coverage view with `hand` (session.shows_hand); spectator elsewhere,
# as camera.place needs a spectator or a flyer.
TORCH = "minecraft:torch"
# The End's own clock (plans/m3.md P22, D56): the End flash follows it, so an End view's function
# sets it to the view's time and prep reads it back at the view (`time of <clock> query time`).
END_CLOCK = "minecraft:the_end"
CLOCK = re.compile(rf"^Clock {END_CLOCK} is at (?P<ticks>\d+) tick\(s\)$")

# The coverage site (plans/m3.md D64): a floor of smooth stone at y 100 over x 306..322 and z
# 1061..1077, near (314, 1069) in the overworld, whose views (the views file's coverage list) lie
# over 512 blocks from every perf view; the snapshot's chunks under it reach y 83 at most (read
# 2026-10-22), so nothing stands in its way. suite.json coverageViews' content stands on it, built
# through `command` once Chunky has generated the area: NoAI mobs, an armor stand, an item frame,
# a dropped item, an enchanted item (the enchanted golden apple's own glint), a sign's text, a
# beacon on its iron base and a campfire as the particle source; the held torch is a view's `hand`.
SITE = "x=306,y=100,z=1061,dx=16,dy=10,dz=16"  # a selector's box over the floor and above it
FILLS = (
    ("floor", (306, 100, 1061), (322, 100, 1077), "minecraft:smooth_stone"),
    ("beacon base", (313, 100, 1063), (315, 100, 1065), "minecraft:iron_block"),
)
# Each block: its name, its position, what setblock places and the predicate `execute if block`
# tests it by. The sign faces north (rotation 8), its text in front; the planks hold the frame.
SIGN_TEXT = "Optilux"
BLOCKS = (
    ("beacon", (314, 101, 1064), "minecraft:beacon", "minecraft:beacon"),
    ("campfire", (311, 101, 1064), "minecraft:campfire[lit=true]", "minecraft:campfire[lit=true]"),
    ("planks", (315, 101, 1073), "minecraft:spruce_planks", "minecraft:spruce_planks"),
    (
        "sign",
        (313, 101, 1072),
        f'minecraft:oak_sign[rotation=8]{{front_text:{{messages:["{SIGN_TEXT}","coverage","",""]}}}}',
        "minecraft:oak_sign[rotation=8]",
    ),
)
SIGN = BLOCKS[3][1]
# 26.3's answers to a block already as asked (en_us.json): the block is there, so neither fails.
UNCHANGED = ("Could not set the block", "No blocks were filled")
PASSED = "Test passed"
SIGN_LINE = '{x}, {y}, {z} has the following block data: "{text}"'


@dataclass(frozen=True)
class Content:
    """One entity of the coverage content: its name, type, position (a decimal, never centred by
    the command), yaw and data beside the bench tag, and an nbt filter telling it from the site's
    other entities of its type. Each carries PersistenceRequired, which only a mob reads; a mob is
    NoAI and Silent, a dropped item keeps still and never despawns or is picked up."""

    name: str
    kind: str
    pos: tuple[float, float, float]
    yaw: float
    data: str
    match: str = ""

    def summon(self) -> str:
        x, y, z = self.pos
        tags = f'Tags:["{TAG}"],PersistenceRequired:1b,Rotation:[{self.yaw:.1f}f,0.0f]'
        return f"/summon {self.kind} {x:.1f} {y:.1f} {z:.1f} {{{tags},{self.data}}}"

    def selector(self) -> str:
        nbt = f",nbt={self.match}" if self.match else ""
        return f"@e[type={self.kind},tag={TAG},{SITE}{nbt}]"


MOB = "NoAI:1b,Silent:1b"
ITEM = 'Item:{{id:"{id}",count:1}},NoGravity:1b,Age:-32768s,PickupDelay:32767s'
CONTENT = (
    Content("mooshroom", "minecraft:mooshroom", (308.0, 101.0, 1066.5), -90.0, MOB),
    Content("polar bear", "minecraft:polar_bear", (307.5, 101.0, 1069.5), -70.0, MOB),
    Content("fox", "minecraft:fox", (308.5, 101.0, 1072.5), -110.0, MOB),
    Content(
        "armor stand",
        "minecraft:armor_stand",
        (311.5, 101.0, 1072.5),
        180.0,
        'ShowArms:1b,equipment:{head:{id:"minecraft:iron_helmet",count:1},'
        'chest:{id:"minecraft:diamond_chestplate",count:1}}',
    ),
    # Facing north on the planks behind it; Pos and block_pos given, so the frame loads at its
    # block without "Block-attached entity at invalid position" in latest.log (BlockAttachedEntity).
    Content(
        "item frame",
        "minecraft:item_frame",
        (315.5, 101.5, 1072.5),
        0.0,
        'Facing:2b,Fixed:1b,Item:{id:"minecraft:diamond_sword",count:1},'
        "Pos:[315.5d,101.5d,1072.5d],block_pos:[I;315,101,1072]",
    ),
    Content(
        "dropped item",
        "minecraft:item",
        (317.0, 101.0, 1072.0),
        0.0,
        ITEM.format(id="minecraft:diamond"),
        '{Item:{id:"minecraft:diamond"}}',
    ),
    Content(
        "enchanted item",
        "minecraft:item",
        (318.0, 101.0, 1072.5),
        0.0,
        ITEM.format(id="minecraft:enchanted_golden_apple"),
        '{Item:{id:"minecraft:enchanted_golden_apple"}}',
    ),
)


class Processes(Protocol):
    """What snapshot and restore ask of the machine: the running processes (launch.Host)."""

    def processes(self) -> list[launch.ProcessInfo]: ...


class WorldError(RuntimeError):
    """A snapshot, restore or preparation that cannot proceed; the message names the fix."""


# Snapshot and restore.


def check_id(world_id: str) -> None:
    """A snapshot's id is a views file's: [a-z0-9_]{1,40}."""
    if not record.VIEW_ID.fullmatch(world_id):
        raise WorldError(f"world id {world_id!r} is not [a-z0-9_]{{1,40}}; fix: a views file's id")


def save_path(root: Path, plat: platform.Platform, save: str) -> Path:
    """saves/<save> of the platform's game; a name that is not one folder is refused."""
    if not platform.plain_name(save):
        raise WorldError(f"world {save!r} is not one folder name; fix: name a saves/ folder")
    return root / RUNTIME / plat.id / launch.GAME / launch.SAVES / save


def refuse_running(root: Path, plat: platform.Platform, host: Processes) -> None:
    """No game may run from runtime/<platform>/ while its world is copied or restored."""
    base = root / RUNTIME / plat.id
    games = launch.games(base, host.processes(), os.getpid())
    if games:
        names = "; ".join(f"pid {g['pid']} {g['name']}" for g in games)
        raise WorldError(f"a game runs from {shown(base, root)}/ ({names}); fix: quit it first")


def player_uuid(world: Path) -> str | None:
    """The bench player's uuid from players/data/<uuid>.dat (F8); None when the world holds no
    player file, refused when it holds more than one."""
    folder = world / launch.PLAYERS
    found = folder.glob("*.dat") if folder.is_dir() else []
    names = sorted(p.stem for p in found if launch.UUID_NAME.fullmatch(p.stem))
    if len(names) > 1:
        raise WorldError(
            f"{launch.PLAYERS}/ in {world.name} holds {len(names)} player files; fix: keep the "
            "bench player's"
        )
    return names[0] if names else None


def snapshot_paths(root: Path, world_id: str) -> tuple[Path, Path, Path]:
    """The snapshot's folder, manifest and facts file."""
    snaps = root / record.SNAPSHOTS
    return (
        snaps / world_id,
        snaps / MANIFEST.format(id=world_id),
        snaps / FACTS.format(id=world_id),
    )


def tree_bytes(folder: Path) -> int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def snapshot(
    root: Path, world_id: str, save: str, host: Processes, say: Say, note: str | None = None
) -> dict:
    """snapshots/<world_id>/ retaken from saves/<save>: copied beside the old one, hashed equal to
    the live world, then swapped in; its manifest and facts written beside it. The facts."""
    check_id(world_id)
    plat = platform.load(root)
    live = save_path(root, plat, save)
    if not (live / launch.LEVEL).is_file():
        raise WorldError(f"no world {shown(live, root)}/ with a level.dat; fix: name one")
    refuse_running(root, plat, host)
    folder, manifest_path, facts_path = snapshot_paths(root, world_id)
    new = folder.with_name(NEW.format(id=world_id))
    old = folder.with_name(OLD.format(id=world_id))
    recover(folder, old)
    if new.exists():  # an interrupted snapshot's copy
        shutil.rmtree(new)
    new.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(live, new)
    copied = record.tree(new)
    again = record.tree(live)
    try:
        if copied[:2] != again[:2]:
            raise WorldError(
                f"{shown(live, root)}/ changed while it was copied ({again[0][:12]}... against "
                f"the copy's {copied[0][:12]}...); fix: quit whatever writes it, then retake"
            )
        uuid = player_uuid(new)
    except WorldError:
        shutil.rmtree(new)
        raise
    if folder.exists():
        os.replace(folder, old)
    try:
        os.replace(new, folder)
    except OSError as error:
        if old.exists():
            os.replace(old, folder)  # the old snapshot back under its name
        raise WorldError(
            f"{shown(folder, root)}/ could not be replaced ({error}); the old snapshot is kept, "
            f"the copy left in {new.name}; fix: quit whatever holds snapshots/, then retake"
        ) from None
    digest, count, manifest = copied
    manifest_path.write_bytes(manifest.encode("utf-8"))
    facts = {
        "schema": SCHEMA,
        "id": world_id,
        "platform": plat.id,
        "world": save,
        "takenAt": now(),
        "treeSha256": digest,
        "files": count,
        "bytes": tree_bytes(folder),
        "playerUuid": uuid,
        "manifest": manifest_path.name,
        "note": note,
    }
    facts_path.write_bytes((json.dumps(facts, indent=1) + "\n").encode("utf-8"))
    say(
        f"world snapshot: {shown(folder, root)}/ from {shown(live, root)}/: {digest} ({count} "
        f"files, {facts['bytes']:,} bytes), player {uuid or 'none (offlinePlayer)'}"
    )
    try:
        if old.exists():
            shutil.rmtree(old)
    except OSError as error:  # the snapshot is in place; the next one clears what is left
        say(f"world snapshot: {old.name} not yet deleted ({error})")
    return facts


def recover(folder: Path, old: Path) -> None:
    """A swap interrupted between its two renames leaves the old snapshot under its hidden name
    and none under the real one: put it back. With both present, the hidden one is a leftover."""
    if not old.exists():
        return
    if folder.exists():
        shutil.rmtree(old)
    else:
        os.replace(old, folder)


def load_facts(root: Path, world_id: str) -> dict | None:
    """The snapshot's facts, None for one taken before `world snapshot` wrote them."""
    path = snapshot_paths(root, world_id)[2]
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise WorldError(f"{shown(path, root)} is not JSON ({error}); fix: retake it") from None


def clear(path: Path) -> None:
    """A file or folder removed, whichever it is."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def restore_tree(snap: Path, live: Path) -> dict:
    """`live` made equal to `snap` in place (D44): every file whose sha256 differs or that is
    missing copied (through a PART name, then replaced), every file `snap` lacks deleted, then
    the folders: `snap`'s made, the others pruned once empty. Re-hashed after; WorldError when
    the two still differ. Repeating it after an interruption finishes the job: a PART file is a
    file the snapshot lacks."""
    wanted = dict(record.tree_files(snap))
    live.mkdir(parents=True, exist_ok=True)
    found = dict(record.tree_files(live))
    copied, deleted = [], []
    for path in sorted(found, key=lambda p: p.encode("utf-8")):
        if path not in wanted:
            (live / path).unlink()
            deleted.append(path)
    folders = sorted({p.relative_to(snap).as_posix() for p in snap.rglob("*") if p.is_dir()})
    for name in folders:
        target = live / name
        if target.exists() and not target.is_dir():
            clear(target)
        target.mkdir(parents=True, exist_ok=True)
    for path, digest in wanted.items():
        if found.get(path) == digest:
            continue
        target = live / path
        if target.is_dir():
            clear(target)
        part = target.with_name(target.name + PART)
        shutil.copyfile(snap / path, part)
        os.replace(part, target)
        copied.append(path)
    kept = set(folders)
    for folder in sorted(live.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        name = folder.relative_to(live).as_posix()
        if folder.is_dir() and name not in kept and not any(folder.iterdir()):
            folder.rmdir()
    want_hash, want_count, _ = record.tree(snap)
    got_hash, got_count = record.tree_hash(live)
    if (got_hash, got_count) != (want_hash, want_count):
        raise WorldError(
            f"{live} hashes {got_hash[:12]}... ({got_count} files) after the restore, its "
            f"snapshot {want_hash[:12]}... ({want_count}); fix: quit whatever writes it, rerun"
        )
    return {
        "treeSha256": got_hash,
        "files": got_count,
        "copied": copied,
        "deleted": deleted,
        "kept": len(wanted) - len(copied),
    }


def restore(root: Path, world_id: str, save: str, host: Processes, say: Say) -> dict:
    """saves/<save> restored from snapshots/<world_id>/ in place (D44), the snapshot first checked
    against the hash its facts hold when it has them. The restore's facts."""
    check_id(world_id)
    plat = platform.load(root)
    folder, _, facts_path = snapshot_paths(root, world_id)
    live = save_path(root, plat, save)
    refuse_running(root, plat, host)
    recover(folder, folder.with_name(OLD.format(id=world_id)))
    if not folder.is_dir():
        raise WorldError(
            f"no snapshot {shown(folder, root)}/; fix: `optilux world snapshot {world_id}`"
        )
    facts = load_facts(root, world_id)
    retake = f"fix: retake it (`optilux world snapshot {world_id}`)"
    if facts is not None:
        if facts.get("world") != save:
            raise WorldError(
                f"{shown(folder, root)}/ was taken from saves/{facts.get('world')}, not "
                f"saves/{save}: restoring it there would overwrite another world; fix: name "
                f"saves/{facts.get('world')}, or retake the snapshot from saves/{save}"
            )
        digest, count = record.tree_hash(folder)
        if (digest, count) != (facts["treeSha256"], facts["files"]):
            raise WorldError(
                f"{shown(folder, root)}/ hashes {digest[:12]}... ({count} files), its "
                f"{facts_path.name} {facts['treeSha256'][:12]}... ({facts['files']}): the snapshot "
                f"changed after it was taken; {retake}"
            )
    found = restore_tree(folder, live)
    if facts is not None and found["treeSha256"] != facts["treeSha256"]:
        raise WorldError(f"{shown(folder, root)}/ changed during the restore; {retake}")
    found["checkedAgainstFacts"] = facts is not None
    say(
        f"world restore: {shown(live, root)}/ equals {shown(folder, root)}/: "
        f"{found['treeSha256']} ({found['files']} files); copied {len(found['copied'])}, "
        f"deleted {len(found['deleted'])}, kept {found['kept']}"
    )
    return found


# The data pack.


def pack_format(data_format: str) -> list[int]:
    """The platform file's data format ("121.0") as pack.mcmeta's [major, minor]."""
    major, _, minor = data_format.partition(".")
    if not major.isdigit() or not (minor or "0").isdigit():
        raise WorldError(f"data format {data_format!r} is not <major>.<minor>; fix: the platform")
    return [int(major), int(minor or "0")]


def pack_mcmeta(data_format: str, views_id: str) -> bytes:
    """pack.mcmeta for the platform's data format alone (P10: min_format and max_format, no
    pack_format); one-space JSON, LF."""
    version = pack_format(data_format)
    pack = {
        "pack": {
            "description": f"Optilux view functions from config/views/{views_id}.json",
            "min_format": version,
            "max_format": version,
        }
    }
    return (json.dumps(pack, indent=1) + "\n").encode("utf-8")


def view_function(view: dict, views_id: str) -> bytes:
    """A view's function: the overworld clock's time and the weather, both run in the overworld
    (the Nether has no clock, session.set_time); an End view's also sets the End's own clock to
    the view's time (END_CLOCK: plans/m3.md P22, D56); then `return 1`, the only success a
    function reports on 26.3 (P10). A time already at its value fails inside without failing the
    function. LF."""
    lines = [
        f"# {FUNCTION.format(namespace=NAMESPACE, id=view['id'])} from config/views/"
        f"{views_id}.json (optilux world prep)",
        f"execute in {OVERWORLD} run time set {view['time']}",
        f"execute in {OVERWORLD} run weather {view['weather']}",
    ]
    if view["dim"] == END:
        lines.append(f"time of {END_CLOCK} set {view['time']}")
    lines.append("return 1")
    return ("\n".join(lines) + "\n").encode("utf-8")


def pack_files(views: dict, data_format: str) -> dict[str, bytes]:
    """The data pack's files by their path under datapacks/<PACK>/: a function per view, the
    coverage views' too (plans/m3.md D64)."""
    files = {"pack.mcmeta": pack_mcmeta(data_format, views["id"])}
    for view in record.every_view(views):
        files[f"{FUNCTIONS}/{view['id']}.mcfunction"] = view_function(view, views["id"])
    return files


def write_pack(world: Path, files: dict[str, bytes]) -> dict:
    """datapacks/<PACK>/ made to hold exactly `files`: each written where its bytes differ, every
    other file pruned (a function of a view no longer in the views file), empty folders after."""
    folder = world / "datapacks" / PACK
    written, pruned = [], []
    if folder.exists():
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            name = path.relative_to(folder).as_posix()
            if name not in files:
                path.unlink()
                pruned.append(name)
    for name, data in files.items():
        path = folder / name
        if path.is_file() and path.read_bytes() == data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(name)
    for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return {"files": len(files), "written": written, "pruned": pruned}


# Chunky's selections.


@dataclass(frozen=True)
class Selection:
    """One Chunky task: a world, a shape, its centre and radii in blocks, the views it covers."""

    world: str
    shape: str
    x: int
    z: int
    radius_x: int
    radius_z: int
    views: tuple[str, ...]

    def commands(self) -> list[tuple[str, str]]:
        """The commands that select it, each with the start of the chat line Chunky answers it
        with: the world's as Chunky names it (read back by WORLD_ECHO), the shape's translated."""
        if self.shape == "square":
            radius = (f"/chunky radius {self.radius_x}", f"Radius changed to {self.radius_x}.")
        else:
            radius = (
                f"/chunky radius {self.radius_x} {self.radius_z}",
                f"Radius changed for x to {self.radius_x}, and for z to {self.radius_z}.",
            )
        return [
            (f"/chunky world {self.world}", "World changed to "),
            (f"/chunky shape {self.shape}", "Shape changed to "),
            (f"/chunky center {self.x} {self.z}", f"Center changed to {self.x}, {self.z}."),
            radius,
        ]


def span(low: float, high: float) -> tuple[int, int]:
    """A centre and a radius in whole blocks covering low..high plus MARGIN on both sides."""
    start = math.floor(low) - MARGIN
    end = math.ceil(high) + MARGIN
    if (end - start) % 2:
        end += 1
    return (start + end) // 2, (end - start) // 2


def selections(views: dict) -> list[Selection]:
    """D45's tasks from the views file: one rectangle per dimension over its views' bounding box
    plus MARGIN, the coverage views among them (plans/m3.md D64), in the file's order of first
    appearance; the End's one square per view."""
    found: list[Selection] = []
    dims: list[str] = []
    every = record.every_view(views)
    for view in every:
        if view["dim"] not in dims:
            dims.append(view["dim"])
    for dim in dims:
        group = [v for v in every if v["dim"] == dim]
        parts = [[v] for v in group] if dim == END else [group]
        for part in parts:
            x, rx = span(min(v["x"] for v in part), max(v["x"] for v in part))
            z, rz = span(min(v["z"] for v in part), max(v["z"] for v in part))
            shape = "rectangle"
            if dim == END:
                shape, rx = "square", max(rx, rz)
                rz = rx
            found.append(Selection(dim, shape, x, z, rx, rz, tuple(v["id"] for v in part)))
    return found


def strip_codes(text: str) -> str:
    return CODES.sub("", text)


class LogTail:
    """latest.log read on from where it stood: the complete lines written since, colour codes
    stripped. log4j rolls the file only at a start or at midnight; a shorter file is read from
    its start."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = path.stat().st_size if path.is_file() else 0
        self.pending: list[str] = []

    def unread(self, lines: list[str]) -> None:
        """Lines a reader took past what it waited for, handed to the next poll first."""
        self.pending = lines + self.pending

    def poll(self) -> list[str]:
        found, self.pending = self.pending, []
        return found + self.read()

    def read(self) -> list[str]:
        try:
            size = self.path.stat().st_size
            if size < self.offset:
                self.offset = 0
            with self.path.open("rb") as handle:
                handle.seek(self.offset)
                data = handle.read()
        except FileNotFoundError:
            return []
        end = data.rfind(b"\n")
        if end < 0:
            return []
        self.offset += end + 1
        text = data[:end].decode("utf-8", errors="replace")
        return [strip_codes(line) for line in text.splitlines()]


@dataclass
class TaskState:
    """What latest.log said of one task so far."""

    world: str
    started: bool = False
    confirm: bool = False
    already: bool = False
    stopped: bool = False
    no_tasks: bool = False
    done: dict | None = None
    chunks: int | None = None
    percent: float | None = None
    updates: int = 0
    console_updates: int = 0
    lines: list[str] = field(default_factory=list)


def number(text: str) -> float:
    """Chunky's percent: String.format("%.2f") in the JVM's locale, a comma or a point."""
    return float(text.replace(",", "."))


def read_task(state: TaskState, lines: list[str]) -> bool:
    """Fold latest.log's new lines into a task's state; True when one told of its progress."""
    moved = False
    for line in lines:
        if (m := STARTED.search(line)) and m.group("world") == state.world:
            state.started = True
        elif CONFIRM in line:
            state.confirm = True
        elif (m := ALREADY.search(line)) and m.group("world") == state.world:
            state.already = True
        elif (m := DONE.search(line)) and m.group("world") == state.world:
            seconds = int(m.group("h")) * 3600 + int(m.group("m")) * 60 + int(m.group("s"))
            state.done = {
                "chunks": int(m.group("chunks")),
                "percent": number(m.group("percent")),
                "seconds": seconds,
                "line": line,
                "from": "chat" if "[CHAT]" in line else "console",
            }
            moved = True
        elif (m := UPDATE.search(line)) and m.group("world") == state.world:
            chunks = int(m.group("chunks"))
            if state.chunks is None or chunks > state.chunks:
                moved = True
            state.chunks, state.percent = chunks, number(m.group("percent"))
            state.updates += 1
            state.console_updates += "[CHAT]" not in line
        elif (m := STOPPED.search(line)) and m.group("world") == state.world:
            state.stopped = True
        elif NO_TASKS in line:
            state.no_tasks = True
        else:
            continue
        state.lines.append(line)
    return moved


# Entities.


def selector(radius: int = RADIUS, debris: bool = True) -> str:
    """suite.json world.setup's kill as a selector: every entity but the spared types and the
    tagged ones, within `radius` of the camera; without `debris`, what it takes but debris."""
    spared = SPARED if debris else (*SPARED, *DEBRIS)
    types = ",".join(f"type=!{name}" for name in spared)
    return f"@e[{types},tag=!{TAG},distance=..{radius}]"


def kill_command() -> str:
    return f"/kill {selector()}"


def count_command(target: str) -> str:
    return f"/execute if entity {target}"


def parse_count(answer: dict) -> int:
    """`execute if entity`'s count: "Test passed. Count: N", or 0 for the failure "Test failed";
    anything else is refused, never read as 0."""
    passed = answer["succeeded"] is True and len(answer["messages"]) == 1
    if passed and (m := COUNT.match(answer["messages"][0])):
        return int(m.group("count"))
    if answer["succeeded"] is False and answer["failures"] == [NO_COUNT]:
        return 0
    raise WorldError(f"an entity count answered {answer}; fix: read the mod's command feedback")


def parse_positions(answer: dict) -> list[dict]:
    """`data get entity @s Pos` per entity: the name and position of each, sorted; a failure or
    a message of another form is refused, never read as no mob."""
    if answer["failures"]:
        raise WorldError(f"the positions answered {answer}; fix: read the mod's feedback")
    found = []
    for message in answer["messages"]:
        m = POSITION.match(message)
        if m is None:
            raise WorldError(f"a position answered {message!r}; fix: read the mod's feedback")
        found.append({key: m.group(key) for key in ("name", "x", "y", "z")})
    for item in found:
        for key in ("x", "y", "z"):
            item[key] = float(item[key])
    return sorted(found, key=lambda p: (p["name"], p["x"], p["y"], p["z"]))


def ticks_allowed(view: dict) -> bool:
    """Ticks may be stepped at a view unless its camera stands near the End's dragon fight."""
    if view["dim"] != END:
        return True
    return math.dist((view["x"], view["y"], view["z"]), ARENA) > ARENA_RADIUS


def parse_clock(answer: dict) -> int:
    """`time of <END_CLOCK> query time`'s ticks: "Clock minecraft:the_end is at 6000 tick(s)";
    anything else is refused."""
    if answer["succeeded"] is True and len(answer["messages"]) == 1:
        m = CLOCK.match(answer["messages"][0])
        if m:
            return int(m.group("ticks"))
    raise WorldError(f"the End's clock answered {answer}; fix: read the mod's command feedback")


# The coverage site (plans/m3.md D64).


def coverage_commands() -> list[tuple[str, str]]:
    """The site's build in order, each as (name, command): the floor, the beacon's base, the
    blocks, then the entities."""
    found = [
        (name, f"/fill {a[0]} {a[1]} {a[2]} {b[0]} {b[1]} {b[2]} {block}")
        for name, a, b, block in FILLS
    ]
    found += [(name, f"/setblock {x} {y} {z} {block}") for name, (x, y, z), block, _ in BLOCKS]
    return found + [(item.name, item.summon()) for item in CONTENT]


def block_tests() -> list[tuple[str, str]]:
    """Each block the site must hold, as (name, `execute if block` command): the floor's corners,
    the beacon base's nine, then BLOCKS."""
    (_, (x0, y0, z0), (x1, _, z1), floor), (_, (bx0, by, bz0), (bx1, _, bz1), base) = FILLS
    spots = [("floor", (x, y0, z), floor) for x in (x0, x1) for z in (z0, z1)]
    spots += [
        ("beacon base", (x, by, z), base) for x in range(bx0, bx1 + 1) for z in range(bz0, bz1 + 1)
    ]
    spots += [(name, pos, predicate) for name, pos, _, predicate in BLOCKS]
    return [
        (f"{name} at {x} {y} {z}", f"/execute if block {x} {y} {z} {predicate}")
        for name, (x, y, z), predicate in spots
    ]


def parse_test(answer: dict) -> bool:
    """`execute if block`'s answer: "Test passed" (no count for a block) or the failure "Test
    failed"; anything else is refused, never read as either."""
    if answer["succeeded"] is True and answer["messages"] == [PASSED]:
        return True
    if answer["succeeded"] is False and answer["failures"] == [NO_COUNT]:
        return False
    raise WorldError(f"a block test answered {answer}; fix: read the mod's command feedback")


def sign_command() -> str:
    x, y, z = SIGN
    return f"/data get block {x} {y} {z} front_text.messages[0]"


def coverage_problems(found: dict) -> list[str]:
    """What the site must hold (coverage_counts): one of each content entity, every block, the
    sign's first line. The problems, empty when all hold."""
    problems = [
        f"coverage: {n} {name} counted, not 1" for name, n in found["entities"].items() if n != 1
    ]
    missing = [name for name, held in found["blocks"].items() if not held]
    if missing:
        problems.append(f"coverage: no {', '.join(missing)}")
    x, y, z = SIGN
    if found["sign"] != [SIGN_LINE.format(x=x, y=y, z=z, text=SIGN_TEXT)]:
        problems.append(f"coverage: the sign reads {found['sign']}, not {SIGN_TEXT!r}")
    return problems


# The preparation.


@dataclass
class Prep:
    """One preparation's session: the steps' log and the facts gathered for prep.json."""

    s: Session
    tail: LogTail
    facts: dict

    @property
    def c(self) -> modclient.Client:
        return self.s.client


def command(p: Prep, label: str, text: str, check: bool = True) -> dict:
    """One command through the mod as a recorded step; WorldError when `check` and it failed."""
    answer = p.s.step(
        label,
        lambda: p.c.command(text, check=False),
        lambda a: "; ".join(a["messages"] + a["failures"]) or f"succeeded {a['succeeded']}",
    )
    if check and answer["succeeded"] is not True:
        raise WorldError(f"{label}: /{text.lstrip('/')} did not succeed: {answer}")
    return answer


def gamerules(p: Prep, rules: dict[str, str]) -> dict:
    """The platform's gamerules set (P7) and each read back from the game's own answer. A rule
    already at its value (a prepared snapshot's) answers the failure "Game rule <name> is already
    set to <value>", which counts as set; any other failure stops prep."""
    values = {
        "advanceTime": "false",
        "advanceWeather": "false",
        "spawnMobs": "false",
        "randomTickSpeed": "0",
    }
    found = {}
    for key, value in values.items():
        name = rules[key]
        text = f"/gamerule {name} {value}"
        answer = command(p, f"gamerule {name}", text, check=False)
        already = answer["failures"] == [f"Game rule {name} is already set to {value}"]
        if answer["succeeded"] is not True and not already:
            raise WorldError(f"gamerule {name}: {text} did not succeed: {answer}")
        read = command(p, f"gamerule {name}?", f"/gamerule {name}", check=False)
        text = " ".join(read["messages"])
        if read["failures"] or not text.rstrip(".").endswith(f" {value}"):
            raise WorldError(f"/gamerule {name} reads {read}, not {value}")
        found[name] = value
    return found


def alive(p: Prep) -> None:
    """WorldError when the game has exited."""
    process = p.s.launched.process
    if process.poll() is not None:
        raise WorldError(f"the game exited with code {process.returncode}")


def await_echo(p: Prep, wanted: tuple[str, ...], label: str) -> str:
    """Wait for a line holding one of `wanted` (Chunky's chat answer to a command); the line.
    WorldError naming the last chat lines read when none comes in ECHO_TIMEOUT."""
    seen: list[str] = []
    deadline = time.monotonic() + ECHO_TIMEOUT
    while time.monotonic() < deadline:
        alive(p)
        lines = p.tail.poll()
        for index, line in enumerate(lines):
            if any(text in line for text in wanted):
                p.tail.unread(lines[index + 1 :])  # a task's end may follow in the same read
                return line
            seen.append(line)
        time.sleep(0.25)
    chat = [line for line in seen if "[CHAT]" in line][-3:]
    raise WorldError(
        f"{label}: no {' or '.join(map(repr, wanted))} in latest.log in {ECHO_TIMEOUT:g} s (its "
        f"last chat lines: {chat or 'none'})"
    )


def confirm_end(p: Prep, named: str) -> bool:
    """After "No tasks running.", `chunky continue` tells a finished task from a stopped one: a
    finished task is saved cancelled, so nothing continues; a stopped one continues. True when
    it had finished."""
    command(p, f"chunky continue ({named})", "/chunky continue")
    line = await_echo(p, (NO_CONTINUE, f"Task continuing for {named}."), "chunky continue")
    return NO_CONTINUE in line


def run_task(p: Prep, task: Selection, unfreeze: Callable[[], None]) -> dict:
    """One Chunky task selected, started and awaited (D45): its end from the console's "Task
    finished" line in latest.log (at 100 %), else from `chunky progress` answering "No tasks
    running." and `chunky continue` finding nothing to continue; `chunky progress` asked whenever
    no update came for PROGRESS_ASK. Without progress for STALL frozen, the ticks are unfrozen
    once (`unfreeze`) and the same task awaited; without progress unfrozen too, WorldError
    (plans/m2.md section 7)."""
    named = None
    for text, echo in task.commands():
        command(p, text.lstrip("/"), text)
        line = await_echo(p, (echo,), text)
        if named is None:  # the world's line comes first: Chunky's own name for the world
            m = WORLD_ECHO.search(line)
            named = m.group("world") if m else ""
            if named.split(":")[-1] != task.world.split(":")[-1]:
                raise WorldError(f"/chunky world {task.world}: Chunky answered {line!r}")
    state = TaskState(named or task.world)
    began = time.monotonic()
    command(p, f"chunky start ({task.world})", "/chunky start")
    deadline = time.monotonic() + ECHO_TIMEOUT
    while not state.started:
        alive(p)
        read_task(state, p.tail.poll())
        if state.confirm:
            state.confirm = False
            command(p, "chunky confirm", "/chunky confirm")
        if state.already:
            raise WorldError(f"Chunky already ran a task for {task.world} at the start")
        if time.monotonic() > deadline:
            raise WorldError(f'chunky start: no "Task started in {task.world}" in latest.log')
        time.sleep(0.25)
    last_move = last_line = time.monotonic()
    unfrozen_at: float | None = None
    asked = 0
    while state.done is None:
        alive(p)
        lines = p.tail.poll()
        if read_task(state, lines):
            last_move = time.monotonic()
        if any(UPDATE.search(line) or NO_TASKS in line for line in lines):
            last_line = time.monotonic()
        if state.stopped:
            raise WorldError(f"Chunky stopped the task for {task.world}: {state.lines[-1]}")
        if state.done is not None:
            break
        if state.no_tasks and asked:
            state.no_tasks = False
            if confirm_end(p, state.world):
                state.done = {
                    "chunks": state.chunks,
                    "percent": state.percent,
                    "seconds": round(time.monotonic() - began),
                    "line": f"{NO_TASKS} {NO_CONTINUE}",
                    "from": "chunky progress",
                }
                break
            last_move = time.monotonic()  # a stopped task continues: wait on
        state.no_tasks = False
        elapsed = time.monotonic()
        if elapsed - began > TASK_TIMEOUT:
            raise WorldError(
                f"the {task.world} task ran past {TASK_TIMEOUT:g} s at {state.chunks} chunks "
                f"({state.percent} %); a task without its end read is a stop (plans/m2.md "
                "section 7)"
            )
        if elapsed - last_move > STALL:
            if unfrozen_at is not None:
                raise WorldError(
                    f"no progress for {task.world} in {STALL:g} s frozen nor unfrozen (D45; "
                    f"plans/m2.md section 7): last {state.chunks} chunks ({state.percent} %)"
                )
            p.s.say(f"chunky: no progress for {task.world} in {STALL:g} s frozen: unfreezing (D45)")
            unfreeze()
            unfrozen_at = last_move = time.monotonic()
        if elapsed - last_line > PROGRESS_ASK:
            command(p, f"chunky progress ({task.world})", "/chunky progress")
            asked += 1
            last_line = elapsed
        time.sleep(POLL)
    done = state.done
    if done["from"] == "console" and done["percent"] < COMPLETE:
        raise WorldError(f"the {task.world} task finished at {done['percent']} %: {done['line']}")
    p.s.say(
        f"chunky: {task.world} {task.shape} at ({task.x}, {task.z}) radius {task.radius_x}x"
        f"{task.radius_z}: {done['chunks']} chunks ({done['percent']} %) in {done['seconds']} s, "
        f"its end read from {done['from']}; {state.updates} update lines"
        + (", unfrozen" if unfrozen_at is not None else ", ticks frozen throughout")
    )
    return {
        "world": task.world,
        "shape": task.shape,
        "center": [task.x, task.z],
        "radius": [task.radius_x, task.radius_z],
        "views": list(task.views),
        "done": done,
        "updates": state.updates,
        "updatesFromConsole": state.console_updates,
        "progressAsked": asked,
        "unfrozen": unfrozen_at is not None,
        "wallSeconds": round(time.monotonic() - began, 1),
    }


def count(p: Prep, label: str, target: str) -> int:
    answer = command(p, label, count_command(target), check=False)
    return parse_count(answer)


def at_site(p: Prep, view: dict, label: str) -> None:
    """The camera at a coverage view, its chunks loaded, ready."""
    pose = view_pose(view)
    p.s.step(f"{label}: camera.place {view['id']}", lambda: p.c.camera_place(pose, PLACE_TIMEOUT))
    p.s.step(f"{label}: ready", lambda: p.c.ready(STABLE_FRAMES, 1.0, READY_TIMEOUT))


def place(p: Prep, name: str, text: str) -> list[str]:
    """One build command; its answer's lines. A block already as asked (UNCHANGED) passes, any
    other failure stops prep."""
    answer = command(p, f"coverage: {name}", text, check=False)
    failures = answer["failures"]
    unchanged = bool(failures) and all(failure in UNCHANGED for failure in failures)
    if answer["succeeded"] is not True and not unchanged:
        raise WorldError(f"coverage: {name}: {text} did not succeed: {answer}")
    return answer["messages"] + failures


def coverage_counts(p: Prep, view: dict, label: str) -> dict:
    """What the site holds, the camera at `view`: each content entity counted by its selector,
    each block tested (block_tests), the sign's first line read back."""
    at_site(p, view, f"coverage {label}")
    entities = {
        item.name: count(p, f"coverage {label}: {item.name}", item.selector()) for item in CONTENT
    }
    blocks = {
        name: parse_test(command(p, f"coverage {label}: {name}", text, check=False))
        for name, text in block_tests()
    }
    read = command(p, f"coverage {label}: sign text", sign_command(), check=False)
    return {"entities": entities, "blocks": blocks, "sign": read["messages"] + read["failures"]}


def old_content(p: Prep) -> int:
    """The bench-tagged entities in the site's box, read once a second until all of a built
    site's answer or POSITIONS_WAIT passes: a rebuilt site's entities load after their chunks, as
    the entities role's do (positions); a new site answers none throughout."""
    found = count(p, "coverage: old content", f"@e[tag={TAG},{SITE}]")
    for _ in range(int(POSITIONS_WAIT)):
        if found >= len(CONTENT):
            break
        time.sleep(1.0)
        found = count(p, "coverage: old content", f"@e[tag={TAG},{SITE}]")
    return found


def build_coverage(p: Prep, view: dict) -> dict:
    """The coverage step (plans/m3.md D64), once Chunky has generated the site, the camera at its
    first coverage view (`view`), so its chunks are loaded: any bench-tagged entity in the site's
    box (a rebuilt site's old content, waited for: old_content) killed, KILL_TICKS stepped after so
    a killed mob's body goes, none left; the kill (clear_view) of what generation left there and
    those bodies' drops; the floor,
    blocks and entities through `command` (coverage_commands); then the counts, which must hold
    (coverage_problems). Its facts."""
    at_site(p, view, "coverage")
    old = old_content(p)
    if old:
        if not ticks_allowed(view):
            raise WorldError(f"{view['id']}: old content beside the End's dragon fight")
        command(p, "coverage: kill the old content", f"/kill @e[tag={TAG},{SITE}]")
        p.s.step(f"coverage: ticks.step {KILL_TICKS}", lambda: p.c.ticks_step(KILL_TICKS, 60.0))
        left = count(p, "coverage: old content left", f"@e[tag={TAG},{SITE}]")
        if left:
            raise WorldError(f"coverage: {left} of the old content left after its kill")
    cleared = clear_view(p, view)
    placed = {name: place(p, name, text) for name, text in coverage_commands()}
    counted = coverage_counts(p, view, "built")
    problems = coverage_problems(counted)
    if problems:
        raise WorldError("; ".join(problems) + " (plans/m2.md section 7)")
    return {"old": old, "kill": cleared, "placed": placed, "counts": counted}


def positions(p: Prep, label: str) -> list[dict]:
    """The tagged mobs' names and positions near the camera, read until TAGGED_MOBS answer or
    POSITIONS_WAIT passes (their chunks' entities load after the chunks)."""
    text = f"/execute as @e[tag={TAG},distance=..{RADIUS}] run data get entity @s Pos"
    deadline = time.monotonic() + POSITIONS_WAIT
    while True:
        found = parse_positions(command(p, label, text, check=False))
        if len(found) == TAGGED_MOBS or time.monotonic() > deadline:
            return found
        time.sleep(1.0)


def clear_view(p: Prep, view: dict) -> dict:
    """The kill at a view until CLEAR_COUNTS counts a second apart find nothing it selects. A
    kill that took more than debris is followed by KILL_TICKS stepped ticks (the bodies go), a
    kill of debris alone by none (no new debris then). Beside the End's dragon fight no tick may
    be stepped, so anything but debris counted there stops prep before a kill (the user clears
    it); anything left after KILL_ROUNDS kills stops it too."""
    rounds: list[dict] = []
    clear_counts = kills = 0
    while True:
        found = count(p, f"{view['id']}: count", selector())
        if found == 0:
            clear_counts += 1
            rounds.append({"counted": 0})
            if clear_counts == CLEAR_COUNTS:
                return {
                    "rounds": rounds,
                    "kills": kills,
                    "ticks": sum("ticks" in r for r in rounds),
                }
            time.sleep(1.0)
            continue
        clear_counts = 0
        if kills == KILL_ROUNDS:
            raise WorldError(f"{view['id']}: {found} entities left after {kills} kills: {rounds}")
        others = count(p, f"{view['id']}: count but debris", selector(debris=False))
        if others and not ticks_allowed(view):
            raise WorldError(
                f"{view['id']}: {others} entities the kill selects beside the End's dragon fight, "
                "where a killed mob's body stays until a stepped tick, which spawns the dragon; "
                "nothing was killed; fix: the user clears the view"
            )
        killed = command(p, f"{view['id']}: kill", kill_command(), check=False)
        if killed["failures"] and killed["failures"] != [NO_KILL]:
            raise WorldError(f"{view['id']}: the kill answered {killed}")
        kills += 1
        entry = {"counted": found, "notDebris": others, "kill": killed["messages"]}
        if others:
            p.s.step(
                f"{view['id']}: ticks.step {KILL_TICKS}", lambda: p.c.ticks_step(KILL_TICKS, 60.0)
            )
            entry["ticks"] = KILL_TICKS
        rounds.append(entry)


def sweep(p: Prep, views: dict, suite: dict, previous: str) -> dict:
    """The last kill at every view, the coverage views too, ticks frozen unless a mob turns up:
    what later views' ticks left near earlier ones (cave and rain lie within 110 blocks of
    forest_noon). The kills."""
    found = {}
    for view in record.every_view(views):
        vid = view["id"]
        pose = view_pose(view)
        p.s.step(f"{vid}: sweep camera.place", partial(p.c.camera_place, pose, PLACE_TIMEOUT))
        visual = suite["capture"]["visualSettleS"]
        settle = visual["default"] + (
            visual["addAfterDimensionChange"] if previous != view["dim"] else 0
        )
        p.s.step(f"{vid}: sweep ready", partial(p.c.ready, STABLE_FRAMES, settle, READY_TIMEOUT))
        found[vid] = clear_view(p, view)
        previous = view["dim"]
    return found


def frame(p: Prep, view: dict, raw: Path, resolution: str) -> dict:
    """One reference frame of the placed view under raw/frames/<view>/, checked by its files and
    its PNG's size against the display."""
    answer = p.s.step(
        f"{view['id']}: frames.capture",
        lambda: p.c.frames_capture(raw / FRAMES / view["id"], 1, FRAME_TIMEOUT),
        lambda a: f"{a['verified']['frames']} frame, {a['verified']['bytes']:,} bytes",
    )
    if answer["verified"]["frames"] != 1 or answer["dropped"]:
        raise WorldError(f"{view['id']}: the reference frame was not kept: {answer}")
    first = answer["frames"][0]
    path = Path(answer["verified"]["folder"]) / first["name"]
    found = png_size(path.read_bytes())
    size = f"{found[0]}x{found[1]}" if found else "no PNG"
    if size != resolution:
        raise WorldError(f"{view['id']}: the reference frame is {size}, not {resolution}")
    return {
        "file": path.relative_to(raw).as_posix(),
        "sha256": first["sha256"],
        "size": size,
        "frameIndex": first["frameIndex"],
    }


def call_function(p: Prep, vid: str, label: str) -> dict:
    """A view's function through `/function`; WorldError unless it succeeded (plans/m2.md
    section 7: a view function failing stops the phase, the views are the user's)."""
    fn = FUNCTION.format(namespace=NAMESPACE, id=vid)
    called = command(p, label, f"/function {fn}", check=False)
    if called["succeeded"] is not True:
        raise WorldError(
            f"{vid}: /function {fn} did not succeed ({called}); a view function failing stops "
            "the phase (plans/m2.md section 7: the views are the user's)"
        )
    return called


def prepare_view(
    p: Prep, view: dict, ramped: str | None, previous: str | None, suite: dict, raw: Path
) -> tuple[dict, str | None]:
    """A view prepared: its function (an End view's clock read back: END_CLOCK), camera.place,
    ready, then the overworld's weather ramped by ticks when it changed and a coverage view's own
    `ticks` (with the camera already at the view: never beside the End's dragon fight), the kill,
    the counts, one reference frame with the GUI as D49 says (session.shows_hand). The view's
    facts and the weather the overworld is ramped to after it (None once a kill stepped ticks)."""
    vid = view["id"]
    facts: dict[str, Any] = {"function": call_function(p, vid, f"{vid}: function")}
    if view["dim"] == END:
        asked = command(p, f"{vid}: the End's clock", f"/time of {END_CLOCK} query time", False)
        facts["endClock"] = parse_clock(asked)
        if facts["endClock"] != view["time"]:
            raise WorldError(
                f"{vid}: the End's clock reads {facts['endClock']} after the view's function, not "
                f"{view['time']} (plans/m3.md D56)"
            )
    capture = suite["capture"]
    pose = view_pose(view)
    placed = p.s.step(
        f"{vid}: camera.place",
        lambda: p.c.camera_place(pose, PLACE_TIMEOUT),
        lambda a: f"arrived in {a['arrivedSeconds']:.2f} s",
    )
    problems = modclient.pose_differences(pose, placed["pose"])
    if problems:
        raise WorldError(f"{vid}: camera.place answered {placed['pose']}: {problems}")
    if view["dim"] == OVERWORLD and ramped != view["weather"]:
        n = capture["ticksAfterWeatherChange"]
        p.s.step(f"{vid}: ticks.step {n}", lambda: p.c.ticks_step(n, 60.0))
        ramped = view["weather"]
        facts["weatherTicks"] = n
    ticks = view.get("ticks", 0)
    if ticks:
        if not ticks_allowed(view):
            raise WorldError(f"{vid}: its {ticks} ticks would be stepped beside the dragon fight")
        p.s.step(f"{vid}: ticks.step {ticks}, its own", lambda: p.c.ticks_step(ticks, 60.0))
        facts["viewTicks"] = ticks
        if ramped != view["weather"]:  # stepped toward the view's weather, which is not ramped
            ramped = None
    settle = capture["visualSettleS"].get(vid, capture["visualSettleS"]["default"])
    if previous != view["dim"]:
        settle += capture["visualSettleS"]["addAfterDimensionChange"]
    p.s.step(f"{vid}: ready", lambda: p.c.ready(STABLE_FRAMES, settle, READY_TIMEOUT))
    cleared = clear_view(p, view)
    facts["kill"] = cleared
    if cleared["ticks"] and ramped != view["weather"]:
        ramped = None  # ticks stepped under another weather: the overworld's ramp is unknown
    facts["tagged"] = count(p, f"{vid}: tagged", f"@e[tag={TAG},distance=..{RADIUS}]")
    if view["dim"] == END:
        facts["endCrystals"] = count(
            p, f"{vid}: end crystals", f"@e[type=minecraft:end_crystal,distance=..{RADIUS}]"
        )
        facts["dragons"] = count(p, f"{vid}: dragons", "@e[type=minecraft:ender_dragon]")
        if facts["dragons"]:
            raise WorldError(
                f"{vid}: {facts['dragons']} ender dragon(s) counted; the views say none"
            )
    p.s.step(f"{vid}: ready after the kill", lambda: p.c.ready(STABLE_FRAMES, 1.0, READY_TIMEOUT))
    gui = shows_hand(view)
    if gui:
        command(p, f"{vid}: creative", "/gamemode creative")
        p.s.step(f"{vid}: hud.set hideGui false", lambda: p.c.hud_set(hide_gui=False))
    try:
        facts["frame"] = frame(p, view, raw, suite["display"]["resolution"])
    except BaseException:
        if gui:  # put the GUI and spectator back without hiding the frame's error
            with contextlib.suppress(Exception):
                p.c.hud_set(hide_gui=True)
                p.c.command("/gamemode spectator", check=False)
        raise
    if gui:
        p.s.step(f"{vid}: hud.set hideGui true", lambda: p.c.hud_set(hide_gui=True))
        command(p, f"{vid}: spectator", "/gamemode spectator")
    facts["gui"] = gui
    return facts, ramped


def check_counts(
    views: dict, done: dict, before: list[dict], after: list[dict], cover: dict | None = None
) -> list[str]:
    """What prep must count (plans/m2.md section 7): the entities view's seven tagged mobs, unmoved
    from before the pre-generation; end_dragon's ten end crystals; with a coverage list, the
    site's content after the sweep (`cover`: coverage_counts, plans/m3.md D64). The problems,
    empty when all hold."""
    problems = []
    if views.get(record.COVERAGE):
        if cover is None:
            problems.append("coverage: the site was not counted after the sweep")
        else:
            problems += coverage_problems(cover)
    ids = [v["id"] for v in views["views"]]
    if ENTITIES in ids:
        if done[ENTITIES]["tagged"] != TAGGED_MOBS:
            problems.append(
                f"{ENTITIES}: {done[ENTITIES]['tagged']} tagged mobs, not {TAGGED_MOBS}"
            )
        if len(before) != TAGGED_MOBS or before != after:
            problems.append(f"the tagged mobs moved or changed: before {before}, after {after}")
    if END_DRAGON in ids and done[END_DRAGON].get("endCrystals") != END_CRYSTALS:
        problems.append(
            f"{END_DRAGON}: {done[END_DRAGON].get('endCrystals')} end crystals, not {END_CRYSTALS}"
        )
    return problems


def prep(root: Path, world_id: str, host: RunHost, say: Say, announce: Say) -> dict:
    """`world prep <id>` (docs/plans/m2.md M2.P04): the world prep set installed, the world
    restored and its data pack written, the announced launch, the session as the module docstring
    says, the quit, then `world snapshot`. Facts and every step go to results/raw/<prep>/;
    WorldError names a step that failed (the game ended, no snapshot taken)."""
    from optilux.verbs import install as install_verb  # the verb's module: install's own path

    check_id(world_id)
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    views, _ = record.load_views(root, world_id)
    if platform.WORLD_PREP not in plat.sets:
        raise WorldError(f"{plat.path.name} has no {platform.WORLD_PREP} set; fix: pin Chunky")
    name = f"prep-{world_id}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    raw = root / record.RAW / name
    raw.mkdir(parents=True)
    facts: dict[str, Any] = {"name": name, "world": world_id, "startedAt": now()}

    def write_facts() -> None:
        facts["endedAt"] = now()
        text = json.dumps(facts, indent=1, default=str) + "\n"
        (raw / "prep.json").write_bytes(text.encode("utf-8"))

    try:
        outcome = install_verb.install(root, platform.WORLD_PREP, False, say)
        if not outcome.ok:
            raise WorldError("install: the launch spec moved; fix: `optilux install --refresh`")
        facts["install"] = {"hashes": outcome.hashes, "downloaded": outcome.downloaded}
        say(
            f"install: the {platform.WORLD_PREP} set: {outcome.hashes:,} hashes checked, "
            f"{outcome.downloaded} downloaded"
        )
        facts["restore"] = restore(root, world_id, world_id, host, say)
        live = save_path(root, plat, world_id)
        facts["pack"] = write_pack(live, pack_files(views, plat.data["formats"]["dataPack"]))
        say(
            f"data pack: datapacks/{PACK}/ holds {facts['pack']['files']} files (written "
            f"{len(facts['pack']['written'])}, pruned {facts['pack']['pruned'] or 'none'})"
        )
        tasks = selections(views)
        cover = len(views.get(record.COVERAGE, []))
        announce(
            f"launch (announced): world prep, the {platform.WORLD_PREP} set (bench + Chunky), "
            f"world {world_id}: gamerules, /tick freeze, {len(tasks)} Chunky tasks, "
            + ("the coverage site built and counted, " if cover else "")
            + f"then at each of {len(views['views']) + cover} views the kill and a 4K reference "
            "frame; input.block on from the join to the quit (hands off the game window)"
        )
        launched = launch.launch(root, world_id, platform.WORLD_PREP, True, {}, say, host)
        facts["launch"] = {k: launched.facts[k] for k in ("pid", "join", "mods", "uuid")}
        try:
            client, facts["mod"] = launch.open_mod(launched, root, host, say, raw / REQUESTS)
        except BaseException as error:
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise WorldError(f"{error}; the game was ended ({how})") from None
        s = Session(root, raw, launched, client, host, say)
        p = Prep(s, LogTail(launched.log), facts)
        try:
            session(p, plat, suite, views, tasks, raw)
            s.label = "quit"
            facts["quit"] = launch.quit_mod(client, launched.process, host)
            say(f"quit: exit code {facts['quit']['exitCode']} in {facts['quit']['seconds']:.1f} s")
        except BaseException as error:
            client.close()
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise WorldError(f"{s.label}: {error}; the game was ended ({how})") from None
        finally:
            s.drain()
            facts["steps"] = s.steps
            facts["events"] = s.events
            facts["stray"] = list(client.stray)
            try:  # never in place of the session's own error
                shutil.copyfile(launched.log, raw / "session-latest.log")
                facts["logCheck"] = launch.check_log(raw / REQUESTS, launched.mod_token())
            except (launch.LaunchError, OSError) as error:
                facts["logCheck"] = {"tokenAbsent": False, "problem": str(error)}
        problems = judged(facts, launched.log)
        if problems:
            raise WorldError("; ".join(problems) + "; no snapshot taken")
        facts["snapshot"] = snapshot(root, world_id, world_id, host, say, note=name)
        facts["status"] = "ok"
    except BaseException as error:
        facts["status"] = "failed"
        facts["problem"] = f"{type(error).__name__}: {error}"
        write_facts()
        if isinstance(error, Exception):
            raise WorldError(f"{error}; facts in {shown(raw, root)}/prep.json") from error
        raise
    write_facts()
    return facts


def judged(facts: dict, log: Path) -> list[str]:
    """What fails a prep session beside its steps, as session.record_status judges a run: a
    quit other than exit 0, the token in the request log or the log unchecked, an answer no
    request sent, a hook error, and the mod's hook failures or an Iris load failing outside a
    reload in latest.log (a frame may have rendered without the pack)."""
    problems = []
    if facts["quit"]["exitCode"] != 0:
        problems.append(f"the game quit with exit code {facts['quit']['exitCode']}")
    if facts["logCheck"].get("tokenAbsent") is not True:
        problems.append(f"the request log: {facts['logCheck'].get('problem', 'the token')}")
    if facts["stray"]:
        problems.append(f"the mod sent {len(facts['stray'])} answer(s) to no request")
    if any(e["event"] == "hook.error" for e in facts["events"]):
        problems.append("hook.error in the session")
    lines = helper_lines(log.read_text(encoding="utf-8", errors="replace"))
    facts["helperLog"] = {key: len(found) for key, found in lines.items()}
    if lines["hookFailures"]:
        problems.append(f"the mod logged {len(lines['hookFailures'])} hook failure(s)")
    if lines["irisOutsideReload"]:
        problems.append("Iris failed to load the pack outside a reload")
    return problems


def session(p: Prep, plat: platform.Platform, suite: dict, views: dict, tasks: list, raw: Path):
    """The prep session after hello, in order: the join, the render target, input.block, the
    gamerules, /tick freeze, spectator with a torch in the main hand, the tagged mobs' positions,
    Chunky's tasks, the coverage step (build_coverage), every view (the coverage views last), the
    sweep, the site counted again, the positions again, the camera home, input.block off."""
    s, c, facts = p.s, p.c, p.facts
    s.step("world.wait", lambda: c.world_wait(WORLD_TIMEOUT))
    state = s.step(
        "state", c.state, lambda a: f"{a['gamemode']}, framebuffer {framebuffer_size(a)}"
    )
    display = suite["display"]["resolution"]
    problem = framebuffer_refusal(state, display, display)
    if problem is not None:
        raise WorldError(f"state: {problem}")
    s.step("input.block on", lambda: c.input_block(True))
    try:
        s.step("hud.set hideGui", lambda: c.hud_set(hide_gui=True))
        command(p, "spectator", "/gamemode spectator")
        facts["gamerules"] = gamerules(p, plat.data["gamerules"])
        command(p, "tick freeze", "/tick freeze")
        command(p, "torch", f"/item replace entity @s weapon.mainhand with {TORCH}")
        by_id = {v["id"]: v for v in views["views"]}
        before: list[dict] = []
        if ENTITIES in by_id:
            here = view_pose(by_id[ENTITIES])
            s.step(f"{ENTITIES}: camera.place", lambda: c.camera_place(here, PLACE_TIMEOUT))
            s.step(f"{ENTITIES}: ready", lambda: c.ready(STABLE_FRAMES, 1.0, READY_TIMEOUT))
            before = positions(p, f"{ENTITIES}: positions before")
            if len(before) != TAGGED_MOBS:
                raise WorldError(
                    f"{ENTITIES}: {len(before)} tagged mobs answered, not {TAGGED_MOBS}: {before} "
                    "(plans/m2.md section 7)"
                )
        facts["positionsBefore"] = before
        every = record.every_view(views)
        facts["functions"] = {
            v["id"]: call_function(p, v["id"], f"{v['id']}: function (each answering)")["succeeded"]
            for v in every
        }
        frozen = {"on": True}

        def unfreeze() -> None:
            command(p, "tick unfreeze", "/tick unfreeze")
            frozen["on"] = False

        facts["chunky"] = []
        for task in tasks:
            facts["chunky"].append(run_task(p, task, unfreeze))
            if not frozen["on"]:
                command(p, "tick freeze", "/tick freeze")
                frozen["on"] = True
        cover = views.get(record.COVERAGE, [])
        if cover:
            facts["coverage"] = build_coverage(p, cover[0])
        done: dict[str, dict] = {}
        facts["views"] = done
        ramped: str | None = None
        previous: str | None = OVERWORLD if ENTITIES in by_id or cover else None
        for view in every:
            done[view["id"]], ramped = prepare_view(p, view, ramped, previous, suite, raw)
            previous = view["dim"]
        facts["sweep"] = sweep(p, views, suite, previous or OVERWORLD)
        counted = coverage_counts(p, cover[0], "after the sweep") if cover else None
        facts["coverageAfter"] = counted
        after: list[dict] = []
        if ENTITIES in by_id:
            here = view_pose(by_id[ENTITIES])
            s.step(f"{ENTITIES}: camera.place again", lambda: c.camera_place(here, PLACE_TIMEOUT))
            s.step(f"{ENTITIES}: ready again", lambda: c.ready(STABLE_FRAMES, 1.0, READY_TIMEOUT))
            after = positions(p, f"{ENTITIES}: positions after")
        facts["positionsAfter"] = after
        problems = check_counts(views, done, before, after, counted)
        if problems:
            raise WorldError("; ".join(problems) + " (plans/m2.md section 7)")
        home = view_pose(views["views"][0])
        s.step("camera.place home", lambda: c.camera_place(home, PLACE_TIMEOUT))
    finally:
        try:
            c.input_block_when_free(False, 10.0)
            s.say("input.block off")
        except Exception as error:  # noqa: BLE001 said, never in place of the session's error
            s.say(f"input.block off failed: {error}")
