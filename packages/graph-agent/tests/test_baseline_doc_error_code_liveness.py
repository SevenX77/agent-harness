"""Engine `baseline.md` docs must not present a dead error code as a live gate.

A `baseline.md` under `docs/engine/mvp1/` has exactly one job: describe the
CURRENT implementation state. So when such a doc cites an `[F-v3-*]` error code
as something the engine raises, the engine source must actually contain an
emission site for it. A code that exists only in
`packages/graph-agent/src/graph_agent/core/error_registry.py` is registry
metadata, not a live gate, and a baseline doc must say so explicitly.

Observable defect this test reproduces (状态 before the fix)
-----------------------------------------------------------
`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md:54` said:

    - **子图 outputs 仍严校**(编译期):同函数继续要求父 `SUBGRAPH.md io.outputs`
      与子 `GRAPH.md io.outputs` 整个 schema 相等;不一致报
      `[F-v3-subgraph-io-mismatch]`,错误信息标明 `outputs do not match`。

and `:86` said:

    - **子图 io 现状**:inputs 已放宽(`loader.py:528` 不再比较 inputs);outputs
      仍强制相等并用 `[F-v3-subgraph-io-mismatch]` fatal。

Both statements are false. The gate was deleted on 2026-06-20 by commit
`cad7dbc0` ("feat(engine): relax subgraph io.outputs 1:1 compile gate
(n2-iopanel#30)"), whose diff removes the `parent_outputs != child_outputs`
comparison and its `_fatal(...)` call from `_validate_subgraph_io_contracts` in
`packages/graph-agent/src/graph_agent/core/loader.py`. That commit's message
states the retention rule this test encodes:

    The error code is retained in the registry (no longer emitted) to preserve
    the round28 registry<->owner bijection + len==97 count.

Mechanical confirmation on the tree this test was written against:
`grep -rn "outputs do not match" packages/graph-agent/src/` returns nothing, and
`[F-v3-subgraph-io-mismatch]` appears in engine source only at
`error_registry.py:95`.

Why the marker, and why not an allowlist
----------------------------------------
Legitimate baseline prose sometimes has to name a code that has no emitter -
precisely in order to record that it has none. Rather than keep a hand-curated
allowlist of "codes we are allowed to mention" (which would rot exactly the way
the prose it guards rots), the doc line itself must carry the fact:
`ERROR_CODE_NO_EMITTER_MARKER`. The assertion and the documentation are then the
same token, so a line cannot drift back to claiming a live gate while staying
green.

This mirrors `test_doc_hash_lock.py`, which likewise pairs synthetic fixture
tests of the pure checking function with one assertion over the real corpus.
It deliberately does NOT reuse that test's `_doc-exemptions.yaml` mechanism:
that file exists to record owner-approved *pending* drift with an approval
trail, whereas a retired error code is a permanent, self-evident fact that
belongs in the sentence describing it, not in a side file.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SRC_ROOT = REPO_ROOT / "packages" / "graph-agent" / "src" / "graph_agent"
ERROR_REGISTRY_PATH = ENGINE_SRC_ROOT / "core" / "error_registry.py"
BASELINE_DOCS_ROOT = REPO_ROOT / "docs" / "engine" / "mvp1"

ERROR_CODE_PATTERN = re.compile(r"\[F-v3-[a-z0-9-]+\]")

#: Marker a baseline line must carry to cite a code the engine never raises.
ERROR_CODE_NO_EMITTER_MARKER = "无发出点"

NO_EMITTER_REMEDIATION = (
    "either the doc is stale (rewrite the line to stop describing the code as a live gate, "
    f"and mark it with '{ERROR_CODE_NO_EMITTER_MARKER}'), or the gate was lost and the engine "
    "must emit the code again"
)


def collect_emitted_error_codes(engine_src_root: Path, registry_path: Path) -> set[str]:
    """Return every `[F-v3-*]` code that engine source raises.

    The registry module is excluded on purpose: it declares metadata for every
    code that exists, so including it would make every code look live.
    """
    emitted: set[str] = set()
    registry_resolved = registry_path.resolve()
    for module_path in sorted(engine_src_root.rglob("*.py")):
        if module_path.resolve() == registry_resolved:
            continue
        emitted |= set(ERROR_CODE_PATTERN.findall(module_path.read_text(encoding="utf-8")))
    return emitted


def collect_dead_code_citations(*, docs_root: Path, emitted_codes: set[str]) -> list[str]:
    """Report baseline lines citing a code with no emitter and no marker."""
    violations: list[str] = []
    for doc_path in sorted(docs_root.rglob("baseline.md")):
        relative_path = doc_path.relative_to(docs_root).as_posix()
        for line_number, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
            if ERROR_CODE_NO_EMITTER_MARKER in line:
                continue
            for code in sorted(set(ERROR_CODE_PATTERN.findall(line))):
                if code not in emitted_codes:
                    violations.append(
                        f"{relative_path}:{line_number}: cites {code}, which no engine module emits; "
                        f"remediation: {NO_EMITTER_REMEDIATION}"
                    )
    return violations


def test_dead_code_citation_is_reported_unless_the_line_carries_the_marker(tmp_path: Path) -> None:
    docs_root = tmp_path / "mvp1"
    unit_dir = docs_root / "02-mechanism" / "some-unit"
    unit_dir.mkdir(parents=True)
    (unit_dir / "baseline.md").write_text(
        "- live gate reports `[F-v3-live-code]`.\n"
        "- stale claim: 不一致报 `[F-v3-dead-code]`。\n"
        f"- honest record: `[F-v3-dead-code]` registry 保留,引擎源码{ERROR_CODE_NO_EMITTER_MARKER}。\n",
        encoding="utf-8",
    )

    violations = collect_dead_code_citations(docs_root=docs_root, emitted_codes={"[F-v3-live-code]"})

    assert len(violations) == 1, violations
    assert "some-unit/baseline.md:2" in violations[0]
    assert "[F-v3-dead-code]" in violations[0]


def test_only_baseline_docs_are_scanned(tmp_path: Path) -> None:
    """Design/contract docs state the TARGET design, so they are out of scope here."""
    docs_root = tmp_path / "mvp1"
    unit_dir = docs_root / "01-contract" / "some-unit"
    unit_dir.mkdir(parents=True)
    (unit_dir / "mvp1-alignment.md").write_text("`[F-v3-dead-code]` 编译期\n", encoding="utf-8")

    assert collect_dead_code_citations(docs_root=docs_root, emitted_codes=set()) == []


def test_registry_module_alone_does_not_make_a_code_live(tmp_path: Path) -> None:
    engine_src = tmp_path / "graph_agent"
    (engine_src / "core").mkdir(parents=True)
    registry_path = engine_src / "core" / "error_registry.py"
    registry_path.write_text("REGISTRY = {'[F-v3-dead-code]': ..., '[F-v3-live-code]': ...}\n", encoding="utf-8")
    (engine_src / "core" / "loader.py").write_text("_fatal('[F-v3-live-code] boom')\n", encoding="utf-8")

    emitted = collect_emitted_error_codes(engine_src, registry_path)

    assert emitted == {"[F-v3-live-code]"}


def test_engine_baseline_docs_do_not_describe_unemitted_error_codes_as_live() -> None:
    emitted_codes = collect_emitted_error_codes(ENGINE_SRC_ROOT, ERROR_REGISTRY_PATH)
    assert "[F-v3-subgraph-io-mismatch]" not in emitted_codes, (
        "guard premise broken: the subgraph io.outputs gate removed by cad7dbc0 is emitted again"
    )

    violations = collect_dead_code_citations(docs_root=BASELINE_DOCS_ROOT, emitted_codes=emitted_codes)

    assert not violations, "Engine baseline docs describe error codes the engine never raises:\n" + "\n".join(violations)
