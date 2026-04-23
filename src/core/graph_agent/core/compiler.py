"""Static compilation checker for GraphAgent SKILL.md files.

Reads rule definitions from ``skills/compiler/data/rules.yaml`` (the single
source of truth) and performs static analysis without dynamic module imports.

Usage::

    from graph_agent.compiler import compile_skill
    result = compile_skill(Path("path/to/SKILL.md"))
    if not result.passed:
        for f in result.fatals:
            print(f"[{f.rule_id}] {f.location}: {f.message}")
"""

from __future__ import annotations

import ast
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .parser import (
    _NODE_PATTERN,
    _REF_PATTERN,
    _extract_tags,
    _normalise_phase_tags,
    _parse_frontmatter,
    _strip_frontmatter,
)
from .exceptions import SkillLoadError

logger = logging.getLogger(__name__)

# Rules YAML lives inside the compiler skill — single source of truth.
_RULES_PATH = Path(__file__).parent.parent / "skills" / "compiler" / "data" / "rules.yaml"

_PHASE_CONFIG_ALLOWED_KEYS = {
    "name",
    "tier",
    "tools",
    "validator",
    "max_iterations",
    "max_tool_calls",
    "retry_target",
    "max_retries",
    "max_nudges",
    "dead_end_threshold",
    "subagent_enabled",
    "subgraph",
    "context_bridge",
}

# These fields are set via XML tags, not phase_config YAML
_XML_ONLY_KEYS = {"user_prompt_template", "requires_llm"}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CompileIssue:
    """A single compilation diagnostic."""

    rule_id: str
    severity: str  # "FATAL" or "WARNING"
    location: str  # e.g. "SKILL.md:47" or "tools/compile.py"
    message: str


@dataclass
class CompileResult:
    """Aggregated result of compile_skill()."""

    issues: list[CompileIssue] = field(default_factory=list)

    @property
    def fatals(self) -> list[CompileIssue]:
        return [i for i in self.issues if i.severity == "FATAL"]

    @property
    def warnings(self) -> list[CompileIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def passed(self) -> bool:
        return len(self.fatals) == 0


# ---------------------------------------------------------------------------
# Rules metadata cache
# ---------------------------------------------------------------------------

_rules_cache: dict[str, dict[str, Any]] | None = None
_rules_cache_lock: threading.Lock = threading.Lock()


def _load_rules_metadata() -> dict[str, dict[str, Any]]:
    """Load rule definitions from rules.yaml. Returns {rule_id: {description, ...}}."""
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache

    with _rules_cache_lock:
        if _rules_cache is not None:
            return _rules_cache

        if not _RULES_PATH.exists():
            logger.warning("Rules file not found: %s", _RULES_PATH)
            _rules_cache = {}
            return _rules_cache

        raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8"))
        merged: dict[str, dict[str, Any]] = {}
        for severity_key in ("fatal", "warning"):
            section = raw.get(severity_key, {})
            for rule_id, meta in section.items():
                meta["_severity"] = "FATAL" if severity_key == "fatal" else "WARNING"
                merged[rule_id] = meta

        _rules_cache = merged
        return _rules_cache


def _issue(rule_id: str, location: str, message: str) -> CompileIssue:
    """Create a CompileIssue, deriving severity from rules metadata."""
    rules = _load_rules_metadata()
    meta = rules.get(rule_id, {})
    severity = meta.get("_severity", "WARNING")
    return CompileIssue(rule_id=rule_id, severity=severity, location=location, message=message)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parse_python_ast(py_path: Path) -> tuple[ast.Module | None, str | None]:
    """Parse a Python file into AST, returning a human-readable error if it fails."""
    try:
        return ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path)), None
    except SyntaxError as exc:
        line = exc.lineno or "?"
        return None, f"{exc.msg} (line {line})"


