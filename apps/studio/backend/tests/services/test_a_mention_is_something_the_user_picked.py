"""A mention is one object the user picked, addressed by the ref they picked it with.

Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
F4 + decision COPILOT_ASSIST-8. The rules these tests hold the resolver to:

* identity is ``(kind, ref)`` and nothing else — `label` is for echoing back
  what the user saw, never for finding anything;
* `file` / `phase` point at something the workspace can read out right now, so
  the backend injects the content;
* `dot` / `error` / `trace` point at something that only existed during one run
  or one compile, so the backend injects the reference and lets the copilot's
  own tools fetch it — deciding WHICH run's value is the model's call, not the
  shell's;
* a ref that resolves to nothing is named in the echo and the turn still goes:
  dropping it silently would let the user believe it went in.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.models.copilot import CopilotMention
from app.services.copilot_context import (
    MENTION_CONTENT_BUDGET,
    mention_echo_lines,
    render_mentions_xml,
    resolve_mentions,
)


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    root = tmp_path / "story-deconstruction"
    (root / "phases" / "plan").mkdir(parents=True)
    (root / "phases" / "plan" / "LOGIC.md").write_text("# plan phase\n", encoding="utf-8")
    (root / "subgraph" / "event-timeline" / "phases" / "review").mkdir(parents=True)
    (root / "subgraph" / "event-timeline" / "phases" / "review" / "SKILL.md").write_text(
        "# nested review phase\n", encoding="utf-8"
    )
    (root / "GRAPH.md").write_text("# graph\n", encoding="utf-8")
    (tmp_path / "outside.md").write_text("not part of this skill\n", encoding="utf-8")
    return root


def _mention(kind: str, ref: str, label: str | None = None) -> CopilotMention:
    return CopilotMention(kind=kind, ref=ref, label=label or ref)


def test_a_file_mention_injects_the_file_the_ref_names(skill_dir: Path) -> None:
    (resolved,) = resolve_mentions([_mention("file", "GRAPH.md")], skill_dir=skill_dir)

    assert resolved.content == "# graph\n"
    assert resolved.failure is None


def test_a_phase_mention_finds_that_phase_s_node_file(skill_dir: Path) -> None:
    (resolved,) = resolve_mentions([_mention("phase", "plan")], skill_dir=skill_dir)

    assert resolved.content == "# plan phase\n"
    assert resolved.source_path == "phases/plan/LOGIC.md"


def test_a_phase_inside_a_subgraph_is_addressed_through_it(skill_dir: Path) -> None:
    (resolved,) = resolve_mentions([_mention("phase", "event-timeline/review")], skill_dir=skill_dir)

    assert resolved.content == "# nested review phase\n"
    assert resolved.source_path == "subgraph/event-timeline/phases/review/SKILL.md"


def test_the_label_never_decides_what_is_read(skill_dir: Path) -> None:
    """The display name drifts; the thing the user picked does not."""
    (resolved,) = resolve_mentions(
        [_mention("file", "GRAPH.md", label="phases/plan/LOGIC.md")],
        skill_dir=skill_dir,
    )

    assert resolved.content == "# graph\n"


@pytest.mark.parametrize(
    ("kind", "ref"),
    [("dot", "draft.summary"), ("error", "F-v3-graph-phase-island@GRAPH.md:4"), ("trace", "run-7#12")],
)
def test_a_run_scoped_mention_is_injected_as_a_reference(skill_dir: Path, kind: str, ref: str) -> None:
    (resolved,) = resolve_mentions([_mention(kind, ref)], skill_dir=skill_dir)

    assert resolved.content is None, "the shell must not decide which run's value this is"
    assert resolved.failure is None, "a reference-only mention is resolved, not failed"
    assert ref in render_mentions_xml([resolved])


def test_a_ref_that_climbs_out_of_the_skill_is_refused(skill_dir: Path) -> None:
    (resolved,) = resolve_mentions([_mention("file", "../outside.md")], skill_dir=skill_dir)

    assert resolved.content is None
    assert resolved.failure is not None
    assert "not part of this skill" not in render_mentions_xml([resolved])


def test_an_unresolvable_ref_is_named_rather_than_dropped(skill_dir: Path) -> None:
    resolved = resolve_mentions(
        [_mention("file", "deleted.md"), _mention("file", "GRAPH.md")],
        skill_dir=skill_dir,
    )

    assert len(resolved) == 2, "the failed one keeps its place; the turn still goes"
    assert resolved[0].failure is not None
    assert resolved[1].content == "# graph\n"
    echo = "\n".join(mention_echo_lines(resolved))
    assert "deleted.md" in echo
    assert "GRAPH.md" in echo


def test_content_over_the_turn_budget_is_truncated_and_says_so(skill_dir: Path) -> None:
    (skill_dir / "huge.md").write_text("x" * (MENTION_CONTENT_BUDGET + 500), encoding="utf-8")

    (resolved,) = resolve_mentions([_mention("file", "huge.md")], skill_dir=skill_dir)

    assert resolved.truncated is True
    assert resolved.content is not None
    assert len(resolved.content) == MENTION_CONTENT_BUDGET
    assert "truncated" in "\n".join(mention_echo_lines([resolved])).lower()


def test_the_budget_covers_the_whole_turn_not_one_mention(skill_dir: Path) -> None:
    half = MENTION_CONTENT_BUDGET // 2 + 100
    (skill_dir / "a.md").write_text("a" * half, encoding="utf-8")
    (skill_dir / "b.md").write_text("b" * half, encoding="utf-8")

    first, second = resolve_mentions(
        [_mention("file", "a.md"), _mention("file", "b.md")],
        skill_dir=skill_dir,
    )

    assert first.truncated is False
    assert second.truncated is True
    assert len(first.content or "") + len(second.content or "") == MENTION_CONTENT_BUDGET


def test_the_echo_distinguishes_content_from_reference(skill_dir: Path) -> None:
    resolved = resolve_mentions(
        [_mention("file", "GRAPH.md"), _mention("dot", "draft.summary")],
        skill_dir=skill_dir,
    )

    file_line, dot_line = mention_echo_lines(resolved)
    assert "GRAPH.md" in file_line
    assert "draft.summary" in dot_line
    assert file_line != dot_line
    assert "reference" in dot_line.lower(), "the user must see which kind they got"


def test_nothing_mentioned_renders_nothing(skill_dir: Path) -> None:
    assert resolve_mentions([], skill_dir=skill_dir) == ()
    assert render_mentions_xml(()) == ""
    assert mention_echo_lines(()) == []
