"""V2.1 purity scanner for skill-local tools and actions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PurityViolation:
    path: Path
    line: int
    api: str
    reason: str


_PATH_METHODS = {
    "write_text",
    "write_bytes",
    "touch",
    "mkdir",
    "rename",
    "unlink",
    "symlink_to",
    "hardlink_to",
    "replace",
    "rmdir",
    "chmod",
}
_OS_METHODS = {"remove", "rename", "replace", "makedirs", "mkdir", "rmdir", "unlink", "chmod"}
_SHUTIL_METHODS = {"copy", "copy2", "copyfile", "copytree", "move", "rmtree"}
_TEMPFILE_METHODS = {
    "NamedTemporaryFile",
    "TemporaryFile",
    "mkstemp",
    "mkdtemp",
    "TemporaryDirectory",
}
_WRITE_MODE_CHARS = set("wax+")
_READ_MODES = {"r", "rb", "rt"}


def scan_python_purity(path: Path) -> list[PurityViolation]:
    """Return local-write API violations found in a Python source file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            PurityViolation(
                path=path,
                line=exc.lineno or 1,
                api="python",
                reason=f"invalid Python syntax: {exc.msg}",
            )
        ]

    violations: list[PurityViolation] = []
    aliases = _collect_import_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        violation = _violation_for_call(path, node, aliases)
        if violation is not None:
            violations.append(violation)
    return violations


def scan_tool_imports_context(path: Path) -> list[PurityViolation]:
    """Return context-facade imports that are forbidden in Tool files."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            PurityViolation(path, exc.lineno or 1, "python", f"invalid Python syntax: {exc.msg}")
        ]
    violations: list[PurityViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "graph_agent.cognitive.context_facade":
                    form = "form 3" if alias.asname else "form 2"
                    violations.append(
                        PurityViolation(
                            path=path,
                            line=node.lineno,
                            api="graph_agent.cognitive.context_facade",
                            reason=f"Tools must not import the Action Context facade ({form})",
                        )
                    )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "graph_agent.cognitive.context_facade"
        ):
            violations.append(
                PurityViolation(
                    path=path,
                    line=node.lineno,
                    api="graph_agent.cognitive.context_facade",
                    reason="Tools must not import the Action Context facade (form 1)",
                )
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "graph_agent.cognitive":
            for alias in node.names:
                if alias.name == "context_facade":
                    violations.append(
                        PurityViolation(
                            path=path,
                            line=node.lineno,
                            api="graph_agent.cognitive.context_facade",
                            reason="Tools must not import the Action Context facade (form 4)",
                        )
                    )
    return violations


def _collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                aliases[alias.asname or root] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _violation_for_call(
    path: Path,
    node: ast.Call,
    aliases: dict[str, str],
) -> PurityViolation | None:
    func = node.func
    if isinstance(func, ast.Name):
        name = func.id
        qualified = aliases.get(name, name)
        if name == "open" or qualified == "builtins.open":
            reason = _open_violation_reason(node)
            if reason is not None:
                return PurityViolation(path, node.lineno, "open", reason)
        if qualified.startswith("tempfile.") and qualified.rsplit(".", 1)[-1] in _TEMPFILE_METHODS:
            return PurityViolation(path, node.lineno, qualified, "temporary files are local writes")
        if name in _TEMPFILE_METHODS:
            return PurityViolation(path, node.lineno, name, "temporary files are local writes")
        return None

    if isinstance(func, ast.Attribute):
        attr = func.attr
        base = _attribute_base_name(func.value)
        qualified_base = aliases.get(base or "", base or "")
        if attr in _PATH_METHODS:
            return PurityViolation(path, node.lineno, attr, "path mutation APIs are forbidden")
        if qualified_base == "os" and attr in _OS_METHODS:
            return PurityViolation(
                path, node.lineno, f"os.{attr}", "os filesystem mutation is forbidden"
            )
        if qualified_base == "shutil" and attr in _SHUTIL_METHODS:
            return PurityViolation(
                path, node.lineno, f"shutil.{attr}", "shutil filesystem mutation is forbidden"
            )
        if qualified_base == "tempfile" and attr in _TEMPFILE_METHODS:
            return PurityViolation(
                path, node.lineno, f"tempfile.{attr}", "temporary files are local writes"
            )
    return None


def _open_violation_reason(node: ast.Call) -> str | None:
    mode_node: ast.AST | None = None
    if len(node.args) >= 2:
        mode_node = node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode_node = keyword.value
            break
    if mode_node is None:
        return None
    if not isinstance(mode_node, ast.Constant) or not isinstance(mode_node.value, str):
        return "open() mode must be a literal read-only mode"
    mode = mode_node.value
    if mode not in _READ_MODES or any(ch in mode for ch in _WRITE_MODE_CHARS):
        return f"open() mode {mode!r} may write local files"
    return None


def _attribute_base_name(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


__all__ = ["PurityViolation", "scan_python_purity", "scan_tool_imports_context"]
