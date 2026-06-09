"""V2.1 purity scanner for skill-local tools and actions."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PurityViolation:
    path: Path
    line: int
    api: str
    reason: str


_PATH_MUTATION_METHODS = {
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
_PATH_ACCESS_METHODS = {
    "exists",
    "glob",
    "group",
    "is_block_device",
    "is_char_device",
    "is_dir",
    "is_fifo",
    "is_file",
    "is_mount",
    "is_socket",
    "is_symlink",
    "iterdir",
    "lstat",
    "open",
    "owner",
    "read_bytes",
    "read_text",
    "readlink",
    "resolve",
    "rglob",
    "samefile",
    "stat",
}
_OS_MUTATION_METHODS = {
    "chmod",
    "chown",
    "link",
    "makedirs",
    "mkdir",
    "mknod",
    "remove",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "symlink",
    "truncate",
    "unlink",
    "utime",
}
_OS_ACCESS_METHODS = {
    "access",
    "fwalk",
    "listdir",
    "lstat",
    "open",
    "readlink",
    "scandir",
    "stat",
    "walk",
}
_OS_PATH_ACCESS_METHODS = {
    "exists",
    "getatime",
    "getctime",
    "getmtime",
    "getsize",
    "isdir",
    "isfile",
    "islink",
    "lexists",
    "realpath",
    "samefile",
    "sameopenfile",
    "samestat",
}
_GLOB_METHODS = {"glob", "iglob"}
_SYS_PATH_MUTATION_METHODS = {
    "append",
    "clear",
    "extend",
    "insert",
    "pop",
    "remove",
    "reverse",
    "sort",
}
_DYNAMIC_IMPORT_CALLS = {
    "__import__",
    "builtins.__import__",
    "importlib.import_module",
    "importlib.util.spec_from_file_location",
}
_FILE_OPEN_CALLS = {"open", "builtins.open", "io.open"}
_PATH_FACTORY_CALLS = {"pathlib.Path", "pathlib.Path.cwd", "pathlib.Path.home"}
_OS_METHODS = _OS_MUTATION_METHODS | _OS_ACCESS_METHODS
_SYS_PATH_MUTATION_CALLS = {f"sys.path.{method}" for method in _SYS_PATH_MUTATION_METHODS}
_OS_PATH_ACCESS_CALLS = {f"os.path.{method}" for method in _OS_PATH_ACCESS_METHODS}
_GLOB_CALLS = {f"glob.{method}" for method in _GLOB_METHODS}
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
    """Return purity hard-ban API violations found in a Python source file."""
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
    path_names = _collect_path_names(tree, aliases)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            violation = _violation_for_call(path, node, aliases, path_names)
            if violation is not None:
                violations.append(violation)
        elif isinstance(node, ast.Assign):
            violations.extend(_violations_for_targets(path, node.targets, aliases, node.lineno))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            violations.extend(_violations_for_targets(path, [node.target], aliases, node.lineno))
        elif isinstance(node, ast.Delete):
            violations.extend(_violations_for_targets(path, node.targets, aliases, node.lineno))
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


def _collect_path_names(tree: ast.AST, aliases: dict[str, str]) -> set[str]:
    path_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _is_pathlike_expr(node.value, aliases, path_names):
                path_names.update(_name_targets(node.targets))
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None and _is_pathlike_expr(node.value, aliases, path_names):
                path_names.update(_name_targets([node.target]))
    return path_names


def _name_targets(targets: Sequence[ast.AST]) -> set[str]:
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.update(_name_targets(list(target.elts)))
    return names


def _get_call_full_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    elif isinstance(node, ast.Attribute):
        value_name = _get_call_full_name(node.value, aliases)
        if value_name is not None:
            return f"{value_name}.{node.attr}"
    return None


def _target_full_name(
    node: ast.AST,
    aliases: dict[str, str],
    *,
    resolve_name_alias: bool = True,
) -> str | None:
    if isinstance(node, ast.Subscript):
        return _target_full_name(node.value, aliases)
    if isinstance(node, ast.Name):
        if resolve_name_alias:
            return aliases.get(node.id, node.id)
        return node.id
    if isinstance(node, ast.Attribute):
        value_name = _target_full_name(node.value, aliases)
        if value_name is not None:
            return f"{value_name}.{node.attr}"
    return None


def _violations_for_targets(
    path: Path,
    targets: Sequence[ast.AST],
    aliases: dict[str, str],
    lineno: int,
) -> list[PurityViolation]:
    violations: list[PurityViolation] = []
    for target in targets:
        resolve_name_alias = not isinstance(target, ast.Name)
        if _target_full_name(target, aliases, resolve_name_alias=resolve_name_alias) == "sys.path":
            violations.append(PurityViolation(path, lineno, "sys.path", "sys.path mutation is forbidden"))
    return violations


def _violation_for_call(
    path: Path,
    node: ast.Call,
    aliases: dict[str, str],
    path_names: set[str] | None = None,
) -> PurityViolation | None:
    full_name = _get_call_full_name(node.func, aliases)
    if full_name is not None:
        if full_name in {"run_skill", "graph_agent.run_skill", "graph_agent.core.runner.run_skill"}:
            return PurityViolation(path, node.lineno, "run_skill", "run_skill orchestration is forbidden")
        if full_name in _FILE_OPEN_CALLS:
            reason = _open_violation_reason(node) or "file system access open() is forbidden"
            return PurityViolation(path, node.lineno, "open", reason)
        if full_name in _SYS_PATH_MUTATION_CALLS:
            return PurityViolation(path, node.lineno, full_name, "sys.path mutation is forbidden")
        if full_name in _DYNAMIC_IMPORT_CALLS:
            return PurityViolation(path, node.lineno, full_name, f"dynamic import via {full_name} is forbidden")
        if full_name in _OS_PATH_ACCESS_CALLS:
            return PurityViolation(
                path,
                node.lineno,
                full_name,
                f"file system access via {full_name} is forbidden",
            )
        if full_name in _GLOB_CALLS:
            return PurityViolation(
                path,
                node.lineno,
                full_name,
                f"file system access via {full_name} is forbidden",
            )

    func = node.func
    if isinstance(func, ast.Name):
        return _violation_for_name_call(path, node, aliases)

    if isinstance(func, ast.Attribute):
        return _violation_for_attribute_call(path, node, aliases, path_names)
    return None


def _violation_for_name_call(
    path: Path,
    node: ast.Call,
    aliases: dict[str, str],
) -> PurityViolation | None:
    func = node.func
    assert isinstance(func, ast.Name)
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


def _violation_for_attribute_call(
    path: Path,
    node: ast.Call,
    aliases: dict[str, str],
    path_names: set[str] | None = None,
) -> PurityViolation | None:
    func = node.func
    assert isinstance(func, ast.Attribute)
    attr = func.attr
    base = _attribute_base_name(func.value)
    qualified_base = aliases.get(base or "", base or "")
    if attr in _PATH_MUTATION_METHODS and _is_pathlike_expr(func.value, aliases, path_names):
        return PurityViolation(path, node.lineno, attr, "path mutation APIs are forbidden")
    if attr in _PATH_ACCESS_METHODS and _is_pathlike_expr(func.value, aliases, path_names):
        return PurityViolation(
            path,
            node.lineno,
            attr,
            f"file system access via Path.{attr} is forbidden",
        )
    if qualified_base == "os" and attr in _OS_METHODS:
        if attr in _OS_ACCESS_METHODS:
            return PurityViolation(
                path,
                node.lineno,
                f"os.{attr}",
                f"file system access via os.{attr} is forbidden",
            )
        return PurityViolation(path, node.lineno, f"os.{attr}", "os filesystem mutation is forbidden")
    if qualified_base == "shutil" and attr in _SHUTIL_METHODS:
        return PurityViolation(
            path, node.lineno, f"shutil.{attr}", "shutil filesystem mutation is forbidden"
        )
    if qualified_base == "tempfile" and attr in _TEMPFILE_METHODS:
        return PurityViolation(
            path, node.lineno, f"tempfile.{attr}", "temporary files are local writes"
        )
    return None


def _is_pathlike_expr(
    node: ast.AST,
    aliases: dict[str, str],
    path_names: set[str] | None = None,
) -> bool:
    if isinstance(node, ast.Name):
        return path_names is not None and node.id in path_names
    if isinstance(node, ast.Call):
        full_name = _get_call_full_name(node.func, aliases)
        return full_name in _PATH_FACTORY_CALLS
    if isinstance(node, ast.BinOp):
        return _is_pathlike_expr(node.left, aliases, path_names) or _is_pathlike_expr(
            node.right, aliases, path_names
        )
    return False


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
