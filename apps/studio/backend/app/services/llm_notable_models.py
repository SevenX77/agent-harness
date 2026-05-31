"""Doc-driven notable model suggestions for providers without list APIs."""

from __future__ import annotations

import re
from pathlib import Path

_NOTABLE_SECTION_HEADING = "## 4. Notable Model IDs"
_MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")


def default_provider_notes_dir() -> Path:
    return Path(__file__).resolve().parents[5] / "docs/development/llm_provider_notes"


def notable_model_ids(provider_key: str, notes_dir: Path | None = None) -> list[str]:
    normalized_key = provider_key.strip().lower()
    if not normalized_key:
        return []
    note_path = (notes_dir or default_provider_notes_dir()) / f"{normalized_key}.md"
    if not note_path.exists():
        return []

    in_notable_section = False
    models: list[str] = []
    seen: set[str] = set()
    for line in note_path.read_text(encoding="utf-8").splitlines():
        if not in_notable_section:
            in_notable_section = line.strip() == _NOTABLE_SECTION_HEADING
            continue
        if line.startswith("## "):
            break
        for model_id in _MARKDOWN_CODE_RE.findall(line):
            if model_id not in seen:
                models.append(model_id)
                seen.add(model_id)
    return models
