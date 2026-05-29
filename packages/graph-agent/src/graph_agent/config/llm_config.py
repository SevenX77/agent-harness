"""
LLM Role Config — YAML 配置加载器

职责：
  1. 加载 config/llm_roles.yaml → 结构化 dataclass
  2. 代号交叉验证（role→model→provider 链路完整性）
  3. 热加载（mtime 检查，变化时重新加载）
  4. 错误报告（加载失败 fallback 到上次有效配置）

用法：
  from graph_agent._llm_config import get_role_config
  cfg = get_role_config()
  role = cfg.resolve_role("analyst")
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── 配置文件路径 ──────────────────────────────────────────────────────────────

_ENV_CONFIG_PATH = "GRAPH_AGENT_ROLES_PATH"
_CONFIG_FILENAME = "llm_roles.yaml"
_PACKAGE_DIR = Path(__file__).resolve().parent


# ── 数据结构 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelDef:
    """模型注册表条目。"""

    code: str  # 代号，如 CL46T
    name: str  # 人类可读名
    reasoning: bool = False
    min_max_tokens: int = 4096
    max_input_tokens: int | None = None
    fc_supported: bool = False
    providers: dict[str, str] = field(default_factory=dict)  # provider_code → model_name
    provider_options: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderDef:
    """Provider 注册表条目。"""

    code: str  # 代号，如 OC_CL
    name: str
    type: str  # openai_compatible | wavespeed_any_llm | gemini_official | anthropic_compatible
    api_key_env: str = ""
    api_key_env_fallback: str = ""
    base_url: str = ""
    llm_base_url: str = ""  # WaveSpeed LLM 专用 OpenAI 兼容端点
    proxy_env: str = ""
    timeout: int = 120
    trust_env: bool = False
    retry_strategy: str = ""  # "" | "timeout_escalation"


@dataclass(frozen=True)
class RoleModelEntry:
    """角色内的单个模型配置。"""

    model_code: str
    provider_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoleDef:
    """角色注册表条目。"""

    name: str
    temperature: float = 0.7
    model_fallback: bool = False
    active_model: str = ""  # 模型代号
    system_prompt_prefix: str = ""
    models: dict[str, RoleModelEntry] = field(default_factory=dict)  # model_code → entry


@dataclass
class ResolvedProvider:
    """展开后的单个 provider 调用信息。"""

    provider_code: str
    provider_def: ProviderDef
    model_name: str  # 该 provider 下的实际模型名
    model_def: ModelDef
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedRole:
    """展开后的完整角色调用信息。"""

    role_name: str
    temperature: float
    system_prompt_prefix: str
    active_model_code: str
    model_fallback: bool
    # 按优先级排列的调用链：先 active_model 的 providers，再（如果 model_fallback）其他 models
    call_chain: list[ResolvedProvider] = field(default_factory=list)


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Tunable error-threshold + window for ModelResolver provider health."""

    error_threshold: int = 30
    window_seconds: int = 1800
    # Per-provider overrides keyed on provider_code (e.g. OC_CL).
    per_provider: dict[str, CircuitBreakerConfig] = field(default_factory=dict)


def _role_model_order(role: RoleDef) -> list[str]:
    model_order: list[str] = []
    if role.active_model and role.active_model in role.models:
        model_order.append(role.active_model)
    for model_code in role.models:
        if model_code not in model_order:
            model_order.append(model_code)
    return model_order


def _resolved_providers_for_model(
    model_code: str,
    entry: RoleModelEntry,
    model_def: ModelDef,
    providers: dict[str, ProviderDef],
) -> list[ResolvedProvider]:
    call_chain: list[ResolvedProvider] = []
    for provider_code in entry.provider_codes:
        resolved = _resolve_provider_for_model(model_code, provider_code, model_def, providers)
        if resolved is not None:
            call_chain.append(resolved)
    return call_chain


