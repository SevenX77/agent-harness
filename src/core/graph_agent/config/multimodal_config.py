"""Multimodal Role Config — YAML configuration loader.

Responsibilities:
1. Load config/multimodal_roles.yaml → structured dataclass
2. Code cross-validation (role→model→provider chain integrity)
3. Hot reload (mtime check, reload on change)
4. Error reporting (fallback to last valid config on failure)
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

_PACKAGE_DIR = Path(__file__).resolve().parent
_CONFIG_FILENAME = "multimodal_roles.yaml"


def _search_multimodal_config_path() -> Path | None:
    """Search upward (max 6 levels) for ``config/multimodal_roles.yaml``."""
    bases = [_PACKAGE_DIR, *_PACKAGE_DIR.parents]
    for base in bases[:7]:
        candidate = (base / "config" / _CONFIG_FILENAME).resolve()
        if candidate.exists():
            return candidate
    return None


@dataclass(frozen=True)
class MultimodalModelDef:
    code: str
    name: str
    task_type: str = ""
    providers: dict[str, str] = field(default_factory=dict)
    provider_options: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class MultimodalProviderDef:
    code: str
    name: str
    type: str
    api_key_env: str = ""
    base_url: str = ""
    proxy_env: str = ""
    timeout: int = 120
    poll_interval: int = 5


@dataclass(frozen=True)
class MultimodalRoleModelEntry:
    model_code: str
    provider_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MultimodalRoleDef:
    name: str
    model_fallback: bool = False
    active_model: str = ""
    models: dict[str, MultimodalRoleModelEntry] = field(default_factory=dict)


@dataclass
class ResolvedMultimodalProvider:
    provider_code: str
    provider_def: MultimodalProviderDef
    model_name: str
    model_def: MultimodalModelDef
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedMultimodalRole:
    role_name: str
    active_model_code: str
    model_fallback: bool
    call_chain: list[ResolvedMultimodalProvider] = field(default_factory=list)


@dataclass
class MultimodalRoleConfigData:
    models: dict[str, MultimodalModelDef] = field(default_factory=dict)
    providers: dict[str, MultimodalProviderDef] = field(default_factory=dict)
    roles: dict[str, MultimodalRoleDef] = field(default_factory=dict)

    def resolve_role(self, role_name: str) -> ResolvedMultimodalRole:
        role = self.roles.get(role_name)
        if role is None:
            raise KeyError(f"Unknown multimodal role: {role_name}")

        call_chain: list[ResolvedMultimodalProvider] = []
        model_order: list[str] = []

        if role.active_model and role.active_model in role.models:
            model_order.append(role.active_model)
        for model_code in role.models:
            if model_code not in model_order:
                model_order.append(model_code)

        for model_code in model_order:
            entry = role.models.get(model_code)
            if entry is None:
                continue
            model_def = self.models.get(model_code)
            if model_def is None:
                logger.warning(
                    "Multimodal role %s references unregistered model code: %s",
                    role_name,
                    model_code,
                )
                continue
            for provider_code in entry.provider_codes:
                provider_def = self.providers.get(provider_code)
                if provider_def is None:
                    logger.warning(
                        "Multimodal model %s references unregistered provider code: %s",
                        model_code,
                        provider_code,
                    )
                    continue
                model_name = model_def.providers.get(provider_code)
                if model_name is None:
                    logger.warning(
                        "Multimodal model %s has no model name mapping for provider %s",
                        model_code,
                        provider_code,
                    )
                    continue
                provider_options = model_def.provider_options.get(provider_code, {})
                call_chain.append(
                    ResolvedMultimodalProvider(
                        provider_code=provider_code,
                        provider_def=provider_def,
                        model_name=model_name,
                        model_def=model_def,
                        provider_options=provider_options,
                    )
                )
            if not role.model_fallback and model_code == role.active_model:
                break

        return ResolvedMultimodalRole(
            role_name=role_name,
            active_model_code=role.active_model,
            model_fallback=role.model_fallback,
            call_chain=call_chain,
        )


def _parse_models(raw: dict) -> dict[str, MultimodalModelDef]:
    result: dict[str, MultimodalModelDef] = {}
    for code, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("Multimodal model %s config invalid (not dict), skipping", code)
            continue
        result[code] = MultimodalModelDef(
            code=code,
            name=data.get("name", code),
            task_type=data.get("task_type", ""),
            providers=dict(data.get("providers", {})),
            provider_options={
                k: dict(v) for k, v in (data.get("provider_options") or {}).items()
            },
        )
    return result


def _parse_providers(raw: dict) -> dict[str, MultimodalProviderDef]:
    result: dict[str, MultimodalProviderDef] = {}
    for code, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("Multimodal provider %s config invalid (not dict), skipping", code)
            continue
        result[code] = MultimodalProviderDef(
            code=code,
            name=data.get("name", code),
            type=data.get("type", "ark_openai"),
            api_key_env=data.get("api_key_env", ""),
            base_url=data.get("base_url", ""),
            proxy_env=data.get("proxy_env", ""),
            timeout=int(data.get("timeout", 120)),
            poll_interval=int(data.get("poll_interval", 5)),
        )
    return result


def _parse_roles(raw: dict) -> dict[str, MultimodalRoleDef]:
    result: dict[str, MultimodalRoleDef] = {}
    for name, data in (raw or {}).items():
        if not isinstance(data, dict):
            logger.warning("Multimodal role %s config invalid (not dict), skipping", name)
            continue
        models_map: dict[str, MultimodalRoleModelEntry] = {}
        for model_code, model_data in (data.get("models") or {}).items():
            providers_list: list[str]
            if isinstance(model_data, dict):
                providers_list = list(model_data.get("providers", []))
            else:
                providers_list = []
            models_map[model_code] = MultimodalRoleModelEntry(
                model_code=model_code,
                provider_codes=providers_list,
            )
        result[name] = MultimodalRoleDef(
            name=name,
            model_fallback=bool(data.get("model_fallback", False)),
            active_model=data.get("active_model", ""),
            models=models_map,
        )
    return result


def _validate_cross_references(
    models: dict[str, MultimodalModelDef],
    providers: dict[str, MultimodalProviderDef],
    roles: dict[str, MultimodalRoleDef],
) -> list[str]:
    errors: list[str] = []
    for model_code, model_def in models.items():
        for provider_code in model_def.providers:
            if provider_code not in providers:
                errors.append(
                    f"Multimodal model {model_code} references unregistered provider: {provider_code}"
                )
    for role_name, role_def in roles.items():
        if role_def.active_model and role_def.active_model not in models:
            errors.append(
                f"Multimodal role {role_name} active_model={role_def.active_model} not registered in models"
            )
        for model_code, entry in role_def.models.items():
            if model_code not in models:
                errors.append(f"Multimodal role {role_name} references unregistered model: {model_code}")
                continue
            for provider_code in entry.provider_codes:
                if provider_code not in providers:
                    errors.append(
                        f"Multimodal role {role_name} model {model_code} references unregistered provider: {provider_code}"
                    )
                elif provider_code not in models[model_code].providers:
                    errors.append(
                        f"Multimodal role {role_name} model {model_code} uses provider {provider_code}, "
                        "but model has no model name mapping for this provider"
                    )
    return errors


def _build_builtin_default_config() -> MultimodalRoleConfigData:
    """Return empty default config when no multimodal_roles.yaml is found."""
    logger.warning("[MultimodalRoleConfig] No config found, multimodal tools unavailable")
    return MultimodalRoleConfigData()


def load_multimodal_config(config_path: Path | None = None) -> MultimodalRoleConfigData:
    """Load multimodal config from YAML file."""
    path = config_path or _DEFAULT_CONFIG_PATH
    if path is None:
        return _build_builtin_default_config()
    
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    if not isinstance(raw, dict):
        raise ValueError(f"Config file format error (top level not dict): {path}")
    
    models = _parse_models(raw.get("models"))
    providers = _parse_providers(raw.get("providers"))
    roles = _parse_roles(raw.get("roles"))
    errors = _validate_cross_references(models, providers, roles)
    if errors:
        for error in errors:
            logger.error("[MultimodalRoleConfig] Validation error: %s", error)
        raise ValueError(
            f"Config validation failed ({len(errors)} errors): {'; '.join(errors[:5])}"
        )
    logger.info(
        "[MultimodalRoleConfig] Loaded successfully: %d models, %d providers, %d roles",
        len(models),
        len(providers),
        len(roles),
    )
    return MultimodalRoleConfigData(models=models, providers=providers, roles=roles)


def _safe_get_mtime_ns(path: Path | None) -> int | None:
    """Safely get mtime_ns for a path."""
    if path is None:
        return None
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


class _MultimodalRoleConfigHolder:
    """Holder for multimodal role config with hot reload support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config: MultimodalRoleConfigData | None = None
        self._last_mtime_ns: int | None = None
        self._last_config_path: Path | None = None

    @staticmethod
    def _resolve_config_path() -> Path | None:
        """Dynamically resolve config path (env var > upward search)."""
        env_path = os.getenv("MULTIMODAL_ROLES_CONFIG_PATH", "").strip()
        if env_path:
            return Path(env_path).expanduser().resolve()
        return _search_multimodal_config_path()

    def get(self) -> MultimodalRoleConfigData:
        """Get config, reloading if file has changed."""
        resolved_path = self._resolve_config_path()
        if resolved_path is None:
            return _build_builtin_default_config()

        current_mtime_ns = _safe_get_mtime_ns(resolved_path)

        cfg = self._config
        if (
            cfg is not None
            and resolved_path == self._last_config_path
            and current_mtime_ns == self._last_mtime_ns
        ):
            return cfg

        with self._lock:
            cfg = self._config
            if (
                cfg is not None
                and resolved_path == self._last_config_path
                and current_mtime_ns == self._last_mtime_ns
            ):
                return cfg

            if not resolved_path.exists():
                if self._config is None:
                    self._config = _build_builtin_default_config()
                    self._last_mtime_ns = None
                    self._last_config_path = resolved_path
                return self._config

            try:
                new_config = load_multimodal_config(resolved_path)
                self._config = new_config
                self._last_mtime_ns = current_mtime_ns
                self._last_config_path = resolved_path
                return new_config
            except Exception as exc:
                if self._config is not None:
                    logger.warning(
                        "[MultimodalRoleConfig] Hot reload failed, using last valid config: %s",
                        exc,
                    )
                    return self._config
                raise

    def reset(self) -> None:
        """Reset config to force reload on next get()."""
        with self._lock:
            self._config = None
            self._last_mtime_ns = None
            self._last_config_path = None


_holder = _MultimodalRoleConfigHolder()


def get_multimodal_role_config() -> MultimodalRoleConfigData:
    """Get the current multimodal role config."""
    return _holder.get()


def reset_multimodal_role_config() -> None:
    """Reset the config holder to force reload."""
    _holder.reset()
