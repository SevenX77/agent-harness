from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph

REPO_ROOT = Path(__file__).resolve().parents[4]
GRAPH_AGENT_ROOT = REPO_ROOT / "packages" / "graph-agent"
SCAN_ROOTS = (
    GRAPH_AGENT_ROOT / "src",
    GRAPH_AGENT_ROOT / "tests",
)

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
}

REMOVED_VALIDATORS = (
    "template_variables",
    "prompt_quality",
    "validator_required",
    "tool_paths",
    "persona_resolution",
)

REMOVED_VALIDATOR_TESTS = (
    "test_template_variables.py",
    "test_persona_resolution.py",
    "test_prompt_quality.py",
    "test_tool_paths.py",
    "test_validator_required.py",
)


@dataclass(frozen=True)
class LegacyViolation:
    path: Path
    line_number: int
    reason: str
    line: str

    def render(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{rel}:{self.line_number}: {self.reason}: {self.line.strip()}"


class EmptyResolver:
    def resolve_skill(self, skill_id: str) -> Path:
        raise KeyError(skill_id)


class FixtureResolver:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve_skill(self, skill_id: str) -> Path:
        return {
            "e2e.echo": self.root / "registry" / "echo",
            "e2e.expander": self.root / "registry" / "expander",
        }[skill_id]


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    self_path = Path(__file__).resolve()
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path == self_path:
                continue
            if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache"} for part in path.parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                files.append(path)
    return sorted(files)


def _is_allowed_negative_or_rejection_line(path: Path, line: str) -> bool:
    stripped = line.strip()
    if "assert " in stripped and " not in " in stripped:
        return True
    if "reject" in stripped.lower() or "forbidden" in stripped.lower():
        return True
    if path.name == "test_round14_skill_compilation_cutover.py":
        return True
    return False


def _classify_legacy_line(path: Path, line_number: int, line: str) -> list[LegacyViolation]:
    violations: list[LegacyViolation] = []

    if "v21_migrator" in line:
        violations.append(LegacyViolation(path, line_number, "codemod migrator still present", line))
    if "codemod_v20" in line:
        violations.append(LegacyViolation(path, line_number, "codemod_v20 fixture still present", line))

    if _is_allowed_negative_or_rejection_line(path, line):
        return violations

    if "<python_callable>" in line or "</python_callable>" in line:
        violations.append(LegacyViolation(path, line_number, "legacy <python_callable> tag", line))
    elif ".ast.python_callable" in line:
        violations.append(LegacyViolation(path, line_number, "test reads .ast.python_callable", line))
    elif "python_callable" in line and (
        "required" in line
        or "schema" in path.name
        or path.suffix == ".json"
        or "LogicNodeAST" in line
    ):
        violations.append(LegacyViolation(path, line_number, "python_callable schema/API residue", line))

    if "<steps>" in line or "</steps>" in line:
        violations.append(LegacyViolation(path, line_number, "legacy <steps> shell usage", line))

    context_tokens = ("ContextResolver", "context_resolver", "context_mapping", "_context_mapping")
    if any(token in line for token in context_tokens):
        violations.append(LegacyViolation(path, line_number, "context_mapping/ContextResolver residue", line))

    return violations


def _legacy_violations() -> list[LegacyViolation]:
    violations: list[LegacyViolation] = []
    for path in _iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            violations.extend(_classify_legacy_line(path, line_number, line))
    return violations


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_minimal_v030_logic_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: round18-smoke
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [answer]
    properties:
      answer:
        type: string
phases: [main]
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [answer]
    properties:
      answer:
        type: string
actions: [echo]
validator: false
---
<action>echo</action>
""",
    )
    _write(
        root / "phases" / "main" / "actions" / "echo.py",
        "def echo(context):\n    return {'answer': context.get('text')}\n",
    )


def test_round18_semantic_grep_gate_has_no_real_legacy_usage() -> None:
    violations = _legacy_violations()
    assert not violations, "\n".join(violation.render() for violation in violations[:80])


def test_round18_cognitive_modules_remain_importable() -> None:
    for module_name in (
        "graph_agent.cognitive.finish",
        "graph_agent.cognitive.finish_task",
        "graph_agent.cognitive.md2json",
        "graph_agent.cognitive.md_patch",
    ):
        importlib.import_module(module_name)


def test_round18_dead_modules_are_removed() -> None:
    dead_paths = [
        GRAPH_AGENT_ROOT / "src" / "graph_agent" / "codemod",
        GRAPH_AGENT_ROOT / "src" / "graph_agent" / "io" / "context_resolver.py",
        GRAPH_AGENT_ROOT / "tests" / "core" / "test_v21_codemod.py",
        *(
            GRAPH_AGENT_ROOT
            / "src"
            / "graph_agent"
            / "core"
            / "validators"
            / f"{module}.py"
            for module in REMOVED_VALIDATORS
        ),
        *(
            GRAPH_AGENT_ROOT / "tests" / "core" / "validators" / test_name
            for test_name in REMOVED_VALIDATOR_TESTS
        ),
    ]
    existing = [path.relative_to(REPO_ROOT).as_posix() for path in dead_paths if path.exists()]
    assert not existing, "dead modules still exist:\n" + "\n".join(existing)


def test_round18_collect_ignore_glob_does_not_hide_broken_tests() -> None:
    conftest_path = GRAPH_AGENT_ROOT / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("round18_conftest_probe", conftest_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert getattr(module, "collect_ignore_glob", []) == []


def test_round18_v030_compile_and_runtime_path_still_work(tmp_path: Path) -> None:
    resolver = EmptyResolver()

    fixture = GRAPH_AGENT_ROOT / "tests" / "fixtures" / "v030_e2e_pipeline"
    compiled_fixture = compile_skill(fixture, skill_resolver=FixtureResolver(fixture), cache=False)
    assert compiled_fixture.manifest.schema_version == "v0.3.0"

    _write_minimal_v030_logic_skill(tmp_path)
    graph = assemble_graph(
        compile_skill(tmp_path, skill_resolver=resolver, cache=False),
        skill_resolver=resolver,
    ).graph
    result: dict[str, Any] = graph.invoke(
        {
            "data": {"inputs": {"text": "ok"}},
            "flow": {},
            "messages": [],
            "run_id": "round18-smoke",
        }
    )

    assert result["data"]["phase_outputs"]["main"] == {"answer": "ok"}