def _resolve_provider_for_model(
    model_code: str,
    provider_code: str,
    model_def: ModelDef,
    providers: dict[str, ProviderDef],
) -> ResolvedProvider | None:
    prov_def = providers.get(provider_code)
    if prov_def is None:
        logger.warning("模型 %s 引用了未注册的 provider 代号: %s", model_code, provider_code)
        return None
    model_name = model_def.providers.get(provider_code)
    if model_name is None:
        logger.warning(
            "模型 %s 在 provider %s 下无模型名映射",
            model_code,
            provider_code,
        )
        return None
    return ResolvedProvider(
        provider_code=provider_code,
        provider_def=prov_def,
        model_name=model_name,
        model_def=model_def,
        provider_options=model_def.provider_options.get(provider_code, {}),
    )


@dataclass
class RoleConfigData:
    """配置文件的完整解析结果。"""

    models: dict[str, ModelDef] = field(default_factory=dict)
    providers: dict[str, ProviderDef] = field(default_factory=dict)
    roles: dict[str, RoleDef] = field(default_factory=dict)
    # Task 6.2 — same-tier peer model groups. Key = group id (e.g. "coding",
    # "reasoning"), value = list of model_code in preference order. When
    # a role's call_chain exhausts, ModelResolver looks up the active
    # model's peer group (if any) and tries those models' chains in turn.
    peer_model_groups: dict[str, list[str]] = field(default_factory=dict)
    # Task 6.4 — circuit-breaker thresholds; read by ModelResolver instead
    # of the former hard-coded 30/1800.
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    # Task 6.2 — roles that should NOT participate in peer fallback even
    # if their active model belongs to a peer_model_group (e.g. a final
    # validation step that must use one specific model or fail loudly).
    single_model_roles: list[str] = field(default_factory=list)

    def resolve_role(self, role_name: str) -> ResolvedRole:
        """展开角色为完整调用链。"""
        role = self.roles.get(role_name)
        if role is None:
            raise KeyError(f"未知角色: {role_name}")

        call_chain: list[ResolvedProvider] = []
        model_order = _role_model_order(role)

        for model_code in model_order:
            entry = role.models.get(model_code)
            if entry is None:
                continue
            model_def = self.models.get(model_code)
            if model_def is None:
                logger.warning("角色 %s 引用了未注册的模型代号: %s", role_name, model_code)
                continue

            call_chain.extend(
                _resolved_providers_for_model(
                    model_code,
                    entry,
                    model_def,
                    self.providers,
                )
            )

            # 如果不启用 model_fallback，只用 active_model 这一个
            if not role.model_fallback and model_code == role.active_model:
                break

        return ResolvedRole(
            role_name=role_name,
            temperature=role.temperature,
            system_prompt_prefix=(role.system_prompt_prefix or "").strip(),
            active_model_code=role.active_model,
            model_fallback=role.model_fallback,
            call_chain=call_chain,
        )

    def resolve_model(self, model_code: str) -> ResolvedRole:
        """Resolve a specific ``model_code`` directly into a ResolvedRole.

        Builds a synthetic ResolvedRole whose call_chain covers every
        provider that this model is registered under in
        ``llm_roles.yaml``'s ``models:`` section. Used by the
        ``model_override`` phase field (Task 6.1) to pin a phase to a
        single model without going through the tier → role → model
        lookup.

        Raises KeyError when the model_code is not registered.
        """
        model_def = self.models.get(model_code)
        if model_def is None:
            raise KeyError(f"未知模型代号: {model_code}")

        call_chain: list[ResolvedProvider] = []
        for pc, model_name in (model_def.providers or {}).items():
            prov_def = self.providers.get(pc)
            if prov_def is None:
                logger.warning(
                    "model_override %s 引用了未注册的 provider 代号: %s",
                    model_code,
                    pc,
                )
                continue
            prov_opts = model_def.provider_options.get(pc, {})
            call_chain.append(
                ResolvedProvider(
                    provider_code=pc,
                    provider_def=prov_def,
                    model_name=model_name,
                    model_def=model_def,
                    provider_options=prov_opts,
                )
            )

        return ResolvedRole(
            role_name=f"_model_override::{model_code}",
            temperature=0.7,  # neutral default; no role-level temperature to inherit
            system_prompt_prefix="",
            active_model_code=model_code,
            model_fallback=False,
            call_chain=call_chain,
        )


