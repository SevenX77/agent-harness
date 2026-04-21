"""Compiler tools for GraphAgent Skill compilation and auto-fix.

Provides tool functions that wrap the core ``compiler.py`` engine for use
within GraphAgent phases. Each function follows the tool_spec.md conventions:
returns ``str``, has ``ctx: dict`` auto-injected, full docstring, typed args.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compile_skill(ctx: dict) -> str:
    """Run static compilation checks on the target Skill and report all FATAL/WARNING issues.

    Call this tool first to identify problems before attempting fixes.
    The result is stored in ctx for read_compilation_errors to retrieve.

    Returns:
        A formatted compilation report listing all issues found, or "PASS" if clean.
    """
    from ....core.compiler import compile_skill as _compile

    skill_path = ctx.get("skill_path", "")
    if not skill_path:
        return "ERROR: skill_path not set in context"

    result = _compile(Path(skill_path))

    # Store in ctx for read_compilation_errors
    ctx["_compile_result"] = {
        "passed": result.passed,
        "fatals": [
            {"rule_id": i.rule_id, "location": i.location, "message": i.message}
            for i in result.fatals
        ],
        "warnings": [
            {"rule_id": i.rule_id, "location": i.location, "message": i.message}
            for i in result.warnings
        ],
    }

    if result.passed and not result.warnings:
        return "PASS: 无 FATAL 或 WARNING 错误"

    lines = []
    if result.fatals:
        lines.append(f"FATAL ({len(result.fatals)}):")
        for i in result.fatals:
            lines.append(f"  [{i.rule_id}] {i.location}: {i.message}")
    if result.warnings:
        lines.append(f"WARNING ({len(result.warnings)}):")
        for i in result.warnings:
            lines.append(f"  [{i.rule_id}] {i.location}: {i.message}")

    return "\n".join(lines)


def read_skill_file(file_path: str, ctx: dict) -> str:
    """Read a file from the target Skill directory.

    Use this to inspect SKILL.md, config files, or any other file in the
    target Skill's directory tree before making modifications.

    Args:
        file_path: Relative path within the Skill directory (e.g. "SKILL.md", "data/rules.yaml").

    Returns:
        The file content as a string, or an error message if the file cannot be read.
    """
    skill_path = ctx.get("skill_path", "")
    if not skill_path:
        return "ERROR: skill_path not set in context"

    base_dir = Path(skill_path).parent
    target = (base_dir / file_path).resolve()

    # Security: must be within skill directory
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return f"ERROR: 路径 '{file_path}' 超出 Skill 目录范围"

    if not target.exists():
        return f"ERROR: 文件不存在: {file_path}"

    return target.read_text(encoding="utf-8")


def write_skill_file(file_path: str, content: str, ctx: dict) -> str:
    """Write or overwrite a file in the target Skill directory.

    Use this to apply fixes to SKILL.md or create new files (e.g. data/rules.yaml).
    Parent directories are created automatically if they don't exist.

    Args:
        file_path: Relative path within the Skill directory (e.g. "SKILL.md").
        content: The full file content to write.

    Returns:
        Confirmation message with the file path written.
    """
    skill_path = ctx.get("skill_path", "")
    if not skill_path:
        return "ERROR: skill_path not set in context"

    base_dir = Path(skill_path).parent
    target = (base_dir / file_path).resolve()

    # Security: must be within skill directory
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return f"ERROR: 路径 '{file_path}' 超出 Skill 目录范围"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Wrote %d bytes to %s", len(content), target)
    return f"OK: 已写入 {file_path} ({len(content)} bytes)"


def read_compilation_errors(ctx: dict) -> str:
    """Retrieve the compilation errors from the most recent compile_skill run.

    Call compile_skill first, then use this tool to get a structured error list
    for planning your fix strategy.

    Returns:
        JSON-formatted compilation result, or an error if compile_skill hasn't been called.
    """
    result = ctx.get("_compile_result")
    if result is None:
        return "ERROR: 未找到编译结果。请先调用 compile_skill。"
    return json.dumps(result, ensure_ascii=False, indent=2)


def read_reference(reference_name: str, ctx: dict) -> str:
    """Read a reference document from the Compiler Skill's own references/ directory.

    Use this to look up detailed rule specifications, fix strategies, templates,
    or coding standards when you need guidance on how to fix specific issues.

    Args:
        reference_name: Filename in references/ (e.g. "rules_spec.md", "skill_template.md", "tool_spec.md").

    Returns:
        The reference document content, or an error if not found.
    """
    del ctx

    # References are relative to THIS skill's directory, not the target skill
    compiler_skill_dir = Path(__file__).parent.parent
    refs_dir = compiler_skill_dir / "references"
    target = (refs_dir / reference_name).resolve()

    # Security: only allow .md and .yaml from references/
    try:
        target.relative_to(refs_dir.resolve())
    except ValueError:
        return f"ERROR: 路径 '{reference_name}' 超出 references/ 目录范围"

    if target.suffix not in (".md", ".yaml", ".yml"):
        return f"ERROR: 只允许读取 .md/.yaml 文件，不允许: {target.suffix}"

    if not target.exists():
        available = [f.name for f in refs_dir.iterdir() if f.is_file()] if refs_dir.is_dir() else []
        return f"ERROR: 文件不存在: {reference_name}。可用文件: {', '.join(available)}"

    return target.read_text(encoding="utf-8")
