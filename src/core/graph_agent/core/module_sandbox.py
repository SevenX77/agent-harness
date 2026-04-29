"""ModuleSandbox — import SKILL-local classes without global module registration."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


class ModuleSandbox:
    """Resolve dotted class paths without writing to ``sys.modules``.

    T5 will wire this into loader/build_graph_nodes. For now this skeleton
    provides the import-class primitive and a private cache.
    """

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._search_paths = [Path(path) for path in (search_paths or [])]
        self._cache: dict[str, type[Any]] = {}

    def import_class(self, dotted_path: str) -> type[Any]:
        """Resolve ``pkg.module.ClassName`` to a class object."""

        cached = self._cache.get(dotted_path)
        if cached is not None:
            return cached

        module_path, separator, class_name = dotted_path.rpartition(".")
        if not separator or not module_path or not class_name:
            raise ImportError(
                f"ModuleSandbox: expected dotted class path, got {dotted_path!r}"
            )

        module = self._load_module(module_path)
        candidate = getattr(module, class_name, None)
        if not isinstance(candidate, type):
            raise ImportError(
                f"ModuleSandbox: {dotted_path!r} did not resolve to a class"
            )

        self._cache[dotted_path] = candidate
        return candidate

    def _load_module(self, module_path: str) -> ModuleType:
        module_file = self._find_module_file(module_path)
        if module_file is not None:
            return self._load_from_file(module_path, module_file)

        spec = importlib.util.find_spec(module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"ModuleSandbox: cannot find module {module_path!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _find_module_file(self, module_path: str) -> Path | None:
        relative = Path(*module_path.split("."))
        for root in self._search_paths:
            module_file = root / relative.with_suffix(".py")
            if module_file.is_file():
                return module_file
            package_file = root / relative / "__init__.py"
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


__all__ = ["ModuleSandbox"]