# ── YAML 解析 ─────────────────────────────────────────────────────────────────


def _parse_models(raw: dict[str, Any] | None) -> dict[str, ModelDef]:
    result: dict[str, ModelDef] = {}
    for code, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("模型 %s 配置无效（非 dict），跳过", code)
            continue
        result[code] = ModelDef(
            code=code,
            name=data.get("name", code),
            reasoning=bool(data.get("reasoning", False)),
            min_max_tokens=int(data.get("min_max_tokens", 4096)),
            max_input_tokens=(
                int(data["max_input_tokens"])
                if isinstance(data.get("max_input_tokens"), int)
                else None
            ),
            fc_supported=bool(data.get("fc_supported", False)),
            providers=dict(data.get("providers", {})),
            provider_options={k: dict(v) for k, v in (data.get("provider_options") or {}).items()},
        )
    return result


def _parse_providers(raw: dict[str, Any] | None) -> dict[str, ProviderDef]:
    result: dict[str, ProviderDef] = {}
    for code, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("Provider %s 配置无效（非 dict），跳过", code)
            continue
        result[code] = ProviderDef(
            code=code,
            name=data.get("name", code),
            type=data.get("type", "openai_compatible"),
            api_key_env=data.get("api_key_env", ""),
            api_key_env_fallback=data.get("api_key_env_fallback", ""),
            base_url=data.get("base_url", ""),
            llm_base_url=data.get("llm_base_url", ""),
            proxy_env=data.get("proxy_env", ""),
            timeout=int(data.get("timeout", 120)),
            trust_env=bool(data.get("trust_env", False)),
            retry_strategy=data.get("retry_strategy", ""),
        )
    return result


def _parse_roles(
    raw: dict[str, Any] | None,
    models: dict[str, ModelDef],
) -> dict[str, RoleDef]:
    result: dict[str, RoleDef] = {}
    for name, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("角色 %s 配置无效（非 dict），跳过", name)
            continue

        models_map: dict[str, RoleModelEntry] = {}
        for mc, mdata in (data.get("models") or {}).items():
            providers_list = mdata.get("providers", []) if isinstance(mdata, dict) else []
            models_map[mc] = RoleModelEntry(
                model_code=mc,
                provider_codes=list(providers_list),
            )

        result[name] = RoleDef(
            name=name,
            temperature=float(data.get("temperature", 0.7)),
            model_fallback=bool(data.get("model_fallback", False)),
            active_model=data.get("active_model", ""),
            system_prompt_prefix=data.get("system_prompt_prefix", ""),
            models=models_map,
        )
    return result


def _validate_cross_references(
    models: dict[str, ModelDef],
    providers: dict[str, ProviderDef],
    roles: dict[str, RoleDef],
) -> list[str]:
    """代号交叉验证，返回错误列表。"""
    errors: list[str] = []
    errors.extend(_validate_model_provider_refs(models, providers))
    errors.extend(_validate_role_refs(models, providers, roles))
    return errors


def _validate_model_provider_refs(
    models: dict[str, ModelDef],
    providers: dict[str, ProviderDef],
) -> list[str]:
    errors: list[str] = []
    for mc, mdef in models.items():
        for pc in mdef.providers:
            if pc not in providers:
                errors.append(f"模型 {mc} 引用了未注册的 provider: {pc}")
    return errors


