"""IOManager — route finish_task output into BusinessData.

T3 of MVP-2 (A7 IOManager extraction): centralize the hoist/io.outputs
field-copying logic behind a small, testable interface. Runtime callers are
wired in later tasks; this module is intentionally standalone for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .state import BusinessData


@dataclass(frozen=True)
class IODef:
    """Internal representation of one io.output/hoist mapping."""

    source_field: str
    target_field: str
    hoist_path: str | None = None
    required: bool = True


@dataclass
class HoistResult:
    """Result returned by IOManager.resolve_hoist."""

    new_business_data: BusinessData
    io_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _PathToken:
    key: str | None = None
    index: int | None = None


_MISSING = object()


class IOManager:
    """Route declared output fields from source data to BusinessData."""

    def __init__(self, io_specs: list[IODef]) -> None:
        self.io_specs = list(io_specs)

    def resolve_hoist(
        self,
        source_data: dict[str, Any],
        target_data: BusinessData,
    ) -> HoistResult:
        """Copy source fields into a new BusinessData instance.

        Missing required fields and advisory type mismatches are accumulated in
        ``io_errors``. Advisory errors do not block writes; the caller decides
        how to surface them.
        """

        errors: list[str] = []
        updates: dict[str, Any] = {}

        for spec in self.io_specs:
            value = self._extract(source_data, spec)
            if value is _MISSING:
                if spec.required:
                    errors.append(
                        f"required io.output '{spec.source_field}' missing in source_data"
                    )
                continue

            current = target_data.get(spec.target_field)
            if current is not None and value is not None and not isinstance(value, type(current)):
                errors.append(
                    f"io.output '{spec.source_field}' type mismatch for target "
                    f"'{spec.target_field}': expected {type(current).__name__}, "
                    f"got {type(value).__name__}"
                )
            updates[spec.target_field] = value

        new_data = target_data.model_copy(update=updates) if updates else target_data
        return HoistResult(new_business_data=new_data, io_errors=errors)

    def _extract(self, source: dict[str, Any], spec: IODef) -> Any:
        """Extract a value using source_field plus optional dotted/bracket path."""

        if spec.hoist_path:
            path = spec.hoist_path
            if path == spec.source_field or path.startswith(f"{spec.source_field}."):
                return _resolve_path(source, path)
            if path.startswith(f"{spec.source_field}["):
                return _resolve_path(source, path)
            root = source.get(spec.source_field, _MISSING)
            if root is _MISSING:
                return _resolve_path(source, path)
            relative_path = path[1:] if path.startswith(".") else path
            return _resolve_path(root, relative_path)
        return source.get(spec.source_field, _MISSING)

    @staticmethod
    def validate_spec(spec: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate an io output spec dict without raising."""

        errors: list[str] = []
        source = spec.get("source_field")
        target = spec.get("target_field")
        hoist_path = spec.get("hoist_path")
        required = spec.get("required", True)

        if not isinstance(source, str) or not source:
            errors.append("io.output spec missing source_field")
        if not isinstance(target, str) or not target:
            errors.append("io.output spec missing target_field")
        if isinstance(target, str) and target.startswith("_"):
            errors.append("io.output target_field must not start with '_'")
        if hoist_path is not None and not isinstance(hoist_path, str):
            errors.append("io.output hoist_path must be a string when provided")
        if not isinstance(required, bool):
            errors.append("io.output required must be a bool")
        return len(errors) == 0, errors


def _resolve_path(value: Any, path: str) -> Any:
    current = value
    tokens = _parse_path(path)
    if tokens is None:
        return _MISSING
    for token in tokens:
        if token.key is not None:
            if not isinstance(current, dict) or token.key not in current:
                return _MISSING
            current = current[token.key]
        if token.index is not None:
            if not isinstance(current, list):
                return _MISSING
            try:
                current = current[token.index]
            except IndexError:
                return _MISSING
    return current


def _parse_path(path: str) -> list[_PathToken] | None:
    if not path:
        return None

    tokens: list[_PathToken] = []
    for part in path.split("."):
        if not part:
            return None
        key, bracket_parts = _split_brackets(part)
        if "invalid" in bracket_parts:
            return None
        if key:
            tokens.append(_PathToken(key=key))
        for raw_index in bracket_parts:
            try:
                index = int(raw_index)
            except ValueError:
                return None
            if index < 0:
                return None
            tokens.append(_PathToken(index=index))
    return tokens


def _split_brackets(part: str) -> tuple[str, list[str]]:
    key_chars: list[str] = []
    indexes: list[str] = []
    index = 0
    while index < len(part):
        char = part[index]
        if char != "[":
            key_chars.append(char)
            index += 1
            continue
        close_index = part.find("]", index)
        if close_index == -1:
            return "".join(key_chars), ["invalid"]
        indexes.append(part[index + 1 : close_index])
        index = close_index + 1
    return "".join(key_chars), indexes


__all__ = ["HoistResult", "IODef", "IOManager"]
