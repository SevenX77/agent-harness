from __future__ import annotations

from pathlib import Path

from app.services.llm_notable_models import notable_model_ids


def test_notable_model_ids_parse_section_code_spans(tmp_path: Path) -> None:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "openai.md").write_text(
        "\n".join(
            [
                "# OpenAI",
                "",
                "## 4. Notable Model IDs",
                "",
                "- `gpt-4o` — flagship",
                "- `o1-preview` / `o1-mini` — reasoning",
                "- `gpt-4o` — duplicate",
                "",
                "## 5. Other",
                "- `not-a-suggestion`",
            ]
        ),
        encoding="utf-8",
    )

    assert notable_model_ids("OpenAI", notes_dir) == ["gpt-4o", "o1-preview", "o1-mini"]


def test_notable_model_ids_unknown_provider_returns_empty_list(tmp_path: Path) -> None:
    assert notable_model_ids("missing", tmp_path) == []