def _validate_role_refs(
    models: dict[str, ModelDef],
    providers: dict[str, ProviderDef],
    roles: dict[str, RoleDef],
) -> list[str]:
    errors: list[str] = []
    for rname, rdef in roles.items():
        if rdef.active_model and rdef.active_model not in models:
            errors.append(f"角色 {rname} 的 active_model={rdef.active_model} 未在 models 注册")
        errors.extend(_validate_role_model_entries(rname, rdef, models, providers))
    return errors


def _validate_role_model_entries(
    role_name: str,
    role: RoleDef,
    models: dict[str, ModelDef],
    providers: dict[str, ProviderDef],
) -> list[str]:
    errors: list[str] = []
    for model_code, entry in role.models.items():
        if model_code not in models:
            errors.append(f"角色 {role_name} 引用了未注册的模型: {model_code}")
        errors.extend(
            _validate_role_provider_entries(role_name, model_code, entry, models, providers)
        )
    return errors


def _validate_role_provider_entries(
    role_name: str,
    model_code: str,
    entry: RoleModelEntry,
    models: dict[str, ModelDef],
    providers: dict[str, ProviderDef],
) -> list[str]:
    errors: list[str] = []
    for provider_code in entry.provider_codes:
        if provider_code not in providers:
            errors.append(
                f"角色 {role_name} 模型 {model_code} 引用了未注册的 provider: {provider_code}"
            )
        elif model_code in models and provider_code not in models[model_code].providers:
            errors.append(
                f"角色 {role_name} 模型 {model_code} 使用 provider {provider_code}，"
                f"但模型未注册该 provider 的模型名映射"
            )
    return errors


def _normalize_path(path_like: str | Path) -> Path:
    """Normalize explicit config paths, resolving relative paths from CWD."""
    path = Path(path_like).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _search_relative_config_path() -> Path | None:
    """Search upward (max 7 levels) for a sibling ``config/llm_roles.yaml``."""
    bases = [_PACKAGE_DIR, *_PACKAGE_DIR.parents]
    for base in bases[:7]:
        candidate = (base / "config" / _CONFIG_FILENAME).resolve()
        if candidate.exists():
            return candidate
    return None


def _resolve_config_path() -> Path | None:
    """Resolve config path via env override, then relative search."""
    env_path = os.getenv(_ENV_CONFIG_PATH, "").strip()
    if env_path:
        candidate = _normalize_path(env_path)
        if candidate.exists():
            return candidate
        logger.warning(
            "[LLMRoleConfig] 环境变量 %s 指向的配置不存在: %s；继续尝试相对路径",
            _ENV_CONFIG_PATH,
            candidate,
        )

    return _search_relative_config_path()


def _build_builtin_default_config() -> RoleConfigData:
    """Return a minimal built-in fallback config for portable imports."""
    raw: dict[str, Any] = {
        "models": {
            "OPENAI_DEFAULT": {
                "name": "OpenAI Default",
                "reasoning": False,
                "min_max_tokens": 4096,
                "fc_supported": True,
                "providers": {
                    "OPENAI_DEFAULT": "gpt-4.1-mini",
                },
            }
        },
        "providers": {
            "OPENAI_DEFAULT": {
                "name": "OpenAI Default",
                "type": "openai_compatible",
                "api_key_env": "OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
                "timeout": 120,
                "trust_env": False,
            }
        },
        "roles": {
            "balanced": {
                "temperature": 0.7,
                "model_fallback": False,
                "active_model": "OPENAI_DEFAULT",
                "models": {
                    "OPENAI_DEFAULT": {
                        "providers": ["OPENAI_DEFAULT"],
                    }
                },
            }
        },
    }

    models = _parse_models(raw.get("models"))
    providers = _parse_providers(raw.get("providers"))
    roles = _parse_roles(raw.get("roles"), models)
    errors = _validate_cross_references(models, providers, roles)
    if errors:
        raise ValueError(f"内置默认 llm_roles 配置无效: {'; '.join(errors)}")
    logger.warning("[LLMRoleConfig] 未找到 llm_roles.yaml，回退到内置最小默认配置")
    return RoleConfigData(models=models, providers=providers, roles=roles)


