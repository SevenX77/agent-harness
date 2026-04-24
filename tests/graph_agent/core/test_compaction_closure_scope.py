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
with ``ast`` and asserting the kwargs passed to ``_save_compaction_sidecar``
are attribute accesses (``active_ctx.run_id`` / ``.storage_manager``),
NOT bare ``Name`` nodes.

Why AST and not bytecode? ``inspect.getclosurevars`` can't tell a
``LOAD_GLOBAL run_id`` apart from a ``LOAD_ATTR run_id`` — both put
``"run_id"`` into ``code.co_names``. AST gives us the exact node type.

Why not a real runtime invocation? Driving ``execute`` to its compaction
branch requires a mocked LLM, a real Phase resolver, and several steps
of working-memory mutation — that's E2E integration territory (task
I-3 golden baseline), not unit-test scope.
"""
from __future__ import annotations

import ast
from pathlib import Path


_HARNESS_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "core"
    / "graph_agent"
    / "core"
    / "harness.py"
)


def _find_save_compaction_sidecar_call() -> ast.Call:
    """Locate the compaction-sidecar call inside ``_build_phase_node``.

    Raises AssertionError if we can't find it — the call must exist and
    must be exactly one (otherwise the test's invariant is ambiguous).
    """
    source = _HARNESS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    matches: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "_save_compaction_sidecar":
            matches.append(node)

    assert len(matches) == 1, (
        f"expected exactly one call to _save_compaction_sidecar in harness.py, "
        f"found {len(matches)}. If compaction site count changed, update this "
        f"test to check each site."
    )
    return matches[0]


def _kwarg(call: ast.Call, name: str) -> ast.expr:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    raise AssertionError(f"{name}= kwarg missing on _save_compaction_sidecar call")


class TestCompactionCallSiteScope:
    """Static guards against the L1295 NameError regression."""

    def test_run_id_kwarg_is_not_a_bare_name(self) -> None:
        """``run_id=run_id`` (bare Name) is the exact bug. Post-fix the
        RHS is an expression reading ``active_ctx.run_id``."""
        call = _find_save_compaction_sidecar_call()
        rhs = _kwarg(call, "run_id")
        assert not isinstance(rhs, ast.Name), (
            "regression: run_id=<bare Name> at the compaction call site. "
            "This is the L1295 NameError the Gemini audit caught on 2026-04-24. "
            "Read it from harness._active_run_context.run_id instead."
        )

    def test_storage_manager_kwarg_is_not_a_bare_name(self) -> None:
        """Same class of bug as ``run_id`` — ``storage_manager`` wasn't
        in the closure's scope either."""
        call = _find_save_compaction_sidecar_call()
        rhs = _kwarg(call, "storage_manager")
        assert not isinstance(rhs, ast.Name), (
            "regression: storage_manager=<bare Name> at the compaction call "
            "site. Read from harness._active_run_context.storage_manager."
        )

    def test_run_id_expression_mentions_active_run_context(self) -> None:
        """Belt-and-braces: the expression must textually reference
        ``_active_run_context`` so the fix direction can't drift."""
        call = _find_save_compaction_sidecar_call()
        rhs_src = ast.unparse(_kwarg(call, "run_id"))
        assert "_active_run_context" in rhs_src or "active_ctx" in rhs_src, (
            f"run_id kwarg at compaction site does not read from the active "
            f"RunContext. Got: {rhs_src!r}"
        )
