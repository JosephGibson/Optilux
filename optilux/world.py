"""World snapshots and their restore (docs/measurement.md#session, docs/plans/m2.md M2.P04,
D44).

A snapshot is snapshots/<id>/, a copy of the game's saves/<world>/, beside it <id>.manifest (one
`<sha256>  <path>` line per file, its sha256 the tree hash: run-record.md#identity) and <id>.json
(the hash, the file count, the bench player's uuid from players/data/, F8). `restore` makes the
live world equal to its snapshot in place (D44): files that differ copied back, files the
snapshot lacks deleted, the live tree hashed equal after. Both refuse while a game runs from
runtime/<platform>/.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Protocol

from optilux import launch, platform, record
from optilux.session import now
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
