"""The vendor snapshot must be able to say what it was built from.

`apps/studio/tauri/vendor/site-packages` is a frozen copy of the two SDK
packages that the desktop app's Python sidecar imports at runtime -- in dev
builds too. On a developer's machine the launcher gate
(`apps/studio/tauri/scripts/ensure_vendor.js`) has to answer "is this snapshot
stale?"; on a user's machine there is no working tree at all, so the snapshot is
anonymous: nothing in it, or in a bug report about it, can name the source state
it came from.

These tests cover the stamp `build_vendor.py` writes to close both gaps, and the
two properties that make it worth writing:

  * its file list comes from the wheels the build actually produced, so neither
    the build nor the gate has to hold an opinion about which files a package
    consists of -- an opinion that was wrong in both directions before;
  * its digests are a function of file CONTENT only, so the same sources produce
    the same value on any machine, in any directory, at any time.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
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


def make_wheel(path: Path, entries: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return path


def write_project(root: Path, packages: list[str]) -> Path:
    """A minimal hatchling project declaring where its wheel packages come from."""
    root.mkdir(parents=True, exist_ok=True)
    declared = ", ".join(f'"{entry}"' for entry in packages)
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        f"packages = [{declared}]\n",
        encoding="utf-8",
    )
    return root


# ── the expected file set comes from the wheel, not from a walk of the tree ──


def test_wheel_package_files_lists_what_the_wheel_ships(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """Including files a source-tree walk would have skipped.

    Verified against a real hatchling wheel: a package holding
    `.runtime-data.json`, `CHANGELOG.md`, `_native.pyd` and `__pycache__/`
    produced a wheel carrying the first two only -- hatchling ships package
    dotfiles and honours the repo's VCS ignores (`*.py[cod]` covers `.pyd`).
    Both halves of that are the opposite of what the launcher gate used to
    assume, which is why the file set is read off the wheel instead.
    """
    wheel = make_wheel(
        tmp_path / "example-1.0-py3-none-any.whl",
        {
            "example_pkg/__init__.py": b"V = 1\n",
            "example_pkg/.runtime-data.json": b'{"v": 1}\n',
            "example_pkg/registry/call_methods.json": b'{"transform": "none"}\n',
            "example_pkg-1.0.dist-info/METADATA": b"Name: example\n",
            "example_pkg-1.0.dist-info/RECORD": b"example_pkg/__init__.py,,\n",
        },
    )

    files = build_vendor.wheel_package_files(wheel)

    assert set(files) == {"example_pkg"}
    assert set(files["example_pkg"]) == {
        "__init__.py",
        ".runtime-data.json",
        "registry/call_methods.json",
    }
    assert files["example_pkg"]["__init__.py"] == build_vendor.hashlib.sha256(b"V = 1\n").hexdigest()


def test_wheel_package_files_groups_several_packages(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    wheel = make_wheel(
        tmp_path / "two-1.0-py3-none-any.whl",
        {"one/__init__.py": b"", "two/__init__.py": b"", "two-1.0.dist-info/WHEEL": b""},
    )

    assert set(build_vendor.wheel_package_files(wheel)) == {"one", "two"}


def test_wheel_package_files_refuses_a_bare_top_level_module(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """Fail at the boundary rather than guess.

    A wheel shipping a top-level module file has no package directory to map
    back to a source directory, and a guess would put a wrong `source_root` in
    the stamp -- where the launcher gate would compare the snapshot against a
    tree that is not its source.
    """
    wheel = make_wheel(tmp_path / "bare-1.0-py3-none-any.whl", {"bare.py": b"V = 1\n"})

    with pytest.raises(SystemExit, match="bare.py"):
        build_vendor.wheel_package_files(wheel)


# ── the digest that makes a snapshot placeable across machines ──────────────


def test_manifest_digest_is_content_addressed(build_vendor: ModuleType) -> None:
    """Same files, built elsewhere at another time -> same digest.

    Borrowed from Bazel/Nix input hashing: a build input is identified by what
    it contains, never by where it sits or when it was touched. Without this the
    stamp could not be compared across machines at all.
    """
    first = {"__init__.py": "a" * 64, "data/table.json": "b" * 64}
    second = {"data/table.json": "b" * 64, "__init__.py": "a" * 64}

    assert build_vendor.manifest_digest(first) == build_vendor.manifest_digest(second)


def test_manifest_digest_moves_for_a_changed_data_file(build_vendor: ModuleType) -> None:
    """A data file is part of the snapshot, not a decoration.

    `graph_agent_gateway/registry/call_methods.json` is the provider
    call-method routing table, read at runtime through `importlib.resources`. A
    digest that ignored it would attest to a snapshot state it cannot see.
    """
    before = build_vendor.manifest_digest({"registry/call_methods.json": "a" * 64})
    after = build_vendor.manifest_digest({"registry/call_methods.json": "c" * 64})

    assert before != after


def test_manifest_digest_notices_a_renamed_file(build_vendor: ModuleType) -> None:
    """Paths are part of the digest, not just the bag of contents."""
    before = build_vendor.manifest_digest({"resolver.py": "a" * 64})
    after = build_vendor.manifest_digest({"resolve.py": "a" * 64})

    assert before != after


# ── where a wheel's package came from is read from the project's own config ──


def test_hatch_package_dirs_reads_the_projects_own_mapping(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    """Ask the authority instead of assuming `src/<module name>`.

    `[tool.hatch.build.targets.wheel] packages` is the mapping hatchling itself
    uses, and distribution name and module name are separate facts
    (`graph-agent` -> `graph_agent`).
    """
    project = write_project(tmp_path / "graph-agent", ["src/graph_agent"])

    assert build_vendor.hatch_package_dirs(project) == {"graph_agent": "src/graph_agent"}


def test_hatch_package_dirs_refuses_a_project_that_declares_none(
    build_vendor: ModuleType, tmp_path: Path
) -> None:
    project = tmp_path / "plain"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "plain"\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="tool.hatch.build.targets.wheel"):
        build_vendor.hatch_package_dirs(project)


def test_the_real_workspace_packages_declare_where_their_sources_live(
    build_vendor: ModuleType,
) -> None:
    """The rule above must hold for THIS repo, not just a fixture.

    A rule that only works on synthetic trees would leave the shipped stamp
    pointing at directories that do not exist, and the launcher gate would then
    report every file of every package as gone from the sources -- drift no
    rebuild could clear.
    """
    for project, module in (
        ("packages/graph-agent", "graph_agent"),
        ("packages/graph-agent-gateway", "graph_agent_gateway"),
    ):
        dirs = build_vendor.hatch_package_dirs(REPO_ROOT / project)
        assert module in dirs
        assert (REPO_ROOT / project / dirs[module] / "__init__.py").is_file()


def test_install_local_wheels_records_a_workspace_relative_source_root(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stamp entry the launcher gate resolves against the repo root.

    `uv` is stubbed out: what is under test is the mapping from "this wheel came
    from that project" to "this package's sources live there", not uv's ability
    to build a wheel.
    """
    workspace = tmp_path / "workspace"
    write_project(workspace / "packages" / "example", ["src/example_pkg"])

    def fake_run(command: list[str], **kwargs: object) -> None:
        if command[1] != "build":
            return
        out = Path(command[command.index("-o") + 1])
        make_wheel(out / "example-1.0-py3-none-any.whl", {"example_pkg/__init__.py": b"V = 1\n"})

    monkeypatch.setattr(build_vendor.subprocess, "run", fake_run)

    packages = build_vendor.install_local_wheels(
        python=Path("python"),
        local_paths=["./packages/example"],
        target=tmp_path / "site-packages",
        root=workspace,
    )

    assert packages["example_pkg"]["source_root"] == "packages/example/src/example_pkg"
    assert packages["example_pkg"]["files"] == {
        "__init__.py": build_vendor.hashlib.sha256(b"V = 1\n").hexdigest()
    }