def _ast_function_names(py_path: Path) -> set[str]:
    """Return names of top-level public functions defined in a .py file (via AST)."""
    tree, _ = _parse_python_ast(py_path)
    if tree is None:
        return set()
    return {
        node.name
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def _ast_has_any_function(py_path: Path) -> bool:
    """Check if a .py file defines at least one function (public or private)."""
    tree, _ = _parse_python_ast(py_path)
    if tree is None:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.iter_child_nodes(tree)
    )


def _ast_function_info(py_path: Path) -> list[dict[str, Any]]:
    """Extract function metadata (name, docstring, return annotation, snake_case) via AST."""
    tree, _ = _parse_python_ast(py_path)
    if tree is None:
        return []
    results = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        # Docstring
        docstring = ast.get_docstring(node)
        # Return annotation
        ret_ann = None
        if node.returns:
            if isinstance(node.returns, ast.Name):
                ret_ann = node.returns.id
            elif isinstance(node.returns, ast.Constant):
                ret_ann = str(node.returns.value)
        results.append({
            "name": node.name,
            "docstring": docstring,
            "return_annotation": ret_ann,
            "lineno": node.lineno,
        })
    return results


_JSON_PARAM_NAME_RE = re.compile(
    r"(json|diff|fields|appearance|body_features|changes|entities|directives)",
    re.IGNORECASE,
)




def _ast_tool_signature_check(py_path: Path, func_name: str) -> tuple[bool, str]:
    """Check if a tool function signature is valid for code-only phases.
    
    Returns (is_valid, error_message).
    Valid signatures: 0 parameters, or 1 parameter named 'ctx' or 'context'.
    """
    tree, error = _parse_python_ast(py_path)
    if tree is None:
        return False, f"Cannot parse file: {error}"
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            args = node.args
            # Count all positional + keyword-only params (excluding *args, **kwargs)
            all_positional = list(args.posonlyargs) + list(args.args)
            args_count = len(all_positional)
            kwonlyargs = len(args.kwonlyargs)
            total_params = args_count + kwonlyargs

            if total_params == 0:
                return True, ""

            if total_params == 1 and args_count >= 1:
                # Check if the single argument is named 'ctx' or 'context'
                arg_name = all_positional[0].arg
                if arg_name in ("ctx", "context"):
                    return True, ""
                return False, f"Tool function '{func_name}' parameter must be named 'ctx' or 'context', got '{arg_name}'"
            elif total_params > 1:
                return False, f"Tool function '{func_name}' must accept 0 or 1 parameters, got {total_params}"
            
    return False, f"Function '{func_name}' not found in file"


def _ast_json_normalize_violations(py_path: Path) -> list[dict[str, Any]]:
    """Detect T006 violations: JSON-like str params used without _normalize_json_param()."""
    tree, _ = _parse_python_ast(py_path)
    if tree is None:
        return []

    def _is_str_annotation(node: ast.expr | None) -> bool:
        if node is None:
            return False
        if isinstance(node, ast.Name):
            return node.id == "str"
        if isinstance(node, ast.Constant):
            return node.value == "str"
        return False

    violations: list[dict[str, Any]] = []

    for fn in ast.iter_child_nodes(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name.startswith("_"):
            continue

        json_like_params: set[str] = set()
        for arg in fn.args.args:
            if arg.arg in {"context", "ctx"}:
                continue
            if _is_str_annotation(arg.annotation) and _JSON_PARAM_NAME_RE.search(arg.arg):
                json_like_params.add(arg.arg)
        if not json_like_params:
            continue

        normalized_params: set[str] = set()
        parsed_params: set[str] = set()
        dict_access_params: set[str] = set()

        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func

            if isinstance(callee, ast.Name) and callee.id == "_normalize_json_param":
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Name):
                    normalized_params.add(first.id)

            if isinstance(callee, ast.Name) and callee.id in {"_safe_parse", "_safe_parse_json"}:
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Name):
                    parsed_params.add(first.id)

            if (
                isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and isinstance(callee.value.id, str)
                and callee.value.id == "json"
                and callee.attr == "loads"
            ):
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Name):
                    parsed_params.add(first.id)

            if (
                isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and callee.attr in {"get", "keys", "items", "values"}
            ):
                dict_access_params.add(callee.value.id)

        for param in sorted(json_like_params):
            if param in normalized_params:
                continue
            if param in parsed_params or param in dict_access_params:
                violations.append({
                    "function": fn.name,
                    "param": param,
                    "lineno": fn.lineno,
                })

    return violations


