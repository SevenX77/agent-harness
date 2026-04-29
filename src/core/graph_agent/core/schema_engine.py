"""SchemaEngine — unified parsing/validation of SKILL.md output_schema.

T1 of MVP-2 (A5 SchemaEngine 抽出): consolidate the schema-parsing logic
that currently sits scattered across ``loader.py`` / ``finish.py`` /
``md_to_json.py`` / ``artifact_manager.py`` / ``phase_executor.py`` (5
sites identified during the MVP-1 T0-prep audit) behind a single typed
interface.

T1 scope: module skeleton + dataclass containers + interface stubs +
unit tests. Real parsing logic and the wired callers come in later
tasks:

- T2: ``get_pydantic_model`` cache wiring + ``build_business_data_for_skill``
  factory in ``state.py``.
- T3: real text → SchemaObject extraction (lifted from ``loader.py``).
- T5: ``finish.py`` calls ``SchemaEngine.validate`` + ``IOManager.resolve_hoist``.
- T6: ``loader.py`` + ``md_to_json.py`` adopt SchemaEngine and stop reading
  Manifest privates.

The stub returns wired-but-empty values so that any caller introduced in
T2+ gets a working object back without conditional checks. T1 unit tests
pin the contract; T2-T6 will extend the same tests as logic lands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


@dataclass
class SchemaObject:
    """In-memory schema representation passed between SchemaEngine methods.

    ``fields`` maps a SKILL business field name to its declared Python
    type (``str``/``int``/``list[str]`` etc.) when statically known, or to
    a string sentinel (e.g. ``"any"``) when only loosely declared. T3
    populates this from real ``output_schema:`` markdown parsing; T1 ships
    an empty container.
    """

    raw: dict[str, Any]
    fields: dict[str, type | str]
    field_descriptions: dict[str, str] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    schema_version: str | None = None
    skill_id: str | None = None


@dataclass
class ValidationResult:
    """Outcome of ``SchemaEngine.validate`` against a SchemaObject.

    ``passed`` is the high-level verdict; ``errors``/``warnings`` are
    free-form messages and ``field_errors`` maps a field name to its
    specific failure reason for IDE-friendly surfacing.
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_errors: dict[str, str] = field(default_factory=dict)


class SchemaEngine:
    """Single owner for schema parsing, validation, and Pydantic projection.

    T1 ships interface stubs only; real implementations land in later
    MVP-2 tasks. The class is per-instance (no singleton, see MVP-2
    research D1) and holds a per-instance Pydantic model cache keyed by
    SchemaObject identity.
    """

    def __init__(self) -> None:
        self._pydantic_model_cache: dict[int, type[BaseModel]] = {}

    def parse_from_md(self, md_content: str) -> SchemaObject:
        """Parse a SKILL.md ``output_schema``/``output_example`` fragment.

        T1 stub: returns an empty SchemaObject regardless of input. T3
        will lift the real markdown extractor from ``loader.py`` (which
        currently mixes regex parsing with Pydantic field building).
        """
        logger.debug("SchemaEngine.parse_from_md called (T1 stub) len=%d", len(md_content))
        return SchemaObject(raw={}, fields={})

    def get_pydantic_model(self, schema: SchemaObject) -> type[BaseModel]:
        """Return a cached Pydantic model class derived from ``schema``.

        T1 stub: produces a minimal ``extra='allow'`` BaseModel subclass.
        Cache key uses ``id(schema)`` because SchemaObject is a regular
        (mutable) dataclass and not hashable; T3 may switch to a content
        hash once SchemaObject becomes frozen.
        """
        cache_key = id(schema)
        cached = self._pydantic_model_cache.get(cache_key)
        if cached is not None:
            return cached

        class _DynamicModel(BaseModel):
            model_config = ConfigDict(extra="allow")

        self._pydantic_model_cache[cache_key] = _DynamicModel
        return _DynamicModel

    def validate(self, data: Any, schema: SchemaObject) -> ValidationResult:
        """Validate ``data`` against ``schema`` and return a structured result.

        T1 stub: always passes. T3 will project the schema into a
        Pydantic model via ``get_pydantic_model`` and run ``model_validate``,
        translating ``ValidationError`` into ``ValidationResult.field_errors``.
        """
        logger.debug(
            "SchemaEngine.validate called (T1 stub) data_type=%s fields=%d",
            type(data).__name__,
            len(schema.fields),
        )
        return ValidationResult(passed=True)

    def get_json_schema(self, schema: SchemaObject) -> dict[str, Any]:
        """Return a JSON-Schema-shaped dict suitable for prompt rendering.

        T1 stub: returns ``schema.raw`` as-is. T6 will lift the
        ``md_to_json`` prompt projection so callers no longer reach into
        Manifest privates for the same view.
        """
        return dict(schema.raw)
