from __future__ import annotations

import time
from pathlib import Path

import pytest

from graph_agent import assemble_graph, compile_skill

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_ROOT = REPO_ROOT / "skills"
NEGATIVE_CORPUS_SKILLS = {"event-extraction", "text-segmentation"}
NEGATIVE_CORPUS_REASON = "原型阶段 broken skill, 反例 corpus — 触发 [F-v21-actions-keys]"


def _v21_skill_roots() -> list[Path]:
    roots: list[Path] = []
    for graph_md in sorted(SKILLS_ROOT.rglob("GRAPH.md")):
        if "_v2_pending" in graph_md.parts:
            continue
        roots.append(graph_md.parent)
    return roots


def _v21_skill_params() -> list[pytest.ParameterSet]:
    params = []
    for root in _v21_skill_roots():
        skill_id = root.relative_to(SKILLS_ROOT).as_posix()
        marks = []
        if skill_id in NEGATIVE_CORPUS_SKILLS:
            marks.append(pytest.mark.xfail(strict=True, reason=NEGATIVE_CORPUS_REASON))
        params.append(pytest.param(root, marks=marks, id=skill_id))
    return params


@pytest.mark.smoke
@pytest.mark.parametrize("skill_root", _v21_skill_params())
def test_v21_all_skills_compile_assemble_and_cache_hit(
    skill_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("graph_agent.core.cache.get_cache_dir", lambda: tmp_path / "cache")

    first = compile_skill(skill_root, cache=True)
    assembled = assemble_graph(first)
    start = time.perf_counter()
    second = compile_skill(skill_root, cache=True)
    cache_hit_ms = (time.perf_counter() - start) * 1000

    assert assembled.graph is not None
    assert second.manifest.name == first.manifest.name
    assert [phase.id for phase in second.manifest.phases] == [phase.id for phase in first.manifest.phases]
    assert cache_hit_ms <= 200


def test_v21_all_skills_smoke_discovers_current_sources() -> None:
    roots = _v21_skill_roots()

    assert len(roots) == 8
    assert SKILLS_ROOT / "examples" / "subgraph-sample" / "story-deconstruction" in roots