# ── the stamp itself ────────────────────────────────────────────────────────


def package_entry(build_vendor: ModuleType, name: str, files: dict[str, str]) -> dict[str, object]:
    return {
        "source_root": f"packages/{name}/src/{name}",
        "digest": build_vendor.manifest_digest(files),
        "files": files,
    }


def test_build_stamp_records_every_package_and_one_combined_digest(
    build_vendor: ModuleType,
) -> None:
    engine = package_entry(build_vendor, "graph_agent", {"__init__.py": "a" * 64})
    gateway = package_entry(build_vendor, "graph_agent_gateway", {"__init__.py": "b" * 64})

    stamp = build_vendor.build_stamp(
        packages={"graph_agent_gateway": gateway, "graph_agent": engine},
        built_at="2026-09-01T00:00:00+00:00",
        python_version="3.12.13",
        target_triple="x86_64-pc-windows-msvc",
    )

    assert stamp["schema"] == build_vendor.STAMP_SCHEMA
    assert list(stamp["packages"]) == ["graph_agent", "graph_agent_gateway"]
    assert stamp["packages"]["graph_agent"]["files"] == {"__init__.py": "a" * 64}
    assert len(stamp["source_digest"]) == 64
    assert stamp["built_at"] == "2026-09-01T00:00:00+00:00"
    assert stamp["python_version"] == "3.12.13"
    assert stamp["target_triple"] == "x86_64-pc-windows-msvc"


