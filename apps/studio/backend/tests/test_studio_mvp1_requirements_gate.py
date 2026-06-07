from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
SPEC_DIR = REPO_ROOT / ".kiro" / "specs" / "studio-mvp1"
WS0_REQUIREMENTS = SPEC_DIR / "requirements-ws0.md"
SELF_RELATIVE_PATH = "apps/studio/backend/tests/test_studio_mvp1_requirements_gate.py"

REQUIRED_FRONTMATTER_KEYS = {
    "ws_id",
    "modules",
    "depends_on",
    "blocks",
    "owns_files",
    "spec_ssot",
    "status",
}
REQUIRED_SECTION_NUMBERS = range(1, 13)
KNOWN_WS_IDS = {f"WS-{index}" for index in range(0, 9)}
PM_BOUNDARY_PATTERNS = [
    re.compile(r"^##+\s*(?:Phase|Implementation|实现阶段|实施阶段)\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"before\s*->\s*after", re.IGNORECASE),
    re.compile(r"before\s*→\s*after", re.IGNORECASE),
    re.compile(r"改第\s*\d+\s*行"),
    re.compile(r"^\s*[-*]\s*\[\s*\]\s*(?:Step|步骤)\s*\d+", re.IGNORECASE | re.MULTILINE),
]
FORBIDDEN_PRECONTRACT_ARTIFACT_PATTERNS = (
    "task-ws*.md",
    "tasks-ws*.md",
    "gemini-prompt-ws*.md",
)
EXPECTED_OWNS_BY_WS = {
    "WS-1": {
        "apps/studio/tauri/src/lib.rs",
        "apps/studio/tauri/src/sidecar.rs",
        "apps/studio/frontend/src/lib/tauri.ts",
        "apps/studio/frontend/src/config/runtime.ts",
        "apps/studio/frontend/src/App.tsx",
        "apps/studio/frontend/src/components/studio/Workspace.tsx",
        "apps/studio/frontend/src/components/studio/Header.tsx",
        "apps/studio/frontend/src/components/welcome/",
        "apps/studio/backend/app/routers/skills.py",
        "apps/studio/backend/app/services/skills.py",
    },
    "WS-2": {
        "apps/studio/frontend/src/components/GraphCanvas/",
        "apps/studio/frontend/src/components/nodes/SkillNode.tsx",
        "apps/studio/frontend/src/components/edges/ContextEdge.tsx",
        "apps/studio/frontend/src/components/studio/panels/",
        "apps/studio/frontend/src/components/studio/SplitEditor.tsx",
        "apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx",
        "apps/studio/frontend/src/api/client.ts",
    },
    "WS-3": {
        "apps/studio/frontend/src/components/studio/Workspace.tsx",
        "apps/studio/frontend/src/components/studio/center-action-bar.tsx",
        "apps/studio/frontend/src/components/TracePanel.tsx",
        "apps/studio/frontend/src/components/trace/",
        "apps/studio/frontend/src/hooks/useRunStream*",
        "apps/studio/frontend/src/components/history/",
        "apps/studio/backend/app/routers/runs.py",
        "apps/studio/backend/app/services/run_manager.py",
        "apps/studio/backend/app/services/predictor.py",
    },
    "WS-4": {
        "apps/studio/frontend/src/components/studio/settings/",
        "apps/studio/frontend/src/components/studio/api-keys/",
        "apps/studio/frontend/src/api/llm.ts",
        "apps/studio/frontend/src/api/types.ts",
        "apps/studio/backend/app/routers/llm.py",
        "apps/studio/backend/app/services/llm_",
        "apps/studio/backend/app/models/llm_config.py",
    },
    "WS-5": {
        "apps/studio/frontend/src/components/copilot/",
        "apps/studio/frontend/src/store/copilotStore.ts",
        "apps/studio/frontend/src/hooks/useCopilot.ts",
        "apps/studio/backend/app/services/copilot.py",
        "apps/studio/backend/app/routers/copilot.py",
        "apps/studio/backend/app/routers/llm.py",
        "apps/studio/frontend/src/components/studio/settings/copilot/",
    },
    "WS-6": {
        "apps/studio/backend/app/services/golden_diff.py",
        "apps/studio/backend/app/services/artifact_registry.py",
        "apps/studio/backend/app/routers/golden.py",
        "apps/studio/backend/app/routers/compare.py",
        "apps/studio/backend/app/routers/skills.py",
        "apps/studio/frontend/src/components/diff/",
        "apps/studio/frontend/src/components/history/",
        "apps/studio/frontend/src/components/studio/Header.tsx",
    },
    "WS-7": {
        "apps/studio/frontend/src/index.css",
        "apps/studio/frontend/src/lib/llm-error-messages.ts",
        "apps/studio/frontend/src/components/ui/",
    },
    "WS-8": {
        "apps/studio/backend/app/routers/debug.py",
        "apps/studio/backend/app/routers/runs.py",
        "apps/studio/frontend/src/components/history/",
        "apps/studio/frontend/src/components/trace/",
        "apps/studio/frontend/src/components/studio/Workspace.tsx",
    },
}


@dataclass(frozen=True)
class RequirementsDoc:
    path: Path
    relative_path: str
    frontmatter: dict[str, Any]
    body: str


def _read_markdown_with_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.relative_to(REPO_ROOT)} must start with YAML frontmatter"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.relative_to(REPO_ROOT)} must close YAML frontmatter"
    frontmatter = yaml.safe_load(text[4:end]) or {}
    assert isinstance(frontmatter, dict), f"{path.relative_to(REPO_ROOT)} frontmatter must be a mapping"
    return frontmatter, text[end + len("\n---\n") :]


