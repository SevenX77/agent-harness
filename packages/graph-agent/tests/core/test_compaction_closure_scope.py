"""Regression test for the L1295 NameError bug (Gemini audit 2026-04-24).

Before the fix, ``_build_phase_node``'s inner ``execute`` closure called
``self._save_compaction_sidecar(run_id=run_id, ..., storage_manager=storage_manager)``
where both right-hand-side ``run_id`` and ``storage_manager`` were bare
names. But ``_build_phase_node`` is a *method* on GraphAgentHarness —
it's invoked from ``__init__`` (via ``_build_graph``) long before any
``run_id`` variable exists in ``run()``'s locals. The inner closure
captured nothing for those names, so a production invocation that
actually triggered compaction (``plan_verified && wm_updated &&
wm_current``) would raise ``NameError``.

The fix reads both values from ``harness._active_run_context`` at the
call site. This test locks that in by statically parsing ``harness.py``
(and, post-D-7.2, ``phase_executor.py``) with ``ast`` and asserting the
kwargs passed to ``_save_compaction_sidecar`` are attribute accesses
(``active_ctx.run_id`` / ``.storage_manager``), NOT bare ``Name`` nodes.

Why AST and not bytecode? ``inspect.getclosurevars`` can't tell a
``LOAD_GLOBAL run_id`` apart from a ``LOAD_ATTR run_id`` — both put
``"run_id"`` into ``code.co_names``. AST gives us the exact node type.

Why not a real runtime invocation? Driving ``execute`` to its compaction
branch requires a mocked LLM, a real Phase resolver, and several steps
of working-memory mutation — that's E2E integration territory (task
I-3 golden baseline), not unit-test scope.

Post-D-7.2 update: the call site moved out of ``harness.py`` and into
``phase_executor.py``'s ``execute_llm_phase`` as part of the harness
split. The test now scans both files and asserts the invariant holds
at *every* found call site — if a future refactor adds another
compaction call anywhere, it will be checked too.

Post-PHASE3 §6 (M9 Mirror Refactor): the call shape changed from
``self._save_compaction_sidecar(...)`` (Attribute call) to a local
variable ``save_compaction_sidecar(...)`` (Name call) sourced from
``self.container.save_compaction_sidecar``. The matcher now accepts
both patterns so the L1295 NameError guard survives the rename.
"""

from __future__ import annotations

import ast
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[2] / "src" / "graph_agent" / "core"
_SCAN_PATHS = [
    _CORE_DIR / "harness.py",
    _CORE_DIR / "phase_executor.py",
    # Phase 3 M6 (PHASE3_DESIGN.md §2): execute_llm_phase moved into
    # the polymorphic LLMPhaseNode subclass; the compaction call site
    # rides along, so the AST regression guard must scan there too.
    _CORE_DIR / "phase_nodes" / "llm_phase_node.py",
]


def _find_save_compaction_sidecar_calls() -> list[tuple[Path, ast.Call]]:
    """Locate every compaction-sidecar call across scanned modules.

    Returns (file_path, call_node) pairs. Asserts at least one call is
    found so a silent rename / removal breaks loudly.

    Accepts either the legacy ``something._save_compaction_sidecar(...)``
    pattern or the post-M9 ``save_compaction_sidecar(...)`` local-name
    pattern (where the local is sourced from
    ``self.container.save_compaction_sidecar``). The L1295 guard fires
    on the kwargs of whichever form matches.
    """
    accepted_attr_names = {"_save_compaction_sidecar", "save_compaction_sidecar"}
    accepted_local_names = {"save_compaction_sidecar"}
    calls: list[tuple[Path, ast.Call]] = []
    for path in _SCAN_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr in accepted_attr_names) or (
                isinstance(func, ast.Name) and func.id in accepted_local_names
            ):
                calls.append((path, node))

    assert calls, (
        "expected at least one compaction-sidecar call across "
        f"{[p.name for p in _SCAN_PATHS]}, found 0. If the call site "
        "moved to a new module, add it to _SCAN_PATHS."
    )
    return calls


def _kwarg(call: ast.Call, name: str) -> ast.expr:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    raise AssertionError(f"{name}= kwarg missing on _save_compaction_sidecar call")


class TestCompactionCallSiteScope:
    """Static guards against the L1295 NameError regression — at every call site."""

    def test_run_id_kwarg_is_not_a_bare_name(self) -> None:
        """``run_id=run_id`` (bare Name) is the exact bug. Post-fix the
        RHS is an expression reading ``active_ctx.run_id``."""
        for path, call in _find_save_compaction_sidecar_calls():
            rhs = _kwarg(call, "run_id")
            assert not isinstance(rhs, ast.Name), (
                f"regression in {path.name}: run_id=<bare Name> at the "
                "compaction call site. This is the L1295 NameError the "
                "Gemini audit caught on 2026-04-24. Read it from "
                "harness._active_run_context.run_id instead."
            )

    def test_storage_manager_kwarg_is_not_a_bare_name(self) -> None:
        """Same class of bug as ``run_id`` — ``storage_manager`` wasn't
        in the closure's scope either."""
        for path, call in _find_save_compaction_sidecar_calls():
            rhs = _kwarg(call, "storage_manager")
            assert not isinstance(rhs, ast.Name), (
                f"regression in {path.name}: storage_manager=<bare Name> "
                "at the compaction call site. Read from "
                "harness._active_run_context.storage_manager."
            )

    def test_run_id_expression_reads_from_per_run_context(self) -> None:
        """Belt-and-braces: the expression must textually reference the
        per-run context — either the legacy ``_active_run_context`` /
        ``active_ctx`` alias or, post-Phase-B, the executor's own
        ``_run_context`` field (``self._run_context`` typically aliased
        as ``active_ctx`` in the executor's closure)."""
        accepted_fragments = ("_active_run_context", "active_ctx", "_run_context")
        for path, call in _find_save_compaction_sidecar_calls():
            rhs_src = ast.unparse(_kwarg(call, "run_id"))
            assert any(f in rhs_src for f in accepted_fragments), (
                f"run_id kwarg at compaction site in {path.name} does not "
                f"read from a per-run RunContext-derived expression. "
                f"Got: {rhs_src!r}. Accepted fragments: {accepted_fragments}"
            )
