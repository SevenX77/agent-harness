from __future__ import annotations

import time
from pathlib import Path

from graph_agent.core.cache import compute_cache_key
from graph_agent.core.compiler import compile_skill

from tests.core.test_v21_graph_assembly import _base, _logic


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
