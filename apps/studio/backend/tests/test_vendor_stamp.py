"""The vendor snapshot must be able to say what it was built from.

`apps/studio/tauri/vendor/site-packages` is a frozen copy of the two SDK
packages that the desktop app's Python sidecar imports at runtime -- in dev
builds too. On a developer's machine the launcher gate
(`apps/studio/tauri/scripts/ensure_vendor.js`) can answer "is this snapshot
stale?" by comparing it against the working tree. On a user's machine there is
no working tree, so the snapshot is anonymous: nothing in it, or in a bug report
about it, can name the source state it came from.

These tests cover the stamp `build_vendor.py` writes to close that gap, and the
one property that makes it worth writing: the digest is a function of file
CONTENT only, so the same sources produce the same digest on any machine, in any
directory, at any time.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_VENDOR_PATH = REPO_ROOT / "apps" / "studio" / "backend" / "scripts" / "build_vendor.py"


def load_build_vendor() -> ModuleType:
    """Import the vendoring script by path.

    It lives under `scripts/`, which is deliberately not an importable package
    (nothing in the app may depend on a build script), so there is no module
    name to import it by.
    """
    spec = importlib.util.spec_from_file_location("studio_build_vendor", BUILD_VENDOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build_vendor() -> ModuleType:
    return load_build_vendor()


def write_package(root: Path, files: dict[str, str]) -> Path:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_source_tree_digest_is_content_addressed(build_vendor: ModuleType, tmp_path: Path) -> None:
    """Same content, different location and different mtimes -> same digest.

    Borrowed from Bazel/Nix input hashing: a build input is identified by what it
    contains, never by where it sits or when it was touched. Without this the
    stamp could not be compared across machines at all -- every checkout would
    produce a different value for identical sources.
    """
    first = write_package(tmp_path / "a" / "pkg", {"__init__.py": "V = 1\n", "data/table.json": '{"x": 1}\n'})
    second = write_package(tmp_path / "b" / "pkg", {"__init__.py": "V = 1\n", "data/table.json": '{"x": 1}\n'})
    (second / "__init__.py").touch()

    assert build_vendor.source_tree_digest(first) == build_vendor.source_tree_digest(second)


def test_source_tree_digest_changes_for_a_non_python_data_file(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """A data file is part of the snapshot, not a decoration.

    `graph_agent_gateway/registry/call_methods.json` is the provider
    call-method routing table, read at runtime through `importlib.resources`. A
    digest that ignored it would attest to a snapshot state it cannot see.
    """
    first = write_package(tmp_path / "a" / "pkg", {"__init__.py": "", "registry/call_methods.json": '{"t": "old"}\n'})
    second = write_package(tmp_path / "b" / "pkg", {"__init__.py": "", "registry/call_methods.json": '{"t": "new"}\n'})

    assert build_vendor.source_tree_digest(first) != build_vendor.source_tree_digest(second)


def test_source_tree_digest_ignores_bytecode_caches(build_vendor: ModuleType, tmp_path: Path) -> None:
    """`__pycache__` is output, not input, and the wheel never carries it.

    The launcher gate skips it for the same reason
    (`collectPackageFiles` in `ensure_vendor.js`); a digest that counted it
    would drift every time anything imported the package.
    """
    package = write_package(tmp_path / "pkg", {"__init__.py": "V = 1\n"})
    before = build_vendor.source_tree_digest(package)
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "__init__.cpython-312.pyc").write_bytes(b"\x00\x01")

    assert build_vendor.source_tree_digest(package) == before


def test_source_tree_digest_notices_a_renamed_file(build_vendor: ModuleType, tmp_path: Path) -> None:
    """Paths are part of the digest, not just the bag of contents."""
    first = write_package(tmp_path / "a" / "pkg", {"__init__.py": "", "resolver.py": "X = 1\n"})
    second = write_package(tmp_path / "b" / "pkg", {"__init__.py": "", "resolve.py": "X = 1\n"})

    assert build_vendor.source_tree_digest(first) != build_vendor.source_tree_digest(second)


def test_build_stamp_records_every_package_and_one_combined_digest(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    engine = write_package(tmp_path / "graph_agent", {"__init__.py": "V = 1\n"})
    gateway = write_package(tmp_path / "graph_agent_gateway", {"__init__.py": "V = 2\n"})

    stamp = build_vendor.build_stamp(
        package_roots={"graph_agent": engine, "graph_agent_gateway": gateway},
        built_at="2026-09-01T00:00:00+00:00",
        python_version="3.12.13",
        target_triple="x86_64-pc-windows-msvc",
    )

    assert stamp["schema"] == build_vendor.STAMP_SCHEMA
    assert set(stamp["packages"]) == {"graph_agent", "graph_agent_gateway"}
    assert stamp["packages"]["graph_agent"]["digest"] == build_vendor.source_tree_digest(engine)
    assert stamp["packages"]["graph_agent"]["files"] == 1
    assert len(stamp["source_digest"]) == 64
    assert stamp["built_at"] == "2026-09-01T00:00:00+00:00"
    assert stamp["python_version"] == "3.12.13"
    assert stamp["target_triple"] == "x86_64-pc-windows-msvc"


def test_the_combined_digest_moves_when_any_package_moves(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    engine = write_package(tmp_path / "graph_agent", {"__init__.py": "V = 1\n"})
    gateway = write_package(tmp_path / "graph_agent_gateway", {"__init__.py": "V = 2\n"})
    roots = {"graph_agent": engine, "graph_agent_gateway": gateway}
    kwargs = {"built_at": "t", "python_version": "3.12.13", "target_triple": "triple"}

    before = build_vendor.build_stamp(package_roots=roots, **kwargs)["source_digest"]
    (gateway / "__init__.py").write_text("V = 3\n", encoding="utf-8")
    after = build_vendor.build_stamp(package_roots=roots, **kwargs)["source_digest"]

    assert before != after


def iter_strings(value: object) -> Iterator[str]:
    """Every string anywhere in a nested mapping/sequence, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(key)
            yield from iter_strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from iter_strings(item)


