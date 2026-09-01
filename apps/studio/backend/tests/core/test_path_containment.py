"""The containment primitive itself, at the boundaries the route tests cannot reach.

The route tests are the ones that matter — they prove a request is refused. These
cover the edges a request cannot demonstrate, or cannot demonstrate on every
platform: a symlink escape (creating one needs a privilege Windows accounts often
lack, so the route test skips there); the prefix-vs-component distinction, which
no realistic request exercises but which is the classic way this check is written
wrong; and the ORDER of the gates, where what matters is that a filesystem call
did NOT happen — an absence no response body can show.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.core.path_containment import (
    PathEscapesDirectory,
    is_workspace_entry_name,
    resolve_inside,
    resolve_within_roots,
)


@pytest.mark.parametrize(
    "name",
    ["case-a", "case-a.json", "chapter_001", "A", "a-b_c.d"],
)
def test_a_bare_name_is_a_workspace_entry_name(name: str) -> None:
    assert is_workspace_entry_name(name)


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "./a", "../a", "a/b", "a\\b", ".hidden", "-leading", "_leading", "a" * 101],
)
def test_anything_that_could_address_elsewhere_is_not_a_workspace_entry_name(name: str) -> None:
    assert not is_workspace_entry_name(name)


def test_resolve_inside_returns_the_child_it_names(tmp_path: Path) -> None:
    assert resolve_inside(tmp_path, "case.json") == (tmp_path / "case.json").resolve()


def test_resolve_inside_refuses_a_name_that_climbs_out(tmp_path: Path) -> None:
    with pytest.raises(PathEscapesDirectory):
        resolve_inside(tmp_path, "../case.json")


def test_resolve_inside_answers_for_a_path_that_does_not_exist(tmp_path: Path) -> None:
    """A read and a write are entitled to the same verdict.

    ``strict=True`` would make the check depend on the file already being there,
    which silently stops checking anything the first time it guards a create.
    """
    assert resolve_inside(tmp_path, "not-there-yet.json") == (tmp_path / "not-there-yet.json").resolve()


def test_resolve_inside_refuses_a_symlink_pointing_out(tmp_path: Path) -> None:
    """The case the NAME rule cannot see: a well-formed name, resolving outside."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text("{}", encoding="utf-8")
    inside = tmp_path / "inside"
    inside.mkdir()
    try:
        (inside / "escape.json").symlink_to(secret)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform privilege
        pytest.skip(f"this platform/account cannot create symlinks: {exc}")

    with pytest.raises(PathEscapesDirectory):
        resolve_inside(inside, "escape.json")


def test_resolve_within_roots_accepts_a_path_inside_a_root(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "alpha").mkdir(parents=True)

    assert resolve_within_roots(str(root / "alpha"), [root]) == (root / "alpha").resolve()


def test_resolve_within_roots_refuses_a_sibling_that_merely_shares_a_prefix(
    tmp_path: Path,
) -> None:
    """``/skills-evil`` is not inside ``/skills``.

    A string ``startswith`` comparison says it is, which is why the check
    compares path COMPONENTS (``Path.is_relative_to``) rather than characters.
    """
    root = tmp_path / "skills"
    root.mkdir()
    sibling = tmp_path / "skills-evil"
    sibling.mkdir()

    with pytest.raises(PathEscapesDirectory):
        resolve_within_roots(str(sibling), [root])


def test_resolve_within_roots_refuses_a_relative_path(tmp_path: Path) -> None:
    """Resolving it would mean "wherever this server was launched from"."""
    with pytest.raises(PathEscapesDirectory):
        resolve_within_roots("relative/dir", [tmp_path])