def _load_config_file(path: Path) -> tuple[RoleConfigData, int]:
    """Load one concrete YAML config file and return config + source mtime_ns."""
    with path.open("r", encoding="utf-8") as f:
        source_mtime_ns = os.fstat(f.fileno()).st_mtime_ns
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"配置文件格式错误（顶层非 dict）: {path}")

    models = _parse_models(raw.get("models"))
    providers = _parse_providers(raw.get("providers"))
    roles = _parse_roles(raw.get("roles"), models)

    errors = _validate_cross_references(models, providers, roles)
    if errors:
        for e in errors:
            logger.error("[LLMRoleConfig] 验证错误: %s", e)
        raise ValueError(f"配置文件验证失败（{len(errors)} 个错误）: {'; '.join(errors[:5])}")

    # Task 6.2 / 6.4 — new top-level sections, all optional
    peer_groups = _parse_peer_model_groups(raw.get("peer_model_groups"), models)
    circuit_breaker = _parse_circuit_breaker(raw.get("circuit_breaker"))
    single_model_roles = _parse_single_model_roles(raw.get("single_model_roles"), roles)

    logger.info(
        "[LLMRoleConfig] 加载成功: %d 模型, %d provider, %d 角色, "
        "%d peer group, single_model_roles=%d",
        len(models),
        len(providers),
        len(roles),
        len(peer_groups),
        len(single_model_roles),
    )
    return RoleConfigData(
        models=models,
        providers=providers,
        roles=roles,
        peer_model_groups=peer_groups,
        circuit_breaker=circuit_breaker,
        single_model_roles=single_model_roles,
    ), source_mtime_ns


