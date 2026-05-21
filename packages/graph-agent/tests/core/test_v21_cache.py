from __future__ import annotations

import time
from pathlib import Path

import pytest
from graph_agent.core.cache import compute_cache_key
from graph_agent.core.compiler import compile_skill
from tests.core.test_v21_graph_assembly import _base, _logic

_FIXTURES = Path(__file__).parents[1] / "fixtures"


def _cache_root(tmp_path: Path, monkeypatch) -> Path:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr("graph_agent.core.cache.get_cache_dir", lambda: cache_dir)
    return cache_dir


def test_cache_miss_then_hit(tmp_path: Path, monkeypatch) -> None:
    cache_dir = _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)

    first = compile_skill(skill, cache=True)
    second = compile_skill(skill, cache=True)

    assert first.manifest.name == second.manifest.name
    assert len(list(cache_dir.glob("*.json"))) == 1


def test_cache_invalidate_on_graph_md_change(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    key1 = compute_cache_key(skill)
    (skill / "GRAPH.md").write_text((skill / "GRAPH.md").read_text() + "\n", encoding="utf-8")
    key2 = compute_cache_key(skill)
    assert key1 != key2


def test_cache_invalidate_on_phase_file_change(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    key1 = compute_cache_key(skill)
    phase_file = skill / "phases" / "logic" / "LOGIC.md"
    phase_file.write_text(phase_file.read_text() + "\n", encoding="utf-8")
    key2 = compute_cache_key(skill)
    assert key1 != key2


def test_cache_invalidate_on_io_file_change(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    key1 = compute_cache_key(skill)
    outputs = skill / "io" / "outputs.json"
    outputs.write_text("{}\n", encoding="utf-8")
    key2 = compute_cache_key(skill)
    assert key1 != key2


def test_cache_performance_hit_under_200ms(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    compile_skill(skill, cache=True)

    start = time.perf_counter()
    compile_skill(skill, cache=True)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms <= 200


def test_cache_cross_python_version_isolation(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    key1 = compute_cache_key(skill)
    monkeypatch.setattr("graph_agent.core.cache.sys.version_info", (9, 9, 9))
    key2 = compute_cache_key(skill)
    assert key1 != key2


def test_cache_hit_restores_subagents_by_phase(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = _FIXTURES / "subagent_minimal"

    compile_skill(skill, cache=True)
    cached = compile_skill(skill, cache=True)

    subagents = cached.subagents_by_phase["main"]
    tools = {tool.name for tool in cached.tools.for_phase("main")}
    assert subagents[0].name == "echo_expert"
    assert subagents[0].input_model.model_validate({"text": "hello"}).text == "hello"
    assert "call_subagent_echo_expert" in tools


def test_cache_hit_restores_phase_tokens(tmp_path: Path, monkeypatch) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)

    compile_skill(skill, cache=True)
    cached = compile_skill(skill, cache=True)

    token = cached.phase_tokens["logic"]
    assert token.phase_id == "logic"
    assert token.attrs["src"] == "phases/logic"
    assert token.raw_text.startswith("<phase")


def test_cache_write_failure_warns_and_returns_compiled_skill(
    tmp_path: Path, monkeypatch
) -> None:
    _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)

    def raise_permission_error(self, *args, **kwargs) -> None:
        raise PermissionError("cache dir is not writable")

    monkeypatch.setattr(Path, "mkdir", raise_permission_error)

    with pytest.warns(RuntimeWarning, match="cache write failed"):
        compiled = compile_skill(skill, cache=True)

    assert compiled.manifest.name == "assembly-test"


def test_cache_read_failure_falls_back_to_compile(tmp_path: Path, monkeypatch) -> None:
    cache_dir = _cache_root(tmp_path, monkeypatch)
    skill = tmp_path / "skill"
    _base(skill, '<phase id="logic" src="phases/logic" depends_on="" />\n')
    _logic(skill)
    key = compute_cache_key(skill)
    cache_dir.mkdir(parents=True)
    (cache_dir / f"{key}.json").write_text("{not json", encoding="utf-8")

    compiled = compile_skill(skill, cache=True)

    assert compiled.manifest.name == "assembly-test"
