from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from graph_agent.core.module_sandbox import ModuleSandbox


def test_module_sandbox_removes_sys_modules_for_importlib_resolved_spec_name_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_dir = tmp_path / "importable"
    module_dir.mkdir()
    module_name = "pr5_importlib_schema"
    (module_dir / f"{module_name}.py").write_text(
        "class OutputSchema:\n    value = 'importlib-path'\n",
        encoding="utf-8",
    )
    sys.modules.pop(module_name, None)
    monkeypatch.syspath_prepend(str(module_dir))

    cls = ModuleSandbox().import_class(f"{module_name}.OutputSchema")

    assert cls.value == "importlib-path"
    assert module_name not in sys.modules


def test_module_sandbox_preserves_preexisting_importlib_resolved_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_dir = tmp_path / "importable_preexisting"
    module_dir.mkdir()
    module_name = "pr5_preexisting_schema"
    (module_dir / f"{module_name}.py").write_text(
        "class OutputSchema:\n    value = 'preexisting-path'\n",
        encoding="utf-8",
    )
    sys.modules.pop(module_name, None)
    monkeypatch.syspath_prepend(str(module_dir))
    importlib.invalidate_caches()
    original_module = importlib.import_module(module_name)

    cls = ModuleSandbox().import_class(f"{module_name}.OutputSchema")

    assert cls.value == "preexisting-path"
    assert sys.modules[module_name] is original_module


def _sandbox_key(root: Path, module_name: str) -> str:
    module_file = root / f"{module_name}.py"
    return ModuleSandbox._sandbox_module_name(module_name, module_file)


def test_module_sandbox_removes_public_and_sandbox_sys_modules_for_same_named_modules(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "skill_a"
    second_root = tmp_path / "skill_b"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "schemas.py").write_text(
        "class OutputSchema:\n    value = 'a'\n",
        encoding="utf-8",
    )
    (second_root / "schemas.py").write_text(
        "class OutputSchema:\n    value = 'b'\n",
        encoding="utf-8",
    )
    first_key = _sandbox_key(first_root, "schemas")
    second_key = _sandbox_key(second_root, "schemas")
    for key in ("schemas", first_key, second_key):
        sys.modules.pop(key, None)

    first_cls = ModuleSandbox(search_paths=[first_root]).import_class("schemas.OutputSchema")
    second_cls = ModuleSandbox(search_paths=[second_root]).import_class("schemas.OutputSchema")

    assert first_cls.value == "a"
    assert second_cls.value == "b"
    assert "schemas" not in sys.modules
    assert first_key not in sys.modules
    assert second_key not in sys.modules


def test_module_sandbox_forward_ref_model_validate_survives_sys_modules_cleanup(
    tmp_path: Path,
) -> None:
    module_file = tmp_path / "fr_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from typing import Literal\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class FRSchema(BaseModel):\n"
        '    kind: Literal["A", "B"]\n'
        "    value: int\n",
        encoding="utf-8",
    )
    sandbox_key = _sandbox_key(tmp_path, "fr_schemas")
    sys.modules.pop(sandbox_key, None)

    schema_cls = ModuleSandbox(search_paths=[tmp_path]).import_class("fr_schemas.FRSchema")
    instance = schema_cls.model_validate({"kind": "A", "value": 3})

    assert instance.model_dump() == {"kind": "A", "value": 3}
    assert sandbox_key not in sys.modules


def test_module_sandbox_cleans_sys_modules_when_model_rebuild_fails(tmp_path: Path) -> None:
    module_file = tmp_path / "broken_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Broken(BaseModel):\n"
        "    field: NameThatDoesNotExist\n",
        encoding="utf-8",
    )
    sandbox_key = _sandbox_key(tmp_path, "broken_schemas")
    sys.modules.pop(sandbox_key, None)

    with pytest.raises(NameError):
        ModuleSandbox(search_paths=[tmp_path]).import_class("broken_schemas.Broken")

    assert sandbox_key not in sys.modules