def _parse_peer_model_groups(raw: Any, models: dict[str, ModelDef]) -> dict[str, list[str]]:
    """Parse optional ``peer_model_groups`` section.

    Format::

        peer_model_groups:
          coding:
            - DeepSeek_Coder
            - DeepSeek_Chat
          reasoning:
            - CL46T
            - CLO46T

    Unknown model codes are logged and dropped so a typo cannot silently
    re-route production traffic.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        logger.warning("[LLMRoleConfig] peer_model_groups 格式错误（应为 dict），跳过")
        return {}
    result: dict[str, list[str]] = {}
    for group_name, codes in raw.items():
        if not isinstance(codes, list):
            logger.warning("[LLMRoleConfig] peer_model_groups.%s 不是 list，跳过", group_name)
            continue
        valid_codes: list[str] = []
        for code in codes:
            if code in models:
                valid_codes.append(code)
            else:
                logger.warning(
                    "[LLMRoleConfig] peer_model_groups.%s 引用未知模型 %r",
                    group_name,
                    code,
                )
        if valid_codes:
            result[str(group_name)] = valid_codes
    return result


def _parse_circuit_breaker(raw: Any) -> CircuitBreakerConfig:
    if raw is None:
        return CircuitBreakerConfig()
    if not isinstance(raw, dict):
        logger.warning("[LLMRoleConfig] circuit_breaker 格式错误（应为 dict），回退到默认")
        return CircuitBreakerConfig()

    per_provider_raw = raw.get("per_provider") or {}
    per_provider: dict[str, CircuitBreakerConfig] = {}
    if isinstance(per_provider_raw, dict):
        for prov_code, per_cfg in per_provider_raw.items():
            if not isinstance(per_cfg, dict):
                continue
            per_provider[str(prov_code)] = CircuitBreakerConfig(
                error_threshold=int(per_cfg.get("error_threshold", 30)),
                window_seconds=int(per_cfg.get("window_seconds", 1800)),
                per_provider={},  # no recursive override
            )

    return CircuitBreakerConfig(
        error_threshold=int(raw.get("error_threshold", 30)),
        window_seconds=int(raw.get("window_seconds", 1800)),
        per_provider=per_provider,
    )


def _parse_single_model_roles(raw: Any, roles: dict[str, RoleDef]) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning("[LLMRoleConfig] single_model_roles 格式错误（应为 list），跳过")
        return []
    out: list[str] = []
    for role_name in raw:
        if role_name in roles:
            out.append(str(role_name))
        else:
            logger.warning("[LLMRoleConfig] single_model_roles 引用未知角色 %r", role_name)
    return out


def load_config(config_path: Path | None = None) -> RoleConfigData:
    """加载并验证 YAML 配置文件。

    解析顺序：
    1. 显式 ``config_path``
    2. 环境变量 ``GRAPH_AGENT_ROLES_PATH``
    3. 向上搜索 ``config/llm_roles.yaml``
    4. 内置最小默认配置
    """
    if config_path is not None:
        path = _normalize_path(config_path)
        return _load_config_file(path)[0]

    resolved = _resolve_config_path()
    if resolved is None:
        return _build_builtin_default_config()
    return _load_config_file(resolved)[0]


def _safe_get_mtime_ns(path: Path | None) -> int | None:
    """Best-effort file mtime lookup; returns None when path is absent/unreadable."""
    if path is None:
        return None
    try:
        return path.stat().st_mtime_ns
    except OSError as exc:
        logger.warning(
            "phase=llm_config action=mtime_lookup fallback "
            "from=stat to=unknown_mtime path=%s reason=%s",
            path,
            type(exc).__name__,
        )
        return None


# ── 热加载单例 ────────────────────────────────────────────────────────────────


class _RoleConfigHolder:
    """线程安全的配置持有器，支持 mtime 热加载。

    这里仍然存在配置写入与读取并发时的天然竞态，但通过：
    1. 解析环境变量/相对路径时重试一次
    2. 记录已打开文件的 `mtime_ns`
    3. 失败时回退到上次有效配置
    将影响收敛到“下一次 get() 最迟恢复正确版本”。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config: RoleConfigData | None = None
        self._last_mtime_ns: int | None = None
        self._config_path: Path | None = None

    def get(self) -> RoleConfigData:
        """获取当前配置。如果文件变化则重新加载。"""
        resolved_path = _resolve_config_path()
        current_mtime_ns = _safe_get_mtime_ns(resolved_path)

        # Fast path: capture local ref to avoid TOCTOU race with reset()
        cfg = self._config
        if (
            cfg is not None
            and resolved_path == self._config_path
            and current_mtime_ns == self._last_mtime_ns
        ):
            return cfg

        with self._lock:
            resolved_path = _resolve_config_path()
            current_mtime_ns = _safe_get_mtime_ns(resolved_path)
            if (
                self._config is not None
                and resolved_path == self._config_path
                and current_mtime_ns == self._last_mtime_ns
            ):
                return self._config

            try:
                if resolved_path is None:
                    new_config = _build_builtin_default_config()
                    loaded_mtime_ns = None
                else:
                    new_config, loaded_mtime_ns = _load_config_file(resolved_path)
                self._config = new_config
                self._config_path = resolved_path
                self._last_mtime_ns = loaded_mtime_ns
                return new_config
            except Exception as e:
                if self._config is not None:
                    logger.warning(
                        "[LLMRoleConfig] 热加载失败，使用上次有效配置: %s",
                        e,
                    )
                    return self._config
                raise

    def reset(self) -> None:
        """清除缓存，下次 get() 强制重新加载。"""
        with self._lock:
            self._config = None
            self._config_path = None
            self._last_mtime_ns = None


_holder = _RoleConfigHolder()


def get_role_config() -> RoleConfigData:
    """获取 LLM 角色配置（热加载单例）。"""
    return _holder.get()


def reset_role_config() -> None:
    """清除配置缓存（测试用）。"""
    _holder.reset()
