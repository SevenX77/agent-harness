"""Tests for ModuleSandbox."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from graph_agent.core.module_sandbox import ModuleSandbox


def test_import_class_from_search_path(tmp_path: Path) -> None:
    module_file = tmp_path / "schemas.py"
    module_file.write_text("class OutputSchema:\n    value = 1\n", encoding="utf-8")

    cls = ModuleSandbox(search_paths=[tmp_path]).import_class("schemas.OutputSchema")

    assert cls.__name__ == "OutputSchema"
    assert cls.value == 1


def test_import_class_does_not_write_public_module_to_sys_modules(tmp_path: Path) -> None:
    module_file = tmp_path / "schemas.py"
    module_file.write_text("class OutputSchema:\n    pass\n", encoding="utf-8")
    sys.modules.pop("schemas", None)

    ModuleSandbox(search_paths=[tmp_path]).import_class("schemas.OutputSchema")

    assert "schemas" not in sys.modules
    assert not any(name.startswith("_graph_agent_sandbox_") for name in sys.modules)


def test_import_class_caches_result(tmp_path: Path) -> None:
    module_file = tmp_path / "schemas.py"
    module_file.write_text("class OutputSchema:\n    pass\n", encoding="utf-8")
    sandbox = ModuleSandbox(search_paths=[tmp_path])

    first = sandbox.import_class("schemas.OutputSchema")
    second = sandbox.import_class("schemas.OutputSchema")

    assert first is second


def test_import_callable_from_search_path(tmp_path: Path) -> None:
    module_file = tmp_path / "tools.py"
    module_file.write_text(
        "def normalize(value):\n"
        "    return value.strip().lower()\n",
        encoding="utf-8",
    )

    func = ModuleSandbox(search_paths=[tmp_path]).import_callable("tools.normalize")

    assert func("  Hello ") == "hello"


def test_import_callable_rejects_non_callable(tmp_path: Path) -> None:
    module_file = tmp_path / "tools.py"
    module_file.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportError, match="did not resolve to a callable"):
        ModuleSandbox(search_paths=[tmp_path]).import_callable("tools.VALUE")


def test_import_object_from_package_init(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'ok'\n", encoding="utf-8")

    value = ModuleSandbox(search_paths=[tmp_path]).import_object("pkg.VALUE")

    assert value == "ok"


def test_with_search_paths_returns_copy_with_additional_roots(tmp_path: Path) -> None:
    module_file = tmp_path / "schemas.py"
    module_file.write_text("class OutputSchema:\n    pass\n", encoding="utf-8")
    base = ModuleSandbox()

    extended = base.with_search_paths([tmp_path])

    assert base.search_paths == ()
    assert extended.search_paths == (tmp_path.resolve(),)
    assert extended.import_class("schemas.OutputSchema").__name__ == "OutputSchema"


def test_import_class_rejects_missing_module() -> None:
    with pytest.raises(ImportError, match="cannot find module"):
        ModuleSandbox().import_class("does_not_exist.OutputSchema")


def test_import_class_rejects_non_class_attribute(tmp_path: Path) -> None:
    module_file = tmp_path / "schemas.py"
    module_file.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ImportError, match="did not resolve to a class"):
        ModuleSandbox(search_paths=[tmp_path]).import_class("schemas.VALUE")


def test_import_class_rejects_invalid_dotted_path() -> None:
    with pytest.raises(ImportError, match="expected dotted class path"):
        ModuleSandbox().import_class("OutputSchema")
