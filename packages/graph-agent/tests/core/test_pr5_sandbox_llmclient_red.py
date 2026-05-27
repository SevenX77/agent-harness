from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from graph_agent.config.llm_config import ProviderDef
from graph_agent.core.module_sandbox import ModuleSandbox
from graph_agent.models import llm_client_manager as manager_module
from graph_agent.models.llm_client_manager import LLMClientManager


def _provider(
    provider_code: str = "PR5_OPENAI",
    provider_type: str = "openai_compatible",
) -> ProviderDef:
    return ProviderDef(
        code=provider_code,
        name=f"Provider {provider_code}",
        type=provider_type,
        api_key_env="PR5_TEST_API_KEY",
        api_key_env_fallback="",
        base_url="https://provider.example/v1",
        llm_base_url="https://llm.provider.example/v1",
        timeout=12,
        trust_env=False,
    )


class _ControlledClientCache(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__()
        self.first_get_entered = threading.Event()
        self.second_get_entered = threading.Event()
        self.release_first_get = threading.Event()
        self.get_count = 0
        self._get_lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._get_lock:
            self.get_count += 1
            call_index = self.get_count
        if call_index == 1:
            self.first_get_entered.set()
            assert self.release_first_get.wait(2), "test did not release first cache get"
            return default
        if call_index == 2:
            self.second_get_entered.set()
            return super().get(key, default)
        return super().get(key, default)


class _FakeSDKClient:
    created: list[_FakeSDKClient] = []

    def __init__(self, **_: Any) -> None:
        self.closed = False
        self.__class__.created.append(self)

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    LLMClientManager._clients.clear()
    LLMClientManager._usage_stats.clear()
    LLMClientManager._provider_down_cache.clear()
    _FakeSDKClient.created.clear()
    monkeypatch.setenv("PR5_TEST_API_KEY", "secret")


def _run_two_client_getters(
    target: Any,
    cache: _ControlledClientCache,
    monkeypatch: pytest.MonkeyPatch,
) -> list[Any]:
    monkeypatch.setattr(LLMClientManager, "_clients", cache)
    monkeypatch.setattr(manager_module, "OpenAI", _FakeSDKClient)
    monkeypatch.setattr(manager_module, "Anthropic", _FakeSDKClient)

    results: list[Any] = []
    errors: list[BaseException] = []
    results_lock = threading.Lock()

    def worker() -> None:
        try:
            client = target()
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
            return
        with results_lock:
            results.append(client)

    first = threading.Thread(target=worker)
    first.start()
    assert cache.first_get_entered.wait(2), "first thread did not enter cache get"

    second = threading.Thread(target=worker)
    second.start()
    cache.second_get_entered.wait(0.5)
    cache.release_first_get.set()

    first.join(2)
    second.join(2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors
    return results


def test_module_sandbox_removes_sys_modules_for_importlib_resolved_spec_name_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_dir = tmp_path / "importable"
    module_dir.mkdir()
    module_name = "pr5_importlib_schema"
    (module_dir / f"{module_name}.py").write_text(
        "class OutputSchema:\n    value = 'importlib-path'\n",
        encoding="utf-8",
    )
    sys.modules.pop(module_name, None)
    monkeypatch.syspath_prepend(str(module_dir))

    cls = ModuleSandbox().import_class(f"{module_name}.OutputSchema")

    assert cls.value == "importlib-path"
    assert module_name not in sys.modules


def test_module_sandbox_preserves_preexisting_importlib_resolved_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_dir = tmp_path / "importable_preexisting"
    module_dir.mkdir()
    module_name = "pr5_preexisting_schema"
    (module_dir / f"{module_name}.py").write_text(
        "class OutputSchema:\n    value = 'preexisting-path'\n",
        encoding="utf-8",
    )
    sys.modules.pop(module_name, None)
    monkeypatch.syspath_prepend(str(module_dir))
    importlib.invalidate_caches()
    original_module = importlib.import_module(module_name)

    cls = ModuleSandbox().import_class(f"{module_name}.OutputSchema")

    assert cls.value == "preexisting-path"
    assert sys.modules[module_name] is original_module


def test_openai_client_cache_initialization_is_thread_safe_with_deterministic_interleave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _ControlledClientCache()
    provider_def = _provider()

    results = _run_two_client_getters(
        lambda: LLMClientManager._get_openai_client("PR5_OPENAI", provider_def),
        cache,
        monkeypatch,
    )

    assert len(results) == 2
    assert len(_FakeSDKClient.created) == 1
    assert results[0] is results[1]


def test_anthropic_client_cache_initialization_is_thread_safe_with_deterministic_interleave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _ControlledClientCache()
    provider_def = _provider("PR5_ANTHROPIC", "anthropic_compatible")

    results = _run_two_client_getters(
        lambda: LLMClientManager._get_anthropic_client("PR5_ANTHROPIC", provider_def),
        cache,
        monkeypatch,
    )

    assert len(results) == 2
    assert len(_FakeSDKClient.created) == 1
    assert results[0] is results[1]


def test_llm_client_manager_close_all_closes_cached_clients() -> None:
    first = _FakeSDKClient()
    second = _FakeSDKClient()
    LLMClientManager._clients["openai:one"] = first
    LLMClientManager._clients["anthropic:two"] = second

    LLMClientManager.close_all()

    assert first.closed
    assert second.closed
    assert LLMClientManager._clients == {}


def _sandbox_key(root: Path, module_name: str) -> str:
    module_file = root / f"{module_name}.py"
    return ModuleSandbox._sandbox_module_name(module_name, module_file)


def test_module_sandbox_removes_public_and_sandbox_sys_modules_for_same_named_modules(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "skill_a"
    second_root = tmp_path / "skill_b"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "schemas.py").write_text(
        "class OutputSchema:\n    value = 'a'\n",
        encoding="utf-8",
    )
    (second_root / "schemas.py").write_text(
        "class OutputSchema:\n    value = 'b'\n",
        encoding="utf-8",
    )
    first_key = _sandbox_key(first_root, "schemas")
    second_key = _sandbox_key(second_root, "schemas")
    for key in ("schemas", first_key, second_key):
        sys.modules.pop(key, None)

    first_cls = ModuleSandbox(search_paths=[first_root]).import_class("schemas.OutputSchema")
    second_cls = ModuleSandbox(search_paths=[second_root]).import_class("schemas.OutputSchema")

    assert first_cls.value == "a"
    assert second_cls.value == "b"
    assert "schemas" not in sys.modules
    assert first_key not in sys.modules
    assert second_key not in sys.modules


def test_module_sandbox_forward_ref_model_validate_survives_sys_modules_cleanup(
    tmp_path: Path,
) -> None:
    module_file = tmp_path / "fr_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from typing import Literal\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class FRSchema(BaseModel):\n"
        '    kind: Literal["A", "B"]\n'
        "    value: int\n",
        encoding="utf-8",
    )
    sandbox_key = _sandbox_key(tmp_path, "fr_schemas")
    sys.modules.pop(sandbox_key, None)

    schema_cls = ModuleSandbox(search_paths=[tmp_path]).import_class("fr_schemas.FRSchema")
    instance = schema_cls.model_validate({"kind": "A", "value": 3})

    assert instance.model_dump() == {"kind": "A", "value": 3}
    assert sandbox_key not in sys.modules


def test_module_sandbox_cleans_sys_modules_when_model_rebuild_fails(tmp_path: Path) -> None:
    module_file = tmp_path / "broken_schemas.py"
    module_file.write_text(
        "from __future__ import annotations\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Broken(BaseModel):\n"
        "    field: NameThatDoesNotExist\n",
        encoding="utf-8",
    )
    sandbox_key = _sandbox_key(tmp_path, "broken_schemas")
    sys.modules.pop(sandbox_key, None)

    with pytest.raises(NameError):
        ModuleSandbox(search_paths=[tmp_path]).import_class("broken_schemas.Broken")

    assert sandbox_key not in sys.modules