def test_the_stamp_does_not_carry_build_machine_paths(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """The stamp ships inside the installer (`bundle.resources: vendor/**/*`).

    Baking the builder's absolute interpreter path into a shipped file leaks the
    build account's home directory and tells a user nothing. The ABI fact worth
    keeping is the interpreter VERSION, which is what the vendored native wheels
    were built against.

    Checked over the parsed values rather than over `json.dumps` output: on
    Windows the dump escapes `\\` as `\\\\`, so a substring search for the path
    would miss it and the test would pass while the leak was there.
    """
    engine = write_package(tmp_path / "graph_agent", {"__init__.py": ""})

    stamp = build_vendor.build_stamp(
        package_roots={"graph_agent": engine},
        built_at="2026-09-01T00:00:00+00:00",
        python_version="3.12.13",
        target_triple="x86_64-pc-windows-msvc",
    )

    needles = {str(tmp_path), tmp_path.as_posix(), str(engine), engine.as_posix()}
    leaked = [text for text in iter_strings(stamp) if any(needle in text for needle in needles)]
    assert leaked == []


def test_write_stamp_lands_inside_the_snapshot_it_describes(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """Lifetime coupling: the stamp lives in `site-packages`, not beside it.

    `build_vendor.build_vendor(clean=True)` removes the target directory before
    installing. A stamp stored one level up in `vendor/` would survive a build
    that then FAILED, and would go on describing a snapshot that no longer
    exists. Inside the target, a wiped snapshot correctly reports "no
    provenance" and the launcher gate rebuilds it.
    """
    target = tmp_path / "site-packages"
    target.mkdir()

    written = build_vendor.write_stamp(target, {"schema": 1, "source_digest": "d" * 64})

    assert written == target / build_vendor.STAMP_FILENAME
    assert json.loads(written.read_text(encoding="utf-8"))["source_digest"] == "d" * 64


def test_package_source_roots_finds_the_module_dir_under_each_local_path(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """Distribution name and module name differ (`graph-agent` -> `graph_agent`).

    The roots are discovered from the `src/` layout rather than derived by
    replacing hyphens, so the stamp cannot be wrong about a package that names
    its module differently from its distribution.
    """
    write_package(tmp_path / "packages" / "graph-agent" / "src" / "graph_agent", {"__init__.py": ""})
    write_package(
        tmp_path / "packages" / "graph-agent-gateway" / "src" / "graph_agent_gateway",
        {"__init__.py": ""},
    )

    roots = build_vendor.package_source_roots(
        tmp_path, ["./packages/graph-agent", "./packages/graph-agent-gateway"]
    )

    assert roots == {
        "graph_agent": tmp_path / "packages" / "graph-agent" / "src" / "graph_agent",
        "graph_agent_gateway": tmp_path / "packages" / "graph-agent-gateway" / "src" / "graph_agent_gateway",
    }


def test_the_real_workspace_packages_are_discoverable(build_vendor: ModuleType) -> None:
    """The discovery rule above must hold for THIS repo, not just a fixture.

    A rule that only works on synthetic trees would leave the shipped stamp
    describing zero packages, and nothing else would notice.
    """
    roots = build_vendor.package_source_roots(
        REPO_ROOT, ["./packages/graph-agent", "./packages/graph-agent-gateway"]
    )

    assert set(roots) == {"graph_agent", "graph_agent_gateway"}
    for root in roots.values():
        assert (root / "__init__.py").is_file()
