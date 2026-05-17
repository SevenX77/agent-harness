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
    """The dotted public path must not leak into ``sys.modules``.

    Phase 3 M7 follow-up (PHASE3_DESIGN.md v4 §3.5): the sandbox now
    DOES register the namespaced ``_graph_agent_sandbox_<digest>_<path>``
    key so ``Pydantic.model_rebuild`` can resolve forward references via
    ``sys.modules``. That registration is intentional and contained to
    the unique sandbox namespace; what we still defend against is the
    raw public dotted path (``"schemas"``) bleeding into the global
    registry where another caller could pick it up by accident.
    """
    module_file = tmp_path / "schemas.py"
    module_file.write_text("class OutputSchema:\n    pass\n", encoding="utf-8")
    sys.modules.pop("schemas", None)

    ModuleSandbox(search_paths=[tmp_path]).import_class("schemas.OutputSchema")

    # Public name must NOT be polluted (the original guard).
    assert "schemas" not in sys.modules
    # Sandbox-namespaced name MAY appear (forward-ref resolution
    # contract). Other tests in the suite may leave their own sandbox
    # keys in ``sys.modules``; we only assert that THIS load registered
    # at least one key whose suffix encodes our ``"schemas"`` module.
    sandbox_keys_for_schemas = [
        name
        for name in sys.modules
        if name.startswith("_graph_agent_sandbox_") and name.endswith("_schemas")
    ]
    assert sandbox_keys_for_schemas, (
        "expected ModuleSandbox to register a namespaced key in sys.modules "
        "for the just-loaded ``schemas`` module so Pydantic forward refs "
        "resolve at model_rebuild() time"
    )


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
        "def normalize(value):\n    return value.strip().lower()\n",
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


# ---- Phase 3 M7 follow-up §3.5 / §3.8 forward-ref regression --------------


def test_pydantic_forward_ref_class_with_literal_validates_post_load(
    tmp_path: Path,
) -> None:
    """PHASE3_DESIGN.md v4 §3.8: load a Pydantic class declared with
    ``from __future__ import annotations`` plus ``Literal[...]`` —
    exactly the shape that triggered the M7 ``PydanticUserError`` —
    and assert ``model_validate`` succeeds without the test having to
    monkey-patch ``sys.modules``. ModuleSandbox must register the
    namespaced module + call ``model_rebuild()`` automatically per
    design §3.5 step 3 so ``Literal`` resolves cleanly.

    Belt-and-braces guard: the original v3 ``test_cognitive_flow_smoke``
    files for ``text-segmentation`` papered over this bug with a manual
    ``sys.modules[name] = module`` workaround in the test loader. After
    the M7 follow-up the workaround is gone, so this regression case is
    the thing keeping the bug from coming back.
    """
    module_file = tmp_path / "fr_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from typing import Literal\n"
        "from pydantic import BaseModel, Field\n"
        "\n"
        "\n"
        "class FRSchema(BaseModel):\n"
        '    kind: Literal["A", "B", "C"] = Field(\n'
        '        description="A forward-referenced Literal — the M7 trip wire"\n'
        "    )\n"
        "    value: int = Field(ge=0)\n",
        encoding="utf-8",
    )

    sandbox = ModuleSandbox(search_paths=[tmp_path])
    schema_cls = sandbox.import_class("fr_schemas.FRSchema")

    # The probe path: model_validate must succeed without raising
    # ``PydanticUserError: <Class> is not fully defined``. Pre-fix this
    # would crash because the ``Literal`` forward-ref couldn't resolve
    # at class build time.
    instance = schema_cls.model_validate({"kind": "B", "value": 7})
    assert instance.model_dump() == {"kind": "B", "value": 7}


def test_pydantic_forward_ref_rebuild_failure_is_fail_loud(tmp_path: Path) -> None:
    """PHASE3_DESIGN.md v4 §3.8 atomicity contract: when ``model_rebuild``
    fails (e.g. an annotation references a name that genuinely doesn't
    exist), the failure must surface at LOAD time, not silently lurk
    until ``model_validate`` runs. This test plants a Pydantic class
    whose annotation references an undefined symbol and asserts the
    sandbox raises (any ``Exception`` is acceptable — the point is
    fail-loud).
    """
    module_file = tmp_path / "broken_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from pydantic import BaseModel\n"
        "\n"
        "\n"
        "class Broken(BaseModel):\n"
        "    field: NameThatDoesNotExist  # noqa: F821 — intentional forward-ref to nothing\n",
        encoding="utf-8",
    )

    # Pydantic raises ``PydanticUndefinedAnnotation`` (subclass of
    # ``NameError``) at ``model_rebuild`` time when an annotation
    # references an undefined name. We assert ``NameError`` since the
    # MRO covers both the Pydantic-specific subclass and any future
    # plain-``NameError`` path.
    with pytest.raises(NameError):
        ModuleSandbox(search_paths=[tmp_path]).import_class("broken_schemas.Broken")


def test_loader_pipeline_resolves_skill_forward_ref_segment_class() -> None:
    """V2.1 keeps reusable schemas in ``skills/shared`` instead of dotted
    ``script.models`` phase metadata; the sandbox path still rebuilds
    future-annotation models end-to-end.
    """
    repo_root = Path(__file__).resolve().parents[4]
    schema_cls = ModuleSandbox(search_paths=[repo_root / "skills"]).import_class(
        "shared.schemas.ParagraphSegment"
    )

    instance = schema_cls.model_validate(
        {
            "index": 1,
            "type": "B",
            "start_line": 1,
            "end_line": 5,
            "content": "loader-based forward-ref smoke",
            "confidence": 0.99,
        }
    )
    dumped = instance.model_dump()
    assert dumped["type"] == "B"
    assert dumped["index"] == 1