def _load_ws0_frontmatter() -> dict[str, Any]:
    frontmatter, _ = _read_markdown_with_frontmatter(WS0_REQUIREMENTS)
    return frontmatter


def _expected_requirements_paths() -> list[Path]:
    owns_files = _load_ws0_frontmatter()["owns_files"]
    assert isinstance(owns_files, list), "WS-0 owns_files must be a list"
    paths: list[Path] = []
    for item in owns_files:
        assert isinstance(item, str), "WS-0 owns_files entries must be strings"
        if item.startswith(".kiro/specs/studio-mvp1/requirements-ws") and item != (
            ".kiro/specs/studio-mvp1/requirements-ws0.md"
        ):
            paths.append(REPO_ROOT / item)
    return paths


def _load_existing_expected_docs() -> list[RequirementsDoc]:
    docs: list[RequirementsDoc] = []
    for path in _expected_requirements_paths():
        if not path.exists():
            continue
        frontmatter, body = _read_markdown_with_frontmatter(path)
        docs.append(
            RequirementsDoc(
                path=path,
                relative_path=path.relative_to(REPO_ROOT).as_posix(),
                frontmatter=frontmatter,
                body=body,
            )
        )
    return docs


def _section(doc: RequirementsDoc, number: int) -> str:
    pattern = re.compile(rf"^## {number}\.[^\n]*\n(?P<body>.*?)(?=^## {number + 1}\.|^## \d+\.|\Z)", re.S | re.M)
    match = pattern.search(doc.body)
    return match.group("body") if match else ""


def _body_has_any(body: str, needles: tuple[str, ...]) -> bool:
    return any(needle in body for needle in needles)


def _ws_key(doc: RequirementsDoc) -> str | None:
    ws_id = doc.frontmatter.get("ws_id")
    if not isinstance(ws_id, str):
        return None
    match = re.match(r"^(WS-\d+)(?:-|$)", ws_id)
    return match.group(1) if match else None


def _owns_contains(owns_files: list[str], expected: str) -> bool:
    if expected.endswith("/") or expected.endswith("_") or expected.endswith("*"):
        return any(owned.startswith(expected.rstrip("*")) for owned in owns_files)
    return expected in owns_files


def _is_allowed_test_or_spec_owned_file(owned_file: str) -> bool:
    return (
        "/tests/" in owned_file
        or owned_file.endswith(".test.ts")
        or owned_file.endswith(".test.tsx")
        or owned_file.startswith(".kiro/specs/studio-mvp1/requirements-")
    )


def test_ws0_owns_the_requirements_gate_test() -> None:
    owns_files = _load_ws0_frontmatter()["owns_files"]

    assert SELF_RELATIVE_PATH in owns_files


def test_studio_mvp1_has_no_precontract_task_or_prompt_artifacts() -> None:
    forbidden = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for pattern in FORBIDDEN_PRECONTRACT_ARTIFACT_PATTERNS
        for path in SPEC_DIR.glob(pattern)
    )

    assert not forbidden, (
        "WS-0 contract gate must run before task files or Gemini prompts are produced.\n"
        f"Forbidden pre-contract artifacts: {forbidden}"
    )