# ---------------------------------------------------------------------------
# Placeholder extraction
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _extract_placeholders(text: str) -> set[str]:
    """Extract {key} placeholders from prompt text, filtering out JSON patterns."""
    candidates = set()
    for m in _PLACEHOLDER_RE.finditer(text):
        key = m.group(1)
        start = m.start()
        # Skip if preceded by " (likely JSON: {"key": ...})
        if start > 0 and text[start - 1] == '"':
            continue
        candidates.add(key)
    return candidates


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------


def _check_frontmatter(
    frontmatter: dict[str, Any],
    skill_dir: Path,
    result: CompileResult,
) -> None:
    """F001, F002, F005, F006."""
    loc = "SKILL.md:frontmatter"

    # F001: name kebab-case
    name = frontmatter.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        result.issues.append(_issue("F001", loc, "name 缺失或为空"))
    else:
        name = name.strip()
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
            result.issues.append(_issue("F001", loc, f"name '{name}' 不符合 kebab-case"))

    # F002: description
    desc = frontmatter.get("description")
    if not desc:
        result.issues.append(_issue("F002", loc, "description 缺失"))
    elif isinstance(desc, str) and len(desc) > 1024:
        result.issues.append(_issue("F002", loc, f"description 过长 ({len(desc)} > 1024)"))

    # F005: context_mapping syntax
    ctx_map = frontmatter.get("context_mapping", {})
    if isinstance(ctx_map, dict):
        for key, expr in ctx_map.items():
            if not isinstance(expr, str):
                continue
            expr = expr.strip()
            # Valid forms: "{path}", "$func(...)", "'literal'", plain string
            if expr.startswith("$") and "(" not in expr:
                result.issues.append(_issue(
                    "F005", loc,
                    f"context_mapping['{key}']: '$' 开头但缺少函数调用括号: {expr}",
                ))
            if expr.startswith("{") and not expr.endswith("}"):
                result.issues.append(_issue(
                    "F005", loc,
                    f"context_mapping['{key}']: 未闭合的花括号: {expr}",
                ))

    # F006: $func() syntax is deprecated — use setup phase + script/ tools instead
    if isinstance(ctx_map, dict):
        func_pattern = re.compile(r"\$(\w+)\(")
        func_names_used: set[str] = set()
        for expr in ctx_map.values():
            if isinstance(expr, str):
                func_names_used.update(func_pattern.findall(expr))

        for fname in sorted(func_names_used):
            result.issues.append(_issue(
                "F006", loc,
                f"context_mapping 中禁止使用 $func() 语法（${fname}() 已废弃）。"
                f"请改用 setup phase（requires_llm: false）+ script/ tools 模式："
                f"在 setup 节点中调用工具准备数据，写入 context，后续节点通过 {{{{key}}}} 读取。",
            ))


