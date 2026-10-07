"""`optilux pack build` on a fixture tree, in a throwaway repo and on this checkout: the zip holds
exactly the sources under forward-slash names in sorted order with the pinned attributes; two
builds of one tree are byte-identical; the version comes from the newest commit's subject or
--version."""

import hashlib
import os
import zipfile
from pathlib import Path

import pytest
from conftest import commit_file, fresh_repo, git

from optilux import REPO_ROOT, cli
from optilux.verbs import pack

SOURCES = {
    "shader/shaders/shaders.properties": b"# fixture pack\n",
    "shader/shaders/lang/en_us.lang": b"option.X=X\n",
    "shader/shaders/composite.fsh": b"void main() {}\n",
    "LICENSE": b"MIT\n",
    "README.md": b"# Fixture\n",
}
# The archive: shader/ stripped, root files as they are, names sorted.
EXPECTED = {name.removeprefix("shader/"): content for name, content in SOURCES.items()}


def write_tree(root: Path, sources: dict[str, bytes] = SOURCES) -> None:
    for name, content in sources.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)


def unzipped(archive: Path, into: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(into)
    return {
        file.relative_to(into).as_posix(): file.read_bytes()
        for file in into.rglob("*")
        if file.is_file()
    }


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    write_tree(root)
    return root


@pytest.fixture
def packed_repo(tmp_path: Path) -> Path:
    """A throwaway repo holding the fixture tree, its newest commit prefixed 0.00.05."""
    root = fresh_repo(tmp_path / "repo", "m0")
    write_tree(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "0.00.05: Placeholder pack, pack build, license.")
    return root


def test_the_zip_holds_the_sources(tree: Path, tmp_path: Path) -> None:
    built = pack.build(tree, tmp_path / "out", "0.00.05")
    assert built.path == tmp_path / "out" / "optilux-0.00.05.zip"
    assert built.version == "0.00.05"
    assert built.entries == tuple(sorted(EXPECTED))
    assert built.sha256 == hashlib.sha256(built.path.read_bytes()).hexdigest()
    with zipfile.ZipFile(built.path) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == list(built.entries)  # sorted, forward slashes, no dirs
        for info in archive.infolist():
            assert info.date_time == pack.TIMESTAMP
            assert info.compress_type == zipfile.ZIP_DEFLATED
            assert info.create_system == pack.CREATE_SYSTEM
            assert info.external_attr == pack.EXTERNAL_ATTR
    assert unzipped(built.path, tmp_path / "unzipped") == EXPECTED


def test_two_builds_are_byte_identical(tree: Path, tmp_path: Path) -> None:
    first = pack.build(tree, tmp_path / "a", "0.00.05")
    # Source mtimes and the output directory change between the builds; the bytes must not.
    for file in tree.rglob("*"):
        if file.is_file():
            os.utime(file, (1_600_000_000, 1_600_000_000))
    second = pack.build(tree, tmp_path / "b", "0.00.05")
    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.sha256 == second.sha256
    rebuilt = pack.build(tree, tmp_path / "a", "0.00.05")  # overwriting the first in place
    assert rebuilt.sha256 == first.sha256
    (tree / "shader/shaders/shaders.properties").write_bytes(b"# changed\n")
    changed = pack.build(tree, tmp_path / "c", "0.00.05")
    assert changed.sha256 != first.sha256


def test_refuses_a_missing_source(tree: Path, tmp_path: Path) -> None:
    (tree / "LICENSE").unlink()
    with pytest.raises(pack.PackError, match=r"LICENSE is missing under .*; fix: restore it"):
        pack.build(tree, tmp_path / "out", "0.00.05")
    assert not (tmp_path / "out").exists()
    with pytest.raises(pack.PackError, match=r"no shader/ under .*; fix: run inside the Optilux"):
        pack.build(tmp_path / "nowhere", tmp_path / "out", "0.00.05")


def test_refuses_a_pack_file_named_like_a_root_file(tree: Path, tmp_path: Path) -> None:
    (tree / "shader/README.md").write_bytes(b"# clash\n")
    with pytest.raises(pack.PackError, match=r"named like a root file: README.md; fix: rename"):
        pack.build(tree, tmp_path / "out", "0.00.05")


def test_version_from_the_newest_commit(packed_repo: Path) -> None:
    assert pack.version_from_git(packed_repo) == "0.00.05"
    commit_file(packed_repo, "note.txt", b"x\n", "Merge without a prefix")
    with pytest.raises(pack.PackError, match=r"'Merge without a prefix' carries no 0.MM.PP.N "):
        pack.version_from_git(packed_repo)
    empty = fresh_repo(packed_repo.parent / "empty", "main")
    with pytest.raises(pack.PackError, match=r"finds no commit in .*; fix: commit, or give"):
        pack.version_from_git(empty)


def test_check_version() -> None:
    assert pack.check_version("0.01.13.0") == "0.01.13.0"
    assert pack.check_version("0.01.12") == "0.01.12"  # releases before 0.01.12.1
    for bad in ("dev", "0.1.2", "1.00.00", "0.00.05: x", "v0.00.05", "0.01.12.01", "0.01.12."):
        with pytest.raises(
            pack.PackError, match=r"is not of the form 0.MM.PP.N; fix: give --version"
        ):
            pack.check_version(bad)


def test_cli_builds_from_the_git_log_into_build(
    packed_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pack, "REPO_ROOT", packed_repo)
    assert cli.main(["pack", "build"]) == 0
    out = capsys.readouterr().out
    written = packed_repo / "build" / "optilux-0.00.05.zip"
    digest = hashlib.sha256(written.read_bytes()).hexdigest()
    assert out == (
        "optilux pack build: wrote build/optilux-0.00.05.zip (5 entries, version 0.00.05)\n"
        f"sha256: {digest}\n"
    )
    assert unzipped(written, packed_repo.parent / "unzipped") == EXPECTED


def test_cli_takes_out_and_version(
    packed_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(pack, "REPO_ROOT", packed_repo)
    out_dir = tmp_path / "elsewhere"
    assert cli.main(["pack", "build", "--out", str(out_dir), "--version", "0.00.09"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"optilux pack build: wrote {out_dir.as_posix()}/optilux-0.00.09.zip (5")
    assert (out_dir / "optilux-0.00.09.zip").is_file()
    assert cli.main(["pack", "build", "--out", str(out_dir), "--version", "dev"]) == 1
    err = capsys.readouterr().err
    assert err == (
        "optilux pack build: version 'dev' is not of the form 0.MM.PP.N; "
        "fix: give --version 0.MM.PP.N\n"
    )


def test_this_checkout_builds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pack", "build", "--out", str(tmp_path), "--version", "0.00.05"]) == 0
    assert "sha256: " in capsys.readouterr().out
    content = unzipped(tmp_path / "optilux-0.00.05.zip", tmp_path / "unzipped")
    assert content["LICENSE"] == (REPO_ROOT / "LICENSE").read_bytes()
    assert content["README.md"] == (REPO_ROOT / "README.md").read_bytes()
    assert (
        content["shaders/shaders.properties"]
        == (REPO_ROOT / "shader/shaders/shaders.properties").read_bytes()
    )
    assert b"inspired by Complementary Shaders by EminGT" in content["README.md"]
    assert content["LICENSE"].startswith(b"MIT License\n\nCopyright (c) 2026 Joseph Gibson\n")


def test_pack_needs_a_target(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["pack"])
    assert caught.value.code == 1 and "optilux pack --help" in capsys.readouterr().err
    assert "pack" in [verb.name for verb in cli.VERBS]
