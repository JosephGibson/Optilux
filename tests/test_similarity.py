"""optilux.similarity and `verify similarity` (plans/m3.md D55): the normalized tokens, the
winnowing guarantee on fixtures (a renamed copy of t tokens found through one shared
fingerprint, nothing under k, a copied macro body, one match per run), the verb against a fake
reference copy, its controls and the committed threshold."""

import json
import random
import shutil
from pathlib import Path

import pytest
from conftest import similarity_home

from optilux import REPO_ROOT, cli, record, similarity
from optilux.verbs import verify

# Fixture token streams: a shared run drawn from SHARED; each side's context from its own
# vocabulary, disjoint from the other's and from SHARED, so a run ends where the context starts.
SHARED = ("float", "ID", "=", "NUM", ";", "vec3", "(", ")", ",", "return", "{", "}", "if", "<")
SHARED += ("-", "BOOL")
CANDIDATE_CONTEXT = ("+", "%", "&&")
REFERENCE_CONTEXT = ("/", "^", "||")


def render(tokens: list[str], prefix: str, rng: random.Random, comments: bool) -> str:
    """GLSL text whose normalized tokens are `tokens`: identifiers named from prefix, numbers
    and blanks drawn by rng, comments between tokens when asked."""
    numbers = ("0.5", "3", "1e-3", "2.0f", "0x1Fu", ".25")
    pieces = []
    for index, item in enumerate(tokens):
        if item == similarity.IDENTIFIER:
            pieces.append(f"{prefix}{index}")
        elif item == similarity.NUMBER:
            pieces.append(rng.choice(numbers))
        elif item == similarity.BOOLEAN:
            pieces.append(rng.choice(("true", "false")))
        else:
            pieces.append(item)
        blanks = (" ", "\n", "  ", "\t", " /* note */ ", " // note\n") if comments else (" ", "\n")
        pieces.append(rng.choice(blanks))
    return "".join(pieces)