def test_studio_mvp1_ws_requirements_files_match_ws0_manifest() -> None:
    expected_paths = _expected_requirements_paths()
    expected_relative = {path.relative_to(REPO_ROOT).as_posix() for path in expected_paths}
    actual_relative = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in SPEC_DIR.glob("requirements-ws*.md")
        if path.name != "requirements-ws0.md"
    }

    missing = sorted(expected_relative - actual_relative)
    extra_or_misnamed = sorted(actual_relative - expected_relative)

    assert not missing and not extra_or_misnamed, (
        "Studio MVP1 WS requirements files must match WS-0 owns_files.\n"
        f"Missing expected files: {missing}\n"
        f"Extra or misnamed files: {extra_or_misnamed}"
    )


def test_studio_mvp1_ws_requirements_follow_task_spec_template() -> None:
    violations: list[str] = []
    for doc in _load_existing_expected_docs():
        missing_keys = sorted(REQUIRED_FRONTMATTER_KEYS - set(doc.frontmatter))
        if missing_keys:
            violations.append(f"{doc.relative_path}: missing frontmatter keys {missing_keys}")

        for key in ("modules", "depends_on", "blocks", "owns_files", "spec_ssot"):
            value = doc.frontmatter.get(key)
            if not isinstance(value, list):
                violations.append(f"{doc.relative_path}: frontmatter {key} must be a list")

        ws_id = doc.frontmatter.get("ws_id")
        if not isinstance(ws_id, str) or not re.fullmatch(r"WS-\d+-[a-z0-9-]+", ws_id):
            violations.append(f"{doc.relative_path}: ws_id must use WS-N-short-slug form")

        for dependency in doc.frontmatter.get("depends_on", []) or []:
            if isinstance(dependency, str) and dependency.startswith("WS-") and dependency not in KNOWN_WS_IDS:
                violations.append(f"{doc.relative_path}: depends_on uses non-canonical WS dependency {dependency!r}")

        if not re.search(r"^# .+", doc.body, re.M):
            violations.append(f"{doc.relative_path}: missing title")

        for section_number in REQUIRED_SECTION_NUMBERS:
            if not re.search(rf"^## {section_number}\.", doc.body, re.M):
                violations.append(f"{doc.relative_path}: missing section ## {section_number}.")

    assert not violations, "Studio MVP1 requirements template violations:\n" + "\n".join(violations)


def test_studio_mvp1_ws_requirements_encode_contract_gates() -> None:
    violations: list[str] = []
    for doc in _load_existing_expected_docs():
        section_2 = _section(doc, 2)
        section_6 = _section(doc, 6)
        section_8 = _section(doc, 8)
        section_9 = _section(doc, 9)
        section_12 = _section(doc, 12)
        spec_ssot_text = "\n".join(str(item) for item in doc.frontmatter.get("spec_ssot", []))
        owns_text = "\n".join(str(item) for item in doc.frontmatter.get("owns_files", []))
        combined_grounding = f"{spec_ssot_text}\n{section_2}"

        for needle in ("mvp1-alignment.md", "baseline.md", "DESIGN_UNITS_INDEX.md", "01_workflows"):
            if needle not in combined_grounding:
                violations.append(f"{doc.relative_path}: SSOT grounding must include {needle}")

        if ".kiro/specs/studio-" in combined_grounding:
            violations.append(f"{doc.relative_path}: historical .kiro Studio specs must not be design SSOT")

        if not _body_has_any(section_6, ("RED", "失败测试", "先失败")):
            violations.append(f"{doc.relative_path}: section 6 must name RED/failing tests")
        if not _body_has_any(section_6, ("真实 e2e", "真实端到端", "手动验证")):
            violations.append(f"{doc.relative_path}: section 6 must include real e2e or manual validation")
        if "fake mock" not in section_6 and "不许 fake" not in section_6 and "不允许 fake" not in section_6:
            violations.append(f"{doc.relative_path}: section 6 must mark no-fake boundaries")

        if "- [ ]" not in section_8:
            violations.append(f"{doc.relative_path}: section 8 must use checklist hard-exit items")
        if "测试" not in section_8:
            violations.append(f"{doc.relative_path}: section 8 must require tests to pass")
        if not _body_has_any(section_8, ("真实 e2e", "真实端到端", "手动", "blocked", "阻塞")):
            violations.append(f"{doc.relative_path}: section 8 must include real e2e/manual validation or blocked status")

        if not _body_has_any(section_9, ("不做", "范围外", "deferred")):
            violations.append(f"{doc.relative_path}: section 9 must lock non-goals and deferred handling")

        if not _body_has_any(doc.body, ("用户在聊天窗口明确确认", "用户明确确认")):
            violations.append(f"{doc.relative_path}: must preserve explicit human chat confirmation gate")
        for needle in ("RED 测试", "PM 契约门", "Codex", "Gemini", "baseline 回写", "PM 终审"):
            if needle not in doc.body and needle not in section_12:
                violations.append(f"{doc.relative_path}: missing review-flow gate term {needle}")

        for pattern in PM_BOUNDARY_PATTERNS:
            if pattern.search(doc.body):
                violations.append(f"{doc.relative_path}: contains PM-boundary implementation wording {pattern.pattern!r}")
        if "```" in doc.body:
            violations.append(f"{doc.relative_path}: requirements docs must not contain literal code fences")

        if "docs/graph-agent-gateway/" in doc.body or "docs/engine/" in doc.body:
            if not _body_has_any(doc.body, ("floating-draft", "pinned", "blocked", "阻塞", "条件放行")):
                violations.append(f"{doc.relative_path}: external engine/gateway contract status must be stated")

        if "apps/studio/frontend" in owns_text:
            for needle in ("FRONTEND_UI_SPEC.md", "components/ui"):
                if needle not in doc.body:
                    violations.append(f"{doc.relative_path}: UI WS must reference {needle}")
            if not _body_has_any(doc.body, ("Playwright", "浏览器")):
                violations.append(f"{doc.relative_path}: UI WS must require Playwright/browser click verification")
            if "窄" not in doc.body:
                violations.append(f"{doc.relative_path}: UI WS must require narrow-width validation")
            if not _body_has_any(doc.body, ("语义 token", "语义化 token", "语义化 CSS")):
                violations.append(f"{doc.relative_path}: UI WS must require semantic design tokens")

        if "apps/studio/backend" in owns_text and not _body_has_any(
            doc.body,
            ("重启 Studio App", "cargo tauri dev", "重启 Studio"),
        ):
            violations.append(f"{doc.relative_path}: backend WS must require Studio App restart after backend changes")

        if "apps/studio/tauri" in owns_text and not _body_has_any(doc.body, ("Tauri bridge", "Tauri", "原生路径")):
            violations.append(f"{doc.relative_path}: Tauri/native-fs WS must require Tauri bridge/native path validation")

    assert not violations, "Studio MVP1 requirements contract-gate violations:\n" + "\n".join(violations)


