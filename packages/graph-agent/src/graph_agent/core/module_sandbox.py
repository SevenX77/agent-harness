"""ModuleSandbox — import SKILL-local objects with isolated module names."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
            raise ImportError(f"ModuleSandbox: expected dotted class path, got {dotted_path!r}")
        candidate = self.import_object(dotted_path)
        if not isinstance(candidate, type):
            raise ImportError(f"ModuleSandbox: {dotted_path!r} did not resolve to a class")

        self._cache[dotted_path] = candidate
        return candidate

    def import_callable(self, dotted_path: str) -> Any:
        """Resolve ``pkg.module.callable_name`` to any callable object."""

        candidate = self.import_object(dotted_path)
        if not callable(candidate):
            raise ImportError(f"ModuleSandbox: {dotted_path!r} did not resolve to a callable")
        return candidate

    def import_object(self, dotted_path: str) -> Any:
        """Resolve ``pkg.module.symbol`` without constraining symbol type."""

        module_path, separator, class_name = dotted_path.rpartition(".")
        if not separator or not module_path or not class_name:
            raise ImportError(f"ModuleSandbox: expected dotted object path, got {dotted_path!r}")

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
        # Phase 3 M7 follow-up (PHASE3_DESIGN.md v4 §3.5 step 3): register
        # before exec_module so forward-ref resolution during class
        # construction can find the module via ``sys.modules``.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _rebuild_pydantic_models(module, spec.name)
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
        # Phase 3 M7 follow-up (PHASE3_DESIGN.md v4 §3.5 step 3): register
        # the sandbox module in ``sys.modules`` BEFORE ``exec_module`` so
        # any class declared with ``from __future__ import annotations``
        # (which keeps annotations as forward-ref strings) can later
        # resolve those strings via ``typing.get_type_hints`` /
        # Pydantic's ``model_rebuild``. Without this registration
        # ``Pydantic.BaseModel.model_validate`` raises
        # ``PydanticUserError: <Class> is not fully defined`` on any
        # SKILL-local class that uses ``Literal[...]`` or any other
        # forward-ref annotation. The ``sys.modules`` write + the
        # post-exec ``model_rebuild`` loop must stay atomic per design
        # §3.5 / §3.8 so the rebuild surfaces errors at load time
        # instead of at runtime.
        sys.modules[sandbox_name] = module
        spec.loader.exec_module(module)
        _rebuild_pydantic_models(module, sandbox_name)
        return module

    @staticmethod
    def _sandbox_module_name(module_path: str, module_file: Path) -> str:
        digest = hashlib.sha256(str(module_file.resolve()).encode("utf-8")).hexdigest()[:16]
        return f"_graph_agent_sandbox_{digest}_{module_path.replace('.', '_')}"


def _rebuild_pydantic_models(module: ModuleType, module_name: str) -> None:
    """Phase 3 M7 follow-up (PHASE3_DESIGN.md v4 §3.5 step 3, §3.8).

    Iterate every Pydantic ``BaseModel`` subclass defined in ``module``
    and call ``model_rebuild()`` on it. With ``from __future__ import
    annotations`` (and Python 3.10+'s implicit annotation deferral),
    Pydantic stores field annotations as forward-ref strings until a
    consumer calls ``model_validate`` or ``model_rebuild``. Eagerly
    rebuilding here makes those forward-refs resolve **at load time**
    so any ``ImportError`` / ``TypeError`` surfaces fail-loud right
    next to the offending SKILL, instead of silently lurking until
    ``CognitiveFlowMiddleware._validate_finish_args`` calls
    ``model_validate`` mid-run and crashes with the cryptic
    ``PydanticUserError: <Class> is not fully defined``.

    The companion ``sys.modules[module_name] = module`` registration
    happens in the caller before ``exec_module``; both writes must
    stay atomic per design §3.8 so a partial loader path never leaves
    a class that resolves *some* refs but not others.
    """
    for attr_name, obj in vars(module).items():
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            try:
                obj.model_rebuild()
            except Exception as exc:
                logger.error(
                    "ModuleSandbox: model_rebuild failed for %s.%s (module=%s) reason=%s",
                    module_name,
                    attr_name,
                    obj.__name__,
                    type(exc).__name__,
                )
                raise


def _ensure_under_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ImportError(
            f"ModuleSandbox: resolved module path escapes search root: {path}"
        ) from exc


__all__ = ["ModuleSandbox"]