def test_resolve_within_roots_accepts_a_path_inside_any_root(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()

    assert resolve_within_roots(str(second), [first, second]) == second.resolve()


@pytest.mark.parametrize(
    "unc_path",
    [
        r"\\attacker\share\x",
        "//attacker/share/x",
        r"\\?\C:\Windows\win.ini",
        r"\\.\NUL",
        r"\\attacker\share",
        "//?/UNC/attacker/share/x",
    ],
)
def test_resolve_within_roots_refuses_a_unc_or_device_path(tmp_path: Path, unc_path: str) -> None:
    """A UNC name is refused, and refused for being a UNC name."""
    with pytest.raises(PathEscapesDirectory) as excinfo:
        resolve_within_roots(unc_path, [tmp_path])

    assert "UNC" in excinfo.value.reason


def test_a_unc_path_is_refused_without_touching_the_filesystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal has to happen BEFORE the resolve, not after it.

    ``ntpath.realpath`` walks a UNC path component by component, and each
    component is an SMB request to the host in the path — one that can carry an
    NTLM handshake. A check that resolves first and rejects afterwards has
    already reached out to the attacker's machine and leaked a credential
    exchange by the time it says "no", which is why this asserts the ABSENCE of
    the call rather than only the verdict.

    Patching ``Path.resolve`` to raise is what makes the assertion real: a fix
    that reorders the gate passes, and any fix that resolves first fails here
    with the marker rather than with ``PathEscapesDirectory``.
    """

    def _forbidden_resolve(self: Path, strict: bool = False) -> Path:
        raise AssertionError(f"resolve() was called before the UNC gate, on {self}")

    monkeypatch.setattr(Path, "resolve", _forbidden_resolve)

    with pytest.raises(PathEscapesDirectory):
        resolve_within_roots(r"\\attacker\share\x", [tmp_path])


def test_resolve_within_roots_refuses_an_empty_path(tmp_path: Path) -> None:
    """``Path("")`` is ``.`` — the process working directory, which is not an answer."""
    with pytest.raises(PathEscapesDirectory) as excinfo:
        resolve_within_roots("   ", [tmp_path])

    assert "empty" in excinfo.value.reason


@pytest.mark.skipif(
    os.name != "nt",
    reason="drive letters only exist on Windows; POSIX anchors are all '/' and cannot differ in case",
)
@pytest.mark.parametrize("drive_case", ["lower", "upper"])
def test_the_same_drive_spelled_either_case_is_the_same_volume(
    tmp_path: Path,
    drive_case: str,
) -> None:
    """``d:\\`` and ``D:\\`` are ONE volume, so the gate must accept both.

    ``Path.anchor`` is a plain ``str``, so comparing two of them was a
    case-SENSITIVE comparison — while ``Path.resolve()`` normalises the drive to
    upper case and the caller's spelling is whatever they typed. A request, or a
    skill-index entry, holding a lower-case drive was therefore refused as "not
    on a volume we manage": a legitimate save turned into a 422 by the case of
    one letter.

    Both spellings are exercised because the fix has to be a NORMALISATION. A
    one-way ``.upper()`` would pass this half and then fail the mirror case
    below, where the oddly-spelled side is the root.
    """
    inside = tmp_path / "skill"
    inside.mkdir()
    raw = str(inside)
    drive = raw[:2].lower() if drive_case == "lower" else raw[:2].upper()

    assert resolve_within_roots(drive + raw[2:], [tmp_path]) == inside.resolve()


@pytest.mark.skipif(
    os.name != "nt",
    reason="drive letters only exist on Windows; POSIX anchors are all '/' and cannot differ in case",
)
@pytest.mark.parametrize("drive_case", ["lower", "upper"])
def test_a_differently_cased_root_drive_still_accepts_the_path(
    tmp_path: Path,
    drive_case: str,
) -> None:
    """The mirror case: the ROOT is the oddly-spelled side.

    Honestly labelled — this direction passes even WITHOUT the normalisation,
    because the roots go through ``resolve()`` and that upper-cases the drive on
    the way. Only the candidate side, which is deliberately not resolved yet, can
    reach the comparison oddly cased, and that is the half that was broken.

    Kept anyway: it pins the property to the comparison rather than to a side
    effect of ``resolve()``, so if root resolution ever stops normalising, this
    fails here instead of in a user's 422.
    """
    inside = tmp_path / "skill"
    inside.mkdir()
    raw_root = str(tmp_path)
    drive = raw_root[:2].lower() if drive_case == "lower" else raw_root[:2].upper()

    assert resolve_within_roots(str(inside), [Path(drive + raw_root[2:])]) == inside.resolve()


@pytest.mark.skipif(
    os.name != "nt",
    reason="the anchor gate has only one possible answer on POSIX: every absolute path is /",
)
def test_resolve_within_roots_refuses_a_path_on_another_drive(tmp_path: Path) -> None:
    """A path on a different drive is out before the link-following resolve.

    This is the gate's whole purpose on Windows, where a drive letter can be a
    mapped network share — resolving such a path reaches the network exactly the
    way a UNC name does. The chosen drive need not exist: the gate is lexical, so
    "does not exist" and "is not ours" reach the same verdict without a syscall,
    which is what the second assertion pins down.
    """
    other_drive = "Z:" if tmp_path.drive.upper() != "Z:" else "Y:"

    with pytest.raises(PathEscapesDirectory) as excinfo:
        resolve_within_roots(rf"{other_drive}\stolen\GRAPH.md", [tmp_path])

    assert "volume" in excinfo.value.reason
    assert other_drive.lower() in str(excinfo.value).lower()
