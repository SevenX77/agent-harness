"""The containment primitive itself, at the boundaries the route tests cannot reach.

The route tests are the ones that matter — they prove a request is refused. These
cover the two edges a request cannot demonstrate on every platform: a symlink
escape (creating one needs a privilege Windows accounts often lack, so the route
test skips there) and the prefix-vs-component distinction, which no realistic
request happens to exercise but which is the classic way this check is written
wrong.
"""

from __future__ import annotations

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