def seeded(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 fixture streams, no secret


def context(rng: random.Random, vocabulary: tuple[str, ...], count: int) -> list[str]:
    return [rng.choice(vocabulary) for _ in range(count)]


def pair(rng: random.Random, run: list[str], before: int = 15) -> tuple[list[str], list[str]]:
    """Candidate and reference token streams sharing `run` alone, at index `before`."""
    candidate = context(rng, CANDIDATE_CONTEXT, before) + run
    reference = context(rng, REFERENCE_CONTEXT, before) + run
    return (
        candidate + context(rng, CANDIDATE_CONTEXT, 15),
        reference + context(rng, REFERENCE_CONTEXT, 15),
    )


def sources(
    rng: random.Random, candidate: list[str], reference: list[str]
) -> tuple[similarity.Source, similarity.Source]:
    """Both streams rendered and tokenized: the candidate renamed, renumbered and commented."""
    cand = similarity.tokenize("cand.fsh", render(candidate, "alpha", rng, comments=True))
    ref = similarity.tokenize("ref.glsl", render(reference, "beta", rng, comments=False))
    assert cand.tokens == tuple(candidate) and ref.tokens == tuple(reference)
    return cand, ref


def shared_fingerprints(cand: similarity.Source, ref: similarity.Source, k: int, w: int) -> set:
    return set(similarity.fingerprints(cand, k, w)) & set(similarity.fingerprints(ref, k, w))


def spans(found: list[similarity.Match]) -> list[tuple[int, int, int]]:
    return [(m.candidate_start, m.reference_start, m.length) for m in found]


def test_tokens_drop_comments_blanks_and_directives_and_reduce_names_and_literals() -> None:
    text = (
        "#version 330 core\r\n"
        "// a comment\r\n"
        "uniform vec3 sunDir; /* a block\r\n"
        " comment */ float x = 1.5e-3 + 0x1Fu;\r\n"
        "  #ifdef FOO\r\n"
        "bool b = true; mat3x4 m; sampler2DShadow s; usampler2DArray u; float y = \\\n"
        " .5; a # b\n"
        "#endif\n"
    )
    found = similarity.tokenize("x.fsh", text)
    assert " ".join(found.tokens) == (
        "uniform vec3 ID ; float ID = NUM + NUM ; bool ID = BOOL ; mat3x4 ID ; "
        "sampler2DShadow ID ; usampler2DArray ID ; float ID = NUM ; ID # ID"
    )
    assert found.lines[:9] == (3, 3, 3, 3, 4, 4, 4, 4, 4)
    assert found.lines[-7:] == (6, 6, 7, 7, 7, 7, 7)  # a continuation still ends its line


def test_a_defines_replacement_is_kept_without_its_name_and_parameters() -> None:
    def tokens(text: str) -> str:
        return " ".join(similarity.tokenize("x.glsl", text).tokens)

    assert tokens("#define F(x, y) ((x) * 2.0) // c\n") == "( ( ID ) * NUM )"
    assert tokens("#define G (1.0)\n") == "( NUM )"  # object-like: the blank keeps the paren
    assert tokens("# define H\n#define\n#define 3 4\n") == ""
    assert tokens("#define K /* a\n */ 3 * 2\nfloat") == "NUM * NUM float"  # a comment spans it
    assert tokens('#include "/lib/a.glsl"\n#if A > 2\n#endif') == ""
    assert similarity.tokenize("x.glsl", "#define M(a) \\\n  a + \\\n  1\n").lines == (2, 2, 3)


def test_a_define_whose_replacement_is_a_value_gives_no_token() -> None:
    """An options list is values, which would line up into runs of NUM any pack's options
    match (Unbound's lib/common.glsl: 111 in a row)."""
    options = "".join(
        f"#define OPTION_{n} {n % 4} //[0 1 2 3]\n#define FLAG_{n}\n" for n in range(100)
    )
    signed = "#define A -1 //[-1 1]\n#define B +2.0\n#define C true\n#define D OTHER_NAME\n"
    assert similarity.tokenize("settings.glsl", options + signed).tokens == ()
    kept = "#define E (1.0)\n#define F 1 + 2\n#define G -x\n#define H(x) x * 2\n"
    assert " ".join(similarity.tokenize("x.glsl", kept).tokens) == "( NUM ) NUM + NUM - ID ID * NUM"


def test_winnowing_keeps_each_windows_rightmost_minimum_once() -> None:
    assert similarity.winnow([3, 1, 1, 2], 2) == [1, 2]
    assert similarity.winnow([5, 4, 3], 4) == []  # no full window
    assert similarity.winnow([2, 2, 2], 1) == [0, 1, 2]
    assert similarity.winnow([1, 5, 6, 7, 0], 3) == [0, 1, 4]


def test_a_renamed_copy_of_t_tokens_is_found_through_its_one_shared_fingerprint() -> None:
    """P10's guarantee and the extension: the run of exactly t tokens shares one fingerprint,
    which covers k tokens, and the match reported is the whole run."""
    k, t = 5, 12
    w = t - k + 1
    for seed in range(500):
        rng = seeded(seed)
        run = [rng.choice(SHARED) for _ in range(t)]
        if len({tuple(run[i : i + k]) for i in range(w)}) < w:
            continue  # a repeated k-gram could share a fingerprint off the run's diagonal
        cand, ref = sources(rng, *pair(rng, run))
        if len(shared_fingerprints(cand, ref, k, w)) == 1:
            break
    else:
        pytest.fail("no seed in 500 gave one shared fingerprint")
    assert spans(similarity.matches([cand], [ref], k, w)) == [(15, 15, t)]


def test_every_run_of_t_tokens_is_found_whole() -> None:
    k, t = 5, 12
    for seed in range(200):
        rng = seeded(seed)
        run = [rng.choice(SHARED) for _ in range(t)]
        cand, ref = sources(rng, *pair(rng, run))
        found = similarity.matches([cand], [ref], k, t - k + 1)
        assert (15, 15, t) in spans(found), seed


def test_no_run_under_k_is_matched_even_over_every_kgram() -> None:
    k = 6
    for seed in range(100):
        rng = seeded(seed)
        cand, ref = sources(rng, *pair(rng, [rng.choice(SHARED) for _ in range(k - 1)]))
        assert similarity.matches([cand], [ref], k, 1) == [], seed
    rng = seeded(0)
    cand, ref = sources(rng, *pair(rng, [rng.choice(SHARED) for _ in range(k)]))
    assert (15, 15, k) in spans(similarity.matches([cand], [ref], k, 1))


def test_a_copied_macro_body_is_found_in_a_renamed_function() -> None:
    reference = (
        "#version 330 core\n"
        "#define BLEND(base, glow) \\\n"
        "    (base * max(dot(glow, vec3(0.2, 0.7, 0.1)), 0.0) \\\n"
        "    + glow * clamp(base.r - 0.5, 0.0, 1.0))\n"
        "uniform float frameTime;\n"
    )
    candidate = (
        "vec3 mixLight(vec3 albedo, vec3 emit) {\n"
        "    return (albedo * max(dot(emit, vec3(0.3, 0.6, 0.1)), 0.0) + emit * "
        "clamp(albedo.r - 0.25, 0.0, 1.0));\n"
        "}\n"
    )
    ref = similarity.tokenize("lib/blend.glsl", reference)
    cand = similarity.tokenize("final.fsh", candidate)
    found = similarity.matches([cand], [ref], 5, 30 - 5 + 1)
    assert [(m.length, m.candidate_lines, m.reference_lines) for m in found] == [
        (37, (2, 2), (3, 4))
    ]
    assert found[0].text() == "final.fsh:2-2 matches lib/blend.glsl:3-4 (37 tokens)"


def test_the_fingerprints_of_one_run_give_one_match_and_two_runs_two() -> None:
    k, t = 5, 12
    w = t - k + 1
    rng = seeded(7)
    run = [rng.choice(SHARED) for _ in range(3 * t)]
    cand, ref = sources(rng, *pair(rng, run))
    assert len(shared_fingerprints(cand, ref, k, w)) > 1
    assert spans(similarity.matches([cand], [ref], k, w)) == [(15, 15, 3 * t)]
    first, second = run[:20], run[21:]
    split = [*first, "+", *second]  # one token apart in the candidate only
    candidate, reference = pair(rng, run)
    candidate[15 : 15 + len(run)] = split
    cand, ref = sources(rng, candidate, reference)
    assert sorted(spans(similarity.matches([cand], [ref], k, w))) == [(15, 15, 20), (36, 36, 15)]


def test_equal_hashes_over_different_tokens_are_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(similarity, "kgram_hashes", lambda tokens, k: [0] * (len(tokens) - k + 1))
    cand = similarity.tokenize("a.fsh", "float a = 1.0; vec3 b = c;")
    ref = similarity.tokenize("b.fsh", "if (x < y) { return; }")
    assert similarity.matches([cand], [ref], 3, 1) == []


def test_only_glsl_files_are_read() -> None:
    texts = {"s/a.fsh": "float a;", "s/b.glsl.frag": "float b;", "s/shaders.properties": "x=1"}
    assert [source.name for source in similarity.sources(texts)] == ["s/a.fsh", "s/b.glsl.frag"]


# The verb.

COPIED = (
    "#define BLEND(base, glow) \\\n"
    "    (base * max(dot(glow, vec3(0.2, 0.7, 0.1)), 0.0) \\\n"
    "    + glow * clamp(base.r - 0.5, 0.0, 1.0))\n"
)
RENAMED = (
    "vec3 mixLight(vec3 albedo, vec3 emit) {\n"
    "    return (albedo * max(dot(emit, vec3(0.3, 0.6, 0.1)), 0.0)\n"
    "        + emit * clamp(albedo.r - 0.25, 0.0, 1.0));\n"
    "}\n"
)


def test_the_check_flags_a_copy_naming_both_files_and_lines(tmp_path: Path) -> None:
    home = similarity_home(tmp_path / "home", {"shaders/lib/blend.glsl": COPIED}, 5, 30)
    texts = {"shader/shaders/final.fsh": RENAMED, "shader/shaders/shaders.properties": "x=1\n"}
    found = verify.check_similarity(home, texts)
    assert (found.files, found.references, found.k, found.t) == (1, 1, 5, 30)
    assert [verify.flagged_text(m, found.t) for m in found.flagged] == [
        "shader/shaders/final.fsh:2-3 matches reference/studied-1/shaders/lib/blend.glsl:2-3 "
        "(37 tokens), t 30; fix: write it fresh in your own structure (docs/shader.md#policy)"
    ]
    assert verify.check_similarity(home, {"shader/shaders/final.fsh": "float a;"}).flagged == []
    longer = verify.check_similarity(
        similarity_home(tmp_path / "strict", {"b.glsl": COPIED}, 5, 38), texts
    )
    assert longer.flagged == []  # 37 tokens under t 38


def test_the_check_refuses_a_copy_missing_or_off_its_pin(tmp_path: Path) -> None:
    home = similarity_home(tmp_path / "home", {"shaders/lib/blend.glsl": COPIED}, 5, 30)
    (home / "reference" / "studied-1" / "shaders" / "lib" / "blend.glsl").write_text("float a;")
    with pytest.raises(
        verify.SimilarityError, match=r"differs from its pin .* `uv run optilux install`"
    ):
        verify.check_similarity(home, {})
    shutil.rmtree(home / "reference")
    with pytest.raises(
        verify.SimilarityError, match="studied-1/ is missing; fix: `uv run optilux install`"
    ):
        verify.check_similarity(home, {})


@pytest.mark.parametrize("k, t", [(0, 5), (6, 5), (5, "30"), (None, 30)])
def test_the_check_refuses_k_and_t_off_their_rule(tmp_path: Path, k: object, t: object) -> None:
    home = similarity_home(tmp_path / "home", {"a.glsl": COPIED}, 5, 30)
    path = home / "config" / "similarity.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "k": k, "t": t}))
    with pytest.raises(verify.SimilarityError, match="k <= t"):
        verify.check_similarity(home, {})


def test_the_check_refuses_a_pin_it_cannot_read_and_a_tree_it_cannot_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = similarity_home(tmp_path / "home", {"a.glsl": COPIED}, 5, 30)
    config = verify.similarity_config(home)
    for studied in (None, {**config["studied"], "folder": "../up"}, {"folder": "studied-1"}):
        text = json.dumps({**config, "studied": studied})
        with pytest.raises(verify.SimilarityError, match="studied: no plain folder"):
            verify.parse_config(text)
    with pytest.raises(verify.SimilarityError, match="control: no plain folder"):
        verify.control_figures(home)  # no control pinned

    def linked(folder: Path) -> tuple[str, int]:
        raise record.RecordError(f"{folder}: a link; fix: copy the world as plain files")

    monkeypatch.setattr(record, "tree_hash", linked)
    with pytest.raises(verify.SimilarityError, match=r"a link; .*fix: delete the folder and run"):
        verify.check_similarity(home, {})


def test_the_verb_exits_1_on_a_copy_under_shader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = similarity_home(tmp_path / "home", {"shaders/lib/blend.glsl": COPIED}, 5, 30)
    monkeypatch.setattr(verify, "REPO_ROOT", home)
    assert cli.main(["verify", "similarity"]) == 0
    assert "0 GLSL files under shader/ (0 tokens) against 1 of" in capsys.readouterr().out
    (home / "shader" / "shaders").mkdir(parents=True)
    (home / "shader" / "shaders" / "final.fsh").write_text(RENAMED)
    assert cli.main(["verify", "similarity"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("shader/shaders/final.fsh:2-3 matches reference/studied-1/")
    assert out[1].endswith("(k 5, t 30): 1 matches of 30 tokens or more")
    assert cli.main(["verify", "similarity", "--json"]) == 1
    found = json.loads(capsys.readouterr().out)
    assert not found["ok"] and found["flagged"][0]["length"] == 37
    shutil.rmtree(home / "reference")
    assert cli.main(["verify", "similarity"]) == 1
    assert "is missing; fix: `uv run optilux install`" in capsys.readouterr().out


def control_home(tmp_path: Path, controls: dict | None) -> Path:
    """A home whose studied copy holds the blend macro and a short file, and whose control pack
    shares 8 tokens with it."""
    files = {"lib/blend.glsl": COPIED, "lib/short.glsl": "float a = 1.0;\n"}
    home = similarity_home(tmp_path / "home", files, 5, 30)
    folder = home / "reference" / "control-1"
    folder.mkdir(parents=True)
    (folder / "x.fsh").write_text("void main() { float q = max(dot(n, vec3(a))); }\n")
    digest, count = record.tree_hash(folder)
    path = home / "config" / "similarity.json"
    config = json.loads(path.read_text())
    config["control"] = {"folder": "control-1", "treeSha256": digest, "files": count}
    if controls is not None:
        config["controls"] = controls
    path.write_text(json.dumps(config))
    return home


def test_the_controls_measure_both_figures_and_hold_the_rule(tmp_path: Path) -> None:
    home = control_home(tmp_path, None)
    figures = verify.control_figures(home)
    assert figures == {
        "self": {"files": 1, "flagged": 1},
        "control": {
            "longest": 8,
            "at": "reference/control-1/x.fsh:1-1 matches reference/studied-1/lib/blend.glsl:2-2 "
            "(8 tokens)",
        },
    }
    config = verify.similarity_config(home)
    problems = verify.control_problems(figures, config)
    assert len(problems) == 4 and all("fix: record the measured figure" in p for p in problems)
    assert verify.control_problems(figures, {**config, "controls": figures}) == []
    over = verify.control_problems(figures, {**config, "t": 8, "controls": figures})
    assert over == [
        "the control pack shares 8 tokens with the studied copy, not under t 8: a rule change "
        "is the user's (plans/m3.md section 7)"
    ]
    missed = {**figures, "self": {"files": 2, "flagged": 1}}
    assert (
        "flags 1 of its 2 files of 30 tokens or more" in verify.control_problems(missed, config)[0]
    )


def test_the_verbs_controls_exit_0_when_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = control_home(tmp_path, None)
    monkeypatch.setattr(verify, "REPO_ROOT", home)
    assert cli.main(["verify", "similarity", "--controls"]) == 1
    assert "4 problems" in capsys.readouterr().out
    control_home(tmp_path / "again", verify.control_figures(home))
    monkeypatch.setattr(verify, "REPO_ROOT", tmp_path / "again" / "home")
    assert cli.main(["verify", "similarity", "--controls"]) == 0
    assert (
        capsys.readouterr().out.splitlines()[0] == "self: 1 of 1 files of 30 tokens or more flagged"
    )


def test_the_committed_threshold_keeps_its_rule() -> None:
    """config/similarity.json (D55) as recorded: k <= t, t above the control pack's recorded
    longest run, every studied file of t tokens or more flagged. Whether the figures are current
    needs the copies, which CI lacks: `verify similarity --controls` answers that."""
    config = verify.similarity_config(REPO_ROOT)
    assert verify.control_problems(config["controls"], config) == []
    assert config["controls"]["self"]["files"] > 0