def _check_anthropic_compat(
    frontmatter: dict[str, Any],
    skill_dir: Path,
    content: str,
    result: CompileResult,
) -> None:
    """A001, A002, A003, A004, A005 — Anthropic platform compatibility."""
    loc = "SKILL.md:frontmatter"

    # A001: description must include WHAT + WHEN (trigger phrases)
    desc = frontmatter.get("description", "")
    if isinstance(desc, str) and desc.strip():
        trigger_patterns = [
            "当", "use when", "use for", "使用", "时使用",
            "trigger", "invoke", "activate",
        ]
        has_trigger = any(p in desc.lower() for p in trigger_patterns)
        if not has_trigger:
            result.issues.append(_issue(
                "A001", loc,
                "description 缺少触发条件（应包含'当...时使用'或'Use when'等触发词）",
            ))

    # A002: no XML angle brackets in frontmatter
    # Check the raw YAML frontmatter section (only < is problematic;
    # > is valid YAML folded-scalar syntax)
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm_raw = fm_match.group(1)
        if "<" in fm_raw:
            result.issues.append(_issue(
                "A002", loc,
                "frontmatter 中包含 XML 角括号 (<)，Anthropic 平台禁止",
            ))

    # A003: no README.md inside skill directory
    readme = skill_dir / "README.md"
    if readme.exists():
        result.issues.append(_issue(
            "A003", "README.md",
            "Skill 目录内不应包含 README.md（应放 SKILL.md 或 references/）",
        ))

    # A004: name must not contain reserved words
    name = frontmatter.get("name", "")
    if isinstance(name, str):
        name_lower = name.lower()
        if "claude" in name_lower or "anthropic" in name_lower:
            result.issues.append(_issue(
                "A004", loc,
                f"name '{name}' 包含保留词 (claude/anthropic)",
            ))

    # A005: SKILL.md size check (recommend < 5000 words)
    word_count = len(content.split())
    if word_count > 5000:
        result.issues.append(_issue(
            "A005", "SKILL.md",
            f"SKILL.md 过大 ({word_count} 词 > 5000)，建议将详细内容移到 references/",
        ))


