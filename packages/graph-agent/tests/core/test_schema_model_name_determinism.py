"""A schema's generated model name is a function of the schema, nothing else.

`SchemaEngine` names every model it builds `<schema_name>_<digest>`. The digest
has to be a function of the schema's identity alone: the same schema must get
the same name in every process, and two schemas that compare equal must get the
same name. Both properties were broken by taking the digest over `repr(schema)`
-- see the module docstring of `_canonical_schema_key` for what that pulled in.
"""

from __future__ import annotations

import os
import subprocess
import sys

from graph_agent.core.schema_engine import SchemaObject, _model_name_for_schema

_PROBE = """
from graph_agent.core.schema_engine import SchemaObject, _model_name_for_schema

schema = SchemaObject(
    fields=(
        ("title", str),
        ("summary", str),
        ("event_type", str),
        ("paragraph_indices", str),
        ("location", str),
    ),
    required_fields=frozenset(
        {"title", "summary", "event_type", "paragraph_indices", "location"}
    ),
    schema_name="Segment",
)
print(_model_name_for_schema(schema))
"""


def _name_under_hash_seed(seed: str) -> str:
    """The model name this schema gets in a fresh interpreter with `seed`.

    `PYTHONHASHSEED` randomises str hashing, which decides the iteration order
    of `required_fields` (a frozenset). It can only be set before interpreter
    start, so observing the defect at all requires a subprocess.
    """

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


def test_the_same_schema_gets_the_same_model_name_in_every_process() -> None:
    names = {seed: _name_under_hash_seed(seed) for seed in ("0", "1", "2", "3")}
    assert len(set(names.values())) == 1, f"model name varies with the hash seed: {names}"


def test_schemas_that_compare_equal_get_the_same_model_name() -> None:
    """`raw_schema_dict` is `compare=False`, so it must not reach the name.

    Two `SchemaObject`s that are `==` are the same schema by the type's own
    definition; naming them differently would hand the same schema two model
    names within a single process.
    """

    fields = (("title", str), ("body", str))
    left = SchemaObject(
        fields=fields,
        required_fields=frozenset({"title"}),
        schema_name="Article",
        raw_schema_dict={"type": "object", "properties": {"title": {"type": "string"}}},
    )
    right = SchemaObject(
        fields=fields,
        required_fields=frozenset({"title"}),
        schema_name="Article",
        raw_schema_dict={},
    )

    assert left == right
    assert _model_name_for_schema(left) == _model_name_for_schema(right)


def test_different_schemas_still_get_different_model_names() -> None:
    """Determinism must not be bought by collapsing distinct schemas together."""

    base = SchemaObject(fields=(("title", str),), required_fields=frozenset({"title"}), schema_name="Article")
    renamed_field = SchemaObject(fields=(("headline", str),), required_fields=frozenset({"headline"}), schema_name="Article")
    optional_title = SchemaObject(fields=(("title", str),), required_fields=frozenset(), schema_name="Article")
    other_type = SchemaObject(fields=(("title", int),), required_fields=frozenset({"title"}), schema_name="Article")

    names = {
        _model_name_for_schema(base),
        _model_name_for_schema(renamed_field),
        _model_name_for_schema(optional_title),
        _model_name_for_schema(other_type),
    }
    assert len(names) == 4, names
