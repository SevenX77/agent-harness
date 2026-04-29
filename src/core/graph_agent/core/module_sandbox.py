"""ModuleSandbox — import SKILL-local objects with isolated module names."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


class ModuleSandbox:
    """Resolve dotted paths through explicit roots and a private cache.

    The sandbox searches explicit roots first, then falls back to normal
    importlib resolution. Loaded modules live only in this instance's private
    cache so SKILL-local module names do not leak into the process registry.
    """

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._search_paths = [Path(path).resolve() for path in (search_paths or [])]
        self._module_cache: dict[str, ModuleType] = {}
        self._cache: dict[str, type[Any]] = {}

    @property
    def search_paths(self) -> tuple[Path, ...]:
        """Search roots used for local module resolution."""

        return tuple(self._search_paths)

    def with_search_paths(self, search_paths: list[Path]) -> ModuleSandbox:
        """Return a sandbox copy with additional search roots appended."""

        return ModuleSandbox([*self._search_paths, *search_paths])

    def import_class(self, dotted_path: str) -> type[Any]:
        """Resolve ``pkg.module.ClassName`` to a class object."""

        cached = self._cache.get(dotted_path)
        if cached is not None:
            return cached

        if "." not in dotted_path:
            raise ImportError(
                f"ModuleSandbox: expected dotted class path, got {dotted_path!r}"
            )
        candidate = self.import_object(dotted_path)
        if not isinstance(candidate, type):
            raise ImportError(
                f"ModuleSandbox: {dotted_path!r} did not resolve to a class"
            )

        self._cache[dotted_path] = candidate
        return candidate

    def import_callable(self, dotted_path: str) -> Any:
        """Resolve ``pkg.module.callable_name`` to any callable object."""

        candidate = self.import_object(dotted_path)
        if not callable(candidate):
            raise ImportError(
                f"ModuleSandbox: {dotted_path!r} did not resolve to a callable"
            )
        return candidate

    def import_object(self, dotted_path: str) -> Any:
        """Resolve ``pkg.module.symbol`` without constraining symbol type."""

        module_path, separator, class_name = dotted_path.rpartition(".")
        if not separator or not module_path or not class_name:
            raise ImportError(
                f"ModuleSandbox: expected dotted object path, got {dotted_path!r}"
            )

        module = self._load_module(module_path)
        candidate = getattr(module, class_name, None)
        if candidate is None:
            raise ImportError(
                f"ModuleSandbox: module {module_path!r} does not define {class_name!r}"
            )
        return candidate

    def _load_module(self, module_path: str) -> ModuleType:
        cached = self._module_cache.get(module_path)
        if cached is not None:
            return cached

        module_file = self._find_module_file(module_path)
        if module_file is not None:
            module = self._load_from_file(module_path, module_file)
            self._module_cache[module_path] = module
            return module

        spec = importlib.util.find_spec(module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"ModuleSandbox: cannot find module {module_path!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module_cache[module_path] = module
        return module

    def _find_module_file(self, module_path: str) -> Path | None:
        relative = Path(*module_path.split("."))
        for root in self._search_paths:
            module_file = (root / relative.with_suffix(".py")).resolve()
            _ensure_under_root(module_file, root)
            if module_file.is_file():
                return module_file
            package_file = (root / relative / "__init__.py").resolve()
            _ensure_under_root(package_file, root)
            if package_file.is_file():
                return package_file
        return None

    def _load_from_file(self, module_path: str, module_file: Path) -> ModuleType:
        sandbox_name = self._sandbox_module_name(module_path, module_file)
        loader = importlib.machinery.SourceFileLoader(sandbox_name, str(module_file))
        spec = importlib.util.spec_from_loader(sandbox_name, loader)
        if spec is None or spec.loader is None:
            raise ImportError(f"ModuleSandbox: cannot create spec for {module_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _sandbox_module_name(module_path: str, module_file: Path) -> str:
        digest = hashlib.sha256(str(module_file.resolve()).encode("utf-8")).hexdigest()[:16]
        return f"_graph_agent_sandbox_{digest}_{module_path.replace('.', '_')}"


def _ensure_under_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ImportError(
            f"ModuleSandbox: resolved module path escapes search root: {path}"
        ) from exc


__all__ = ["ModuleSandbox"]