def _check_phases(
    content: str,
    frontmatter: dict[str, Any],
    skill_dir: Path,
    result: CompileResult,
) -> None:
    """P003, P006, P007, P008, P009, P010, P002, P005, P012."""
    skill_type = frontmatter.get("type", "simple")
    ctx_map_keys = set((frontmatter.get("context_mapping") or {}).keys())

    # Collect nodes for graph-mode checks
    nodes_info: list[dict[str, Any]] = []

    if skill_type == "graph":
        # Task 5.3: accept <phase> as a synonym for <node> on the compiler
        # side too so W/F rules see a consistent document regardless of
        # which tag the author used.
        content = _normalise_phase_tags(content)
        for m in _NODE_PATTERN.finditer(content):
            node_id = m.group(1)
            depends_on = m.group(2)
            node_content = m.group(3).strip()
            # Resolve <ref> inline (read file content)
            resolved = _resolve_refs_safe(node_content, skill_dir)
            tags = _extract_tags(resolved)
            nodes_info.append({
                "id": node_id,
                "depends_on": depends_on,
                "tags": tags,
                "raw": resolved,
            })
    else:
        # Simple mode: extract tags from body
        body = _strip_frontmatter(content)
        tags = _extract_tags(body)
        if tags.get("phase_config"):
            nodes_info.append({"id": "main", "depends_on": None, "tags": tags, "raw": body})

    for node in nodes_info:
        phase_cfg_texts = node["tags"].get("phase_config", [])
        if not phase_cfg_texts:
            continue
        try:
            phase_cfg = yaml.safe_load(phase_cfg_texts[0])
        except yaml.YAMLError:
            continue
        if not isinstance(phase_cfg, dict):
            continue
        node["phase_cfg"] = phase_cfg
        phase_name = phase_cfg.get("name") or node["id"]
        node["phase_name"] = str(phase_name).strip() or node["id"]

    known_phase_names = {
        str(node["phase_name"])
        for node in nodes_info
        if isinstance(node.get("phase_name"), str)
    }

    # P008/P009: graph topology
    if skill_type == "graph":
        defined_node_ids = {n["id"] for n in nodes_info}
        dep_graph: dict[str, list[str]] = {n["id"]: [] for n in nodes_info}

        for n in nodes_info:
            if n["depends_on"]:
                deps = [d.strip() for d in n["depends_on"].split(",")]
                for dep in deps:
                    if dep not in defined_node_ids:
                        result.issues.append(_issue(
                            "P008", f"node:{n['id']}",
                            f"depends_on '{dep}' 指向未定义的 node",
                        ))
                    else:
                        dep_graph[n["id"]].append(dep)

        # P009: cycle detection (simple DFS)
        if not _is_dag(dep_graph):
            result.issues.append(_issue("P009", "SKILL.md", "节点依赖存在循环"))

    # Per-phase checks
    for node in nodes_info:
        node_id = node["id"]
        tags = node["tags"]
        loc = f"node:{node_id}"

        phase_cfg = node.get("phase_cfg")
        if not isinstance(phase_cfg, dict):
            continue

        unknown_keys = sorted(set(phase_cfg.keys()) - _PHASE_CONFIG_ALLOWED_KEYS - _XML_ONLY_KEYS)
        for key in unknown_keys:
            result.issues.append(_issue("P004", loc, f"未知 phase_config key: '{key}'"))
        xml_misplaced = sorted(set(phase_cfg.keys()) & _XML_ONLY_KEYS)
        for key in xml_misplaced:
            result.issues.append(_issue("P004", loc, f"'{key}' 应在 XML tag 中定义，而非 phase_config YAML"))
        # P003: tool paths
        tool_refs = phase_cfg.get("tools", [])
        for ref in tool_refs:
            if not isinstance(ref, str):
                continue
            parts = ref.rsplit(".", 1)
            if len(parts) != 2:
                result.issues.append(_issue("P003", loc, f"工具引用格式无效: '{ref}'"))
                continue
            module_path_str, func_name = parts
            py_file = skill_dir / module_path_str.replace(".", "/")
            py_file = py_file.with_suffix(".py")
            if not py_file.exists():
                result.issues.append(_issue("P003", loc, f"工具文件不存在: {py_file.name}"))
            else:
                _, parse_error = _parse_python_ast(py_file)
                if parse_error:
                    result.issues.append(_issue(
                        "P003",
                        loc,
                        f"工具文件无法解析: {py_file.name} ({parse_error})",
                    ))
                    continue
                funcs = _ast_function_names(py_file)
                if func_name not in funcs:
                    result.issues.append(_issue(
                        "P003", loc,
                        f"函数 '{func_name}' 未在 {py_file.name} 中定义",
                    ))

        # Validator reference check (same logic as tools)
        validator_ref = phase_cfg.get("validator")
        if validator_ref and isinstance(validator_ref, str):
            parts = validator_ref.rsplit(".", 1)
            if len(parts) != 2:
                result.issues.append(_issue("P003", loc, f"validator 引用格式无效: '{validator_ref}'"))
            else:
                module_path_str, func_name = parts
                py_file = skill_dir / module_path_str.replace(".", "/")
                py_file = py_file.with_suffix(".py")
                if not py_file.exists():
                    result.issues.append(_issue("P003", loc, f"validator 文件不存在: {py_file.name}"))
                else:
                    _, parse_error = _parse_python_ast(py_file)
                    if parse_error:
                        result.issues.append(_issue(
                            "P003",
                            loc,
                            f"validator 文件无法解析: {py_file.name} ({parse_error})",
                        ))
                    else:
                        funcs = _ast_function_names(py_file)
                        if func_name not in funcs:
                            result.issues.append(_issue(
                                "P003",
                                loc,
                                f"validator 函数 '{func_name}' 未在 {py_file.name} 中定义",
                            ))

        retry_target = phase_cfg.get("retry_target")
        if retry_target is not None:
            if not isinstance(retry_target, str) or not retry_target.strip():
                result.issues.append(_issue("P011", loc, "retry_target 必须是非空字符串"))
            elif retry_target not in known_phase_names:
                result.issues.append(_issue(
                    "P011",
                    loc,
                    f"retry_target '{retry_target}' 指向未定义 phase",
                ))

        # P006: placeholders defined
        sys_prompts = tags.get("system_prompt", [])
        usr_prompts = tags.get("user_prompt_builder", []) or tags.get("user_prompt", [])
        all_prompt_text = " ".join(sys_prompts + usr_prompts)
        placeholders = _extract_placeholders(all_prompt_text)
        missing = placeholders - ctx_map_keys
        for key in sorted(missing):
            result.issues.append(_issue("P006", loc, f"占位符 '{{{key}}}' 未在 context_mapping 中定义"))

        # P007: no inline JSON in system_prompt
        for sp in sys_prompts:
            if re.search(r'\{"', sp):
                result.issues.append(_issue("P007", loc, "system_prompt 中包含内联 JSON"))
                break

        # P002: tier known (WARNING)
        tier = phase_cfg.get("tier")
        if tier:
            known_tiers = _get_known_tiers()
            if known_tiers and tier not in known_tiers:
                result.issues.append(_issue("P002", loc, f"tier '{tier}' 不在 llm_roles.yaml 已知角色中"))

        # P005: both prompts (WARNING)
        requires_llm = bool(sys_prompts) and not phase_cfg.get("subgraph")
        if requires_llm and not usr_prompts:
            result.issues.append(_issue("P005", loc, "LLM 阶段缺少 <user_prompt>"))

        # P010: LLM phase must mention finish_task (WARNING)
        if requires_llm and "finish_task" not in all_prompt_text:
            result.issues.append(_issue("P010", loc, "LLM 阶段的 prompt 中未提及 finish_task（所有 LLM 阶段均自动启用认知循环）"))

        # P012: code-only phase tool signature validation (WARNING)
        # When phase has no system_prompt and no subgraph (code-only), check tool function AST
        is_code_only = not sys_prompts and not phase_cfg.get("subgraph")
        if is_code_only and tool_refs:
            for ref in tool_refs:
                if not isinstance(ref, str):
                    continue
                parts = ref.rsplit(".", 1)
                if len(parts) != 2:
                    continue
                module_path_str, func_name = parts
                py_file = skill_dir / module_path_str.replace(".", "/")
                py_file = py_file.with_suffix(".py")
                if py_file.exists():
                    is_valid, error_msg = _ast_tool_signature_check(py_file, func_name)
                    if not is_valid:
                        result.issues.append(_issue("P012", loc, f"code-only phase tool signature invalid: {error_msg}"))