def test_the_combined_digest_moves_when_any_package_moves(build_vendor: ModuleType) -> None:
    engine = package_entry(build_vendor, "graph_agent", {"__init__.py": "a" * 64})
    gateway = package_entry(build_vendor, "graph_agent_gateway", {"__init__.py": "b" * 64})
    kwargs = {"built_at": "t", "python_version": "3.12.13", "target_triple": "triple"}

    before = build_vendor.build_stamp(
        packages={"graph_agent": engine, "graph_agent_gateway": gateway}, **kwargs
    )["source_digest"]
    moved = package_entry(build_vendor, "graph_agent_gateway", {"__init__.py": "c" * 64})
    after = build_vendor.build_stamp(
        packages={"graph_agent": engine, "graph_agent_gateway": moved}, **kwargs
    )["source_digest"]

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
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stamp ships inside the installer (`bundle.resources: vendor/**/*`).

    Baking the builder's absolute paths into a shipped file leaks the build
    account's home directory and tells a user nothing. Source roots are recorded
    relative to the workspace root, which is a fact about the repo rather than
    about the machine.

    Checked over the parsed values rather than over `json.dumps` output: on
    Windows the dump escapes `\\` as `\\\\`, so a substring search for the path
    would miss it and the test would pass while the leak was there.
    """
    workspace = tmp_path / "workspace"
    write_project(workspace / "packages" / "example", ["src/example_pkg"])

    def fake_run(command: list[str], **kwargs: object) -> None:
        if command[1] != "build":
            return
        out = Path(command[command.index("-o") + 1])
        make_wheel(out / "example-1.0-py3-none-any.whl", {"example_pkg/__init__.py": b""})

    monkeypatch.setattr(build_vendor.subprocess, "run", fake_run)
    packages = build_vendor.install_local_wheels(
        python=Path("python"),
        local_paths=["./packages/example"],
        target=tmp_path / "site-packages",
        root=workspace,
    )

    stamp = build_vendor.build_stamp(
        packages=packages,
        built_at="2026-09-01T00:00:00+00:00",
        python_version="3.12.13",
        target_triple="x86_64-pc-windows-msvc",
    )

    needles = {str(tmp_path), tmp_path.as_posix(), str(workspace), workspace.as_posix()}
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

    written = build_vendor.write_stamp(target, {"schema": 2, "source_digest": "d" * 64})

    assert written == target / build_vendor.STAMP_FILENAME
    assert json.loads(written.read_text(encoding="utf-8"))["source_digest"] == "d" * 64


# ── a build that cannot finish must not leave provenance behind ─────────────


def stub_uv(build_vendor: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_vendor.shutil, "which", lambda name: "uv")


def fail_after_clean(build_vendor: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("uv export failed")

    monkeypatch.setattr(build_vendor, "export_closure", explode)


def test_a_clean_that_removed_nothing_fails_loudly(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ignore_errors=True` let a blocked clean pass for a successful one.

    Windows holds the vendored `.pyd`/`.dll` files open while the desktop app
    runs, so `shutil.rmtree(..., ignore_errors=True)` returned happily having
    removed nothing and the build carried on installing over the snapshot it
    believed it had wiped.
    """
    target = tmp_path / "site-packages"
    target.mkdir()
    stub_uv(build_vendor, monkeypatch)
    monkeypatch.setattr(build_vendor.shutil, "rmtree", lambda *args, **kwargs: None)
    fail_after_clean(build_vendor, monkeypatch)

    with pytest.raises(SystemExit, match="survived its own removal"):
        build_vendor.build_vendor(python=Path("python"), target=target)


