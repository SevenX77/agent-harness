"""MVP-3 T10: lock startup-side-effect invariants in ``runner.main``.

These tests pin the post-T10 contract:

1. ``core/runner.py`` and ``core/__init__.py`` must not contain any
   direct ``os.environ.*`` / ``sys.path.*`` / ``sys.modules.*`` calls
   (T0-prep ``mvp-3-baseline-snapshot.md`` §2 documents the baseline
   as 0; this test prevents regressions in the wrapped CLI module).
2. ``runner.main`` must wire framework startup through ``Bootstrap``:
   ``apply_patches`` happens before ``run_skill`` invocation, and the
   ``Settings`` snapshot is produced. Replacing the CLI's startup
   sequence with ad-hoc ``os.environ`` mutation re-introduces exactly
   the surface MVP-3 T10 set out to remove.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from graph_agent.bootstrap import Bootstrap
from graph_agent.core import runner as runner_module

SRC_RUNNER = Path(runner_module.__file__)
SRC_CORE_INIT = SRC_RUNNER.parent / "__init__.py"


# Pattern intentionally rejects bare uses (``os.environ.get``,
# ``sys.path.append``, ``sys.modules[...] = ...``); a comment or
# docstring referencing the symbol is fine because we anchor on the
# preceding ``=`` / ``.`` punctuation rather than the bare token.
_HACK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("os.environ assignment / mutation", re.compile(r"\bos\.environ\s*\[")),
    ("os.environ method call", re.compile(r"\bos\.environ\.\w+\s*\(")),
    ("sys.path mutation", re.compile(r"\bsys\.path\.\w+\s*\(")),
    ("sys.path subscript assignment", re.compile(r"\bsys\.path\s*\[")),
    ("sys.modules subscript", re.compile(r"\bsys\.modules\s*\[")),
]


def _scan_for_hacks(path: Path) -> list[tuple[str, int, str]]:
    """Return (pattern_label, line_no, line_text) for each match."""
    findings: list[tuple[str, int, str]] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Strip inline comments before pattern check so docstring/comment
        # mentions of the symbols don't trigger a false positive.
        code_segment = line.split("#", 1)[0]
        for label, pattern in _HACK_PATTERNS:
            if pattern.search(code_segment):
                findings.append((label, line_no, line.strip()))
    return findings


class TestRunnerStartupInvariants:
    def test_runner_py_has_no_direct_environ_or_sys_hacks(self) -> None:
        findings = _scan_for_hacks(SRC_RUNNER)

        assert findings == [], (
            "runner.py must route startup side-effects through Bootstrap; "
            f"found direct hacks: {findings!r}"
        )

    def test_core_init_py_has_no_direct_environ_or_sys_hacks(self) -> None:
        findings = _scan_for_hacks(SRC_CORE_INIT)

        assert findings == [], (
            "core/__init__.py must stay a pure re-export module — no "
            f"startup side-effects; found: {findings!r}"
        )


class TestRunnerMainBootstrapWiring:
    """``runner.main`` must invoke Bootstrap so MVP-3 startup is enforced."""

    def test_main_invokes_bootstrap_apply_patches_before_run_skill(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Stub argv so argparse accepts a minimal CLI invocation.
        skill = tmp_path / "skill.md"
        skill.write_text("# minimal", encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            ["runner", "--skill", str(skill), "--inputs", "{}"],
        )

        call_order: list[str] = []

        # MagicMock spec'd against the real Bootstrap so signature drift
        # surfaces as an ``AttributeError`` instead of silently passing.
        fake_bootstrap = MagicMock(spec=Bootstrap)
        fake_bootstrap.apply_patches.side_effect = lambda: call_order.append("apply_patches")
        fake_bootstrap.load_settings.side_effect = lambda: call_order.append("load_settings")

        def _fake_run_skill(*_args: object, **_kwargs: object) -> dict[str, object]:
            call_order.append("run_skill")
            return {"wall_time_sec": 0.0, "metrics": {}, "trace_path": None}

        with (
            patch("graph_agent.bootstrap.Bootstrap", return_value=fake_bootstrap),
            patch("graph_agent.core.runner.run_skill", _fake_run_skill),
        ):
            runner_module.main()

        assert "apply_patches" in call_order
        assert "load_settings" in call_order
        assert "run_skill" in call_order
        # apply_patches must precede the skill invocation; otherwise the
        # framework runs without monkey-patches in place.
        assert call_order.index("apply_patches") < call_order.index("run_skill")

    def test_main_load_dotenv_runs_between_patches_and_settings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``.env`` loading is sandwiched between apply_patches (which sets
        up patch-level invariants) and load_settings (which freezes the
        Settings snapshot from os.environ). Reordering breaks the
        contract: settings would be read before the .env-supplied keys
        landed."""
        skill = tmp_path / "skill.md"
        skill.write_text("# minimal", encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            ["runner", "--skill", str(skill), "--inputs", "{}"],
        )

        call_order: list[str] = []

        fake_bootstrap = MagicMock(spec=Bootstrap)
        fake_bootstrap.apply_patches.side_effect = lambda: call_order.append("apply_patches")
        fake_bootstrap.load_settings.side_effect = lambda: call_order.append("load_settings")

        def _fake_load_dotenv(*_args: object, **_kwargs: object) -> bool:
            call_order.append("load_dotenv")
            return True

        def _fake_run_skill(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"wall_time_sec": 0.0, "metrics": {}, "trace_path": None}

        with (
            patch("graph_agent.bootstrap.Bootstrap", return_value=fake_bootstrap),
            patch("graph_agent.core.runner.run_skill", _fake_run_skill),
            patch("dotenv.load_dotenv", _fake_load_dotenv),
        ):
            runner_module.main()

        # Required ordering: apply_patches → load_dotenv → load_settings.
        assert call_order.index("apply_patches") < call_order.index("load_dotenv")
        assert call_order.index("load_dotenv") < call_order.index("load_settings")

    def test_main_constructs_and_passes_local_workspace_resolver(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        skill = tmp_path / "skill.md"
        skill.write_text("# minimal", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["runner", "--skill", str(skill), "--inputs", "{}"],
        )

        fake_bootstrap = MagicMock(spec=Bootstrap)
        captured_kwargs: dict[str, object] = {}

        def _fake_run_skill(*_args: object, **kwargs: object) -> dict[str, object]:
            captured_kwargs.update(kwargs)
            return {"wall_time_sec": 0.0, "metrics": {}, "trace_path": None}

        with (
            patch("graph_agent.bootstrap.Bootstrap", return_value=fake_bootstrap),
            patch("graph_agent.core.runner.run_skill", _fake_run_skill),
            patch("dotenv.load_dotenv", return_value=True),
        ):
            runner_module.main()

        resolver = captured_kwargs.get("skill_resolver")
        assert resolver is not None
        assert type(resolver).__name__ == "LocalWorkspaceResolver"
        assert type(resolver).__module__ == "graph_agent.core.local_workspace_resolver"
