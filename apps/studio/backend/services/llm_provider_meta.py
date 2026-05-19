"""Load LLM provider runtime metadata from provider docs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml


@dataclass(frozen=True)
class ProviderMeta:
    vendor: str
    compatible_sdks: list[str]
    models_endpoint_path: str | None
    auth_header_format: str


DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "llm-providers"


def load_provider_meta(vendor: str) -> ProviderMeta:
    """Parse the §1.5 YAML metadata block from docs/llm-providers/<vendor>.md."""
    doc_path = DOCS_DIR / f"{vendor}.md"
    if not doc_path.exists():
        raise FileNotFoundError(f"Provider doc not found: {doc_path}")

    content = doc_path.read_text(encoding="utf-8")
    yaml_block = _extract_section_15_yaml(content)

    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid §1.5 metadata YAML in {doc_path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Invalid §1.5 metadata YAML in {doc_path}")

    compatible_sdks = _require_list_of_strings(data, "compatible_sdks", doc_path)
    models_endpoint_path = _require_optional_string(data, "models_endpoint_path", doc_path)
    auth_header_format = _require_string(data, "auth_header_format", doc_path)

    return ProviderMeta(
        vendor=vendor,
        compatible_sdks=compatible_sdks,
        models_endpoint_path=models_endpoint_path,
        auth_header_format=auth_header_format,
    )


def _extract_section_15_yaml(md_content: str) -> str:
    """Return the first YAML fenced block under a §1.5 heading."""
    pattern = re.compile(
        r"^##\s+§1\.5.*?^```yaml\n(.*?)\n```",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(md_content)
    if not match:
        raise ValueError("§1.5 metadata section not found or YAML block missing")
    return match.group(1)


def _require_list_of_strings(data: dict[Any, Any], key: str, doc_path: Path) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Invalid §1.5 metadata field {key!r} in {doc_path}")
    return value


def _require_optional_string(data: dict[Any, Any], key: str, doc_path: Path) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid §1.5 metadata field {key!r} in {doc_path}")
    return value


def _require_string(data: dict[Any, Any], key: str, doc_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Invalid §1.5 metadata field {key!r} in {doc_path}")
    return value
