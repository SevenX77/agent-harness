from __future__ import annotations

from graph_agent.core.builtin_subagents.reference_reader import (
    ReferenceReaderInput,
    fallback_reference_markdown,
    output_from_any,
    read_references_for_prompt,
)


def test_reference_reader_outputs_markdown_for_registered_content() -> None:
    output = read_references_for_prompt(
        ReferenceReaderInput(
            skill_id="demo",
            phase_id="main",
            references=[
                {
                    "id": "R1",
                    "path": "refs/r1.md",
                    "summary": "Rules",
                    "content": "Use explicit evidence.",
                }
            ],
        )
    )

    assert "## R1: Rules" in output.markdown
    assert output.used_reference_ids == ["R1"]


def test_reference_reader_fallback_markdown_contains_warn_and_excerpt() -> None:
    markdown = fallback_reference_markdown(
        [
            {
                "id": "R1",
                "summary": "Rules",
                "content": "alpha beta gamma",
            }
        ],
        max_output_tokens=2,
    )

    assert "[F-v3-reference-reader-failed]" in markdown
    assert "alpha beta" in markdown
    assert "gamma" not in markdown


def test_reference_reader_rejects_invalid_output() -> None:
    try:
        output_from_any({"markdown": "", "used_reference_ids": []})
    except ValueError as exc:
        assert "[F-v3-reference-reader-output-invalid]" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid output must fail")