def _check_structure(
    skill_dir: Path,
    body: str,
    result: CompileResult,
) -> None:
    """S001, S002, S003, S004."""
    # S001: no scripts in references/
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for f in refs_dir.iterdir():
            if f.suffix in (".py", ".sh"):
                result.issues.append(_issue("S001", f"references/{f.name}", "references/ 中存在可执行脚本"))

    # S002: script/ files must have callables (also check legacy tools/)
    for script_dir_name in ("script", "tools"):
        scripts_dir = skill_dir / script_dir_name
        if scripts_dir.is_dir():
            for f in scripts_dir.glob("*.py"):
                if f.name.startswith("_"):
                    continue
                if not _ast_has_any_function(f):
                    result.issues.append(_issue("S002", f"{script_dir_name}/{f.name}", "工具文件中无可调用函数"))

    # S003: no inline rule tables in SKILL.md
    rule_id_pattern = re.compile(r"\|\s*([FPST]\d{3})\s*\|")
    found_ids = set(rule_id_pattern.findall(body))
    if len(found_ids) >= 3:
        result.issues.append(_issue("S003", "SKILL.md", f"内联了 {len(found_ids)} 条规则定义，应引用 data/rules.yaml"))

    # S004: helpers.py is deprecated
    for helpers_path in [
        skill_dir / "helpers.py",
        skill_dir / "tools" / "helpers.py",
        skill_dir / "script" / "helpers.py",
    ]:
        if helpers_path.exists():
            rel = helpers_path.relative_to(skill_dir)
            result.issues.append(_issue(
                "S004", str(rel),
                "helpers.py 已废弃。请将数据变换逻辑迁移到 setup phase 的 script/ tools 中，"
                "通过 requires_llm: false 节点写入 context，后续节点用 {key} 读取。",
            ))


