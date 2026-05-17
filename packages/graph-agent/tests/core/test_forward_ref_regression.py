"""Regression for Pydantic forward refs in dynamically imported schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from graph_agent.core.module_sandbox import ModuleSandbox


def test_module_sandbox_rebuilds_forward_ref_schema(tmp_path: Path) -> None:
    (tmp_path / "schemas.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "from typing import Literal",
                "from pydantic import BaseModel",
                "",
                "class ForwardRefResult(BaseModel):",
                "    kind: Literal['A', 'B']",
                "    title: str",
            ]
        ),
        encoding="utf-8",
    )

    schema_cls = ModuleSandbox(search_paths=[tmp_path]).import_class(
        "schemas.ForwardRefResult"
    )
    instance = schema_cls.model_validate({"kind": "A", "title": "ok"})

    assert instance.model_dump() == {"kind": "A", "title": "ok"}
    assert schema_cls.model_fields["kind"].annotation == Literal["A", "B"]
