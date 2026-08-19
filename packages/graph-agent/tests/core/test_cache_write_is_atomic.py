"""A compile-cache entry is either the whole snapshot or absent — never half.

`save_to_cache` wrote the snapshot with a plain `write_text`, which opens the
destination file and truncates it before the new bytes land. Two windows open:

* A concurrent `load_from_cache` in another process reads a truncated JSON.
  That half is soft (the reader logs a warning and recompiles), but the wasted
  recompile defeats the cache exactly when two processes race on one skill.
* On Windows, a second process calling `write_text` on the path while the first
  still holds it open raises `PermissionError` (sharing violation), which
  propagates out of `save_to_cache` and kills that compile outright.

The borrowed shape is CPython's own bytecode writer
(`importlib._bootstrap_external._write_atomic`): write to a uniquely-named
sibling temp file, then `os.replace` onto the destination — atomic on one
volume on both POSIX and Windows. One divergence, stated here because the
constraint differs: CPython lets a failed replace propagate; we swallow
`OSError` from the *replace/cleanup* step only, because a cache write is an
optimization — losing it must not fail a compile that already succeeded.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from graph_agent.core import cache as cache_module
from graph_agent.core.cache import load_from_cache, save_to_cache
from graph_agent.core.compiler import compile_skill

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: cache-atomicity-fixture
description: Smallest compilable skill.
io:
  inputs:
    type: object
    required: [text]
    properties:
      text: {type: string}
  outputs:
    type: object
    required: [result]
    properties:
      result: {type: string}
phases: [work]
---
<phase depends_on="input" output>work</phase>
"""

_SKILL_MD = """---
io:
  inputs:
    type: object
    required: [text]
    properties:
      text: {type: string}
  outputs:
    type: object
    required: [result]
    properties:
      result: {type: string}
validator: false
---
<role>echo</role>

<goal>echo {text}</goal>

<step id="S1" name="finish">finish_task result。</step>
"""


def _compiled(tmp_path: Path):
    skill = tmp_path / "cache-atomicity-fixture"
    (skill / "phases" / "work").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "work" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return skill, compile_skill(skill, cache=False)


def test_a_reader_never_sees_a_partial_cache_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every observable state of the cache file parses as complete JSON.

    The destination must go from absent to whole in one step. Hooking the
    writer's own open() would miss the defect class (write_text truncates the
    DESTINATION), so instead every path that ever exists under the cache dir is
    checked to parse — a truncate-then-write sequence fails this the moment the
    interleaved reader thread catches the truncated state.
    """
    monkeypatch.setattr(cache_module, "get_cache_dir", lambda: tmp_path / "cache")
    skill, compiled = _compiled(tmp_path)

    cache_dir = tmp_path / "cache"
    bad_states: list[str] = []
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            target = cache_dir / "k1.json"
            if target.exists():
                try:
                    json.loads(target.read_text(encoding="utf-8"))
                except OSError:
                    # A transiently unopenable file is a cache MISS, not
                    # corruption: `load_from_cache` catches OSError and
                    # recompiles. On Windows a reader can hit this for the
                    # instant of the replace itself; that is the soft edge the
                    # design accepts.
                    continue
                except json.JSONDecodeError:
                    bad_states.append("destination readable but not whole JSON")

    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        for _ in range(50):
            save_to_cache("k1", compiled)
    finally:
        stop.set()
        watcher.join()

    assert not bad_states, bad_states
    assert load_from_cache("k1", skill) is not None


def test_a_locked_destination_does_not_fail_the_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows half: replace onto a path someone holds open must not raise.

    A cache write is an optimization; the compile it serves already succeeded.
    """
    monkeypatch.setattr(cache_module, "get_cache_dir", lambda: tmp_path / "cache")
    _, compiled = _compiled(tmp_path)

    save_to_cache("k2", compiled)
    target = cache_module.get_cache_dir() / "k2.json"
    with open(target, encoding="utf-8"):
        # POSIX replace succeeds into an open file; on Windows this raises
        # PermissionError out of os.replace. Either way the call must return.
        save_to_cache("k2", compiled)


def test_no_temp_files_left_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_module, "get_cache_dir", lambda: tmp_path / "cache")
    _, compiled = _compiled(tmp_path)

    for _ in range(3):
        save_to_cache("k3", compiled)

    leftovers = [p.name for p in cache_module.get_cache_dir().iterdir() if p.name != "k3.json"]
    assert leftovers == [], leftovers