def _check_tools(
    skill_dir: Path,
    result: CompileResult,
) -> None:
    """T001, T002, T003, T005, T006 — checks both script/ and legacy tools/ directories."""
    for script_dir_name in ("script", "tools"):
        tools_dir = skill_dir / script_dir_name
        if not tools_dir.is_dir():
            continue

        for py_file in tools_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            funcs = _ast_function_info(py_file)
            for func in funcs:
                loc = f"{script_dir_name}/{py_file.name}:{func['lineno']}"
                # T001: return type str
                if func["return_annotation"] and func["return_annotation"] != "str":
                    result.issues.append(_issue("T001", loc, f"函数 '{func['name']}' 返回类型应为 str"))
                # T002: has docstring
                if not func["docstring"]:
                    result.issues.append(_issue("T002", loc, f"函数 '{func['name']}' 缺少 docstring"))
                # T003: docstring first para non-empty
                elif not func["docstring"].strip().split("\n")[0].strip():
                    result.issues.append(_issue("T003", loc, f"函数 '{func['name']}' docstring 第一段为空"))
                # T005: snake_case
                if not re.match(r"^[a-z][a-z0-9_]*$", func["name"]):
                    result.issues.append(_issue("T005", loc, f"函数名 '{func['name']}' 不符合 snake_case"))

            for violation in _ast_json_normalize_violations(py_file):
                loc = f"{script_dir_name}/{py_file.name}:{violation['lineno']}"
                result.issues.append(_issue(
                    "T006",
                    loc,
                    (
                        f"函数 '{violation['function']}' 的 JSON 参数 '{violation['param']}' "
                        "在入口处未调用 _normalize_json_param"
                    ),
                ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_refs_safe(content: str, base_dir: Path) -> str:
    """Resolve <ref> tags, returning original content on error."""
    def replacer(m: re.Match[str]) -> str:
        ref_path = base_dir / m.group(1)
        if not ref_path.exists():
            return m.group(0)
        ref_content = ref_path.read_text(encoding="utf-8")
        return _resolve_refs_safe(ref_content, ref_path.parent)
    return _REF_PATTERN.sub(replacer, content)


def _is_dag(graph: dict[str, list[str]]) -> bool:
    """Check if a dependency graph is a DAG (no cycles)."""
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str) -> bool:
        if node in in_stack:
            return False  # cycle
        if node in visited:
            return True
        visited.add(node)
        in_stack.add(node)
        for dep in graph.get(node, []):
            if not dfs(dep):
                return False
        in_stack.discard(node)
        return True

    return all(dfs(n) for n in graph if n not in visited)


def _get_known_tiers() -> set[str]:
    """Load known tier names from llm_roles.yaml (returns empty set on failure)."""
    try:
        from ..config.llm_config import get_role_config

        return set(get_role_config().roles.keys())
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_skill(skill_path: str | Path) -> CompileResult:
    """Run static compilation checks on a SKILL.md file.

    Reads rule definitions from ``skills/compiler/data/rules.yaml`` and
    checks the target SKILL.md against all FATAL and WARNING rules.

    Args:
        skill_path: Path to the SKILL.md file to check.

    Returns:
        CompileResult with all detected issues.
    """
    skill_path = Path(skill_path)
    result = CompileResult()

    if not skill_path.exists():
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location=str(skill_path),
            message="SKILL.md 文件不存在",
        ))
        return result

    content = skill_path.read_text(encoding="utf-8")
    skill_dir = skill_path.parent
    if not content.strip():
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location=str(skill_path),
            message="SKILL.md 文件为空",
        ))
        return result

    # Parse frontmatter
    try:
        frontmatter = _parse_frontmatter(content)
    except SkillLoadError as e:
        result.issues.append(CompileIssue(
            rule_id="INTERNAL",
            severity="FATAL",
            location="SKILL.md:frontmatter",
            message=str(e),
        ))
        return result

    body = _strip_frontmatter(content)

    # Run all checks
    _check_frontmatter(frontmatter, skill_dir, result)
    _check_anthropic_compat(frontmatter, skill_dir, content, result)
    _check_phases(content, frontmatter, skill_dir, result)
    _check_structure(skill_dir, body, result)
    _check_tools(skill_dir, result)

    logger.info(
        "Compiled '%s': %d FATAL, %d WARNING",
        skill_path.name,
        len(result.fatals),
        len(result.warnings),
    )
    return result