def test_a_clean_that_raises_names_the_usual_cause(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "site-packages"
    target.mkdir()
    stub_uv(build_vendor, monkeypatch)

    def locked(*args: object, **kwargs: object) -> None:
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(build_vendor.shutil, "rmtree", locked)
    fail_after_clean(build_vendor, monkeypatch)

    with pytest.raises(SystemExit, match="close it and run this again"):
        build_vendor.build_vendor(python=Path("python"), target=target)


def test_a_failed_build_leaves_no_stamp_behind(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stamp outliving the snapshot it describes is a lie the gate believes.

    The stamp is dropped before anything else is touched, so every way the build
    can fail after that point -- blocked clean, failed export, failed wheel --
    leaves a snapshot that honestly reports "no provenance" and gets rebuilt.
    """
    target = tmp_path / "site-packages"
    target.mkdir()
    stamp = target / build_vendor.STAMP_FILENAME
    stamp.write_text('{"schema": 2, "source_digest": "old"}', encoding="utf-8")
    stub_uv(build_vendor, monkeypatch)
    monkeypatch.setattr(build_vendor.shutil, "rmtree", lambda *args, **kwargs: None)
    fail_after_clean(build_vendor, monkeypatch)

    with pytest.raises(SystemExit):
        build_vendor.build_vendor(python=Path("python"), target=target)

    assert not stamp.exists()


def test_a_no_clean_build_that_fails_also_drops_the_stamp(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--no-clean` installs over the snapshot, so its stamp expires too."""
    target = tmp_path / "site-packages"
    target.mkdir()
    stamp = target / build_vendor.STAMP_FILENAME
    stamp.write_text('{"schema": 2, "source_digest": "old"}', encoding="utf-8")
    stub_uv(build_vendor, monkeypatch)
    fail_after_clean(build_vendor, monkeypatch)

    with pytest.raises(RuntimeError):
        build_vendor.build_vendor(python=Path("python"), target=target, clean=False)

    assert not stamp.exists()


@pytest.mark.skipif(
    sys.platform != "win32", reason="only Windows refuses to delete a file that is open"
)
def test_a_really_locked_snapshot_stops_the_build(
    build_vendor: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real thing, on the platform where it happens.

    This is the situation AGENTS.md (Workflow Pipeline step 7) warns about: the
    running desktop app holds the vendored native extensions open, so the clean
    cannot proceed. No `shutil` stub here -- the lock is genuine.
    """
    target = tmp_path / "site-packages"
    (target / "graph_agent").mkdir(parents=True)
    locked = target / "graph_agent" / "_native.pyd"
    locked.write_bytes(b"MZ")
    stub_uv(build_vendor, monkeypatch)

    with locked.open("rb"):
        with pytest.raises(SystemExit, match="close it and run this again"):
            build_vendor.build_vendor(python=Path("python"), target=target)
