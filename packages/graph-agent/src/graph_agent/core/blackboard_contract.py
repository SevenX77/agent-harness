"""What a compiled graph can produce, and what it declares as its output.

A skill answers two questions at its boundary: what it takes in, and what it
gives back. The second one was only ever derived inside the Studio frontend, so
nothing else — no tool, no check, no other surface — could reason about a
skill's output contract. It is a fact about the graph, not about a panel, so it
is derived here, once, from the compiled skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph_agent.core.loader import CompiledSkill

#: Where a field on the blackboard came from when the graph reaches its output.
INPUT_ORIGIN = "input"


@dataclass(frozen=True)
class BlackboardField:
    """One top-level field present on the blackboard at the graph's output."""

    name: str
    type: str
    #: ``input`` for a graph input, otherwise the phase that writes it last.
    produced_by: str
    #: Whether the graph's own ``io.outputs`` names this field.
    declared_output: bool


def _schema_of(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _type_of(schema: dict[str, Any]) -> str:
    declared = schema.get("type")
    return declared if isinstance(declared, str) else "unknown"


def _properties_of(io_section: Any, side: str) -> dict[str, Any]:
    return _schema_of(_schema_of(_schema_of(io_section).get(side)).get("properties"))


def blackboard_fields_at_output(compiled: CompiledSkill) -> list[BlackboardField]:
    """Project the fields the blackboard carries when the graph finishes.

    Graph inputs seed the blackboard and each phase's declared outputs are laid
    over it in topology order, so a name written by two phases is attributed to
    the later one — that is the value the output boundary actually sees.
    """
    fields: dict[str, BlackboardField] = {}

    declared_names = set(_properties_of(compiled.raw.get("io"), "outputs"))

    for name, raw in _properties_of(compiled.raw.get("io"), "inputs").items():
        fields[name] = BlackboardField(
            name=name,
            type=_type_of(_schema_of(raw)),
            produced_by=INPUT_ORIGIN,
            declared_output=name in declared_names,
        )

    for node in compiled.nodes:
        for name, raw in _properties_of(node.frontmatter.get("io"), "outputs").items():
            fields[name] = BlackboardField(
                name=name,
                type=_type_of(_schema_of(raw)),
                produced_by=node.phase_name,
                declared_output=name in declared_names,
            )

    return list(fields.values())


def undeclared_output_names(compiled: CompiledSkill) -> list[str]:
    """Names in the graph's ``io.outputs`` that no phase and no input provides.

    A declared output nothing produces is a contract the graph cannot honour;
    surfacing it is the point of deriving the universe in the first place.
    """
    produced = {field.name for field in blackboard_fields_at_output(compiled)}
    return [name for name in _properties_of(compiled.raw.get("io"), "outputs") if name not in produced]