def test_studio_mvp1_ws_requirements_owns_files_match_impl_plan_partition() -> None:
    violations: list[str] = []
    for doc in _load_existing_expected_docs():
        ws_key = _ws_key(doc)
        if ws_key is None or ws_key not in EXPECTED_OWNS_BY_WS:
            violations.append(f"{doc.relative_path}: cannot derive canonical WS key from ws_id")
            continue

        owns_files = [item for item in doc.frontmatter.get("owns_files", []) or [] if isinstance(item, str)]
        expected_entries = EXPECTED_OWNS_BY_WS[ws_key]
        missing_expected = sorted(expected for expected in expected_entries if not _owns_contains(owns_files, expected))
        if missing_expected:
            violations.append(f"{doc.relative_path}: owns_files missing IMPL_PLAN key entries {missing_expected}")

        for owned_file in owns_files:
            if _is_allowed_test_or_spec_owned_file(owned_file):
                continue
            if any(_owns_contains([owned_file], expected) for expected in expected_entries):
                continue
            violations.append(f"{doc.relative_path}: owns_files includes non-IMPL_PLAN file {owned_file}")

    assert not violations, "Studio MVP1 requirements owns_files must match IMPL_PLAN partition:\n" + "\n".join(
        violations
    )


def test_studio_mvp1_ws_requirements_have_no_unexplained_owns_conflicts() -> None:
    docs = _load_existing_expected_docs()
    owners_by_file: dict[str, list[RequirementsDoc]] = defaultdict(list)
    for doc in docs:
        for owned_file in doc.frontmatter.get("owns_files", []) or []:
            if isinstance(owned_file, str):
                owners_by_file[owned_file].append(doc)

    violations: list[str] = []
    for owned_file, owners in sorted(owners_by_file.items()):
        if len(owners) < 2:
            continue
        missing_coordination = [
            owner.relative_path
            for owner in owners
            if owned_file not in _section(owner, 3)
            or not _body_has_any(_section(owner, 3), ("串行", "排队", "拆分", "释放", "worktree"))
            or "IMPL_PLAN.md" not in _section(owner, 3)
        ]
        if missing_coordination:
            owner_paths = [owner.relative_path for owner in owners]
            violations.append(
                f"{owned_file}: owned by {owner_paths} without full section 3 coordination in {missing_coordination}"
            )

    assert not violations, "Studio MVP1 requirements owns_files conflicts:\n" + "\n".join(violations)
