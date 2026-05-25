"""Concrete gateway model resolver."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from graph_agent_gateway.exceptions import (
    AllProvidersFailedError,
    GatewayRoleNotConfiguredError,
)
from graph_agent_gateway.gateway_chat_model import GatewayChatModel
from graph_agent_gateway.llm_config import (
    ModelDef,
    ProviderDef,
    ResolvedProvider,
    ResolvedRole,
    RoleModelEntry,
    RolesData,
)


@dataclass
class ModelResolverStats:
    """Runtime statistics for resolver calls."""

    total_resolves: int = 0


class ModelResolver:
    """Resolve role/model configuration to a GatewayChatModel."""

    def __init__(
        self,
        *,
        roles_data: RolesData | None = None,
        client_manager: Any = None,
    ) -> None:
        self.roles_data = roles_data if roles_data is not None else _load_default_roles_data()
        self.client_manager = client_manager
        self._stats_lock = threading.Lock()
        self.stats = ModelResolverStats()

    def resolve(
        self,
        role_name: str | None = None,
        *,
        thinking_enabled: bool | None = None,
        model_override: str | None = None,
        callbacks: tuple[Any, ...] = (),
        phase_name: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        del kwargs
        with self._stats_lock:
            self.stats.total_resolves += 1
        resolved, temperature, max_tokens = self._resolve_role(
            role_name=role_name,
            model_override=model_override,
        )
        if not resolved.call_chain:
            raise AllProvidersFailedError(
                resolved.role_name,
                [],
                phase_name=phase_name or "<gateway>",
            )
        mock_strategy = getattr(self, "_graph_agent_predict_mock_strategy", None)
        if mock_strategy is not None:
            from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

            return PredictGatewayChatModel(
                resolved.role_name,
                resolved,
                mock_strategy=mock_strategy,
                max_tokens=max_tokens,
                temperature=temperature,
                callbacks=callbacks,
                phase_name=phase_name,
                thinking_enabled=thinking_enabled,
                client_manager=self.client_manager,
                name=resolved.call_chain[0].model_name,
            )
        return GatewayChatModel(
            resolved.role_name,
            resolved,
            max_tokens=max_tokens,
            temperature=temperature,
            callbacks=callbacks,
            phase_name=phase_name,
            thinking_enabled=thinking_enabled,
            client_manager=self.client_manager,
            name=resolved.call_chain[0].model_name,
        )

    def _resolve_role(
        self,
        *,
        role_name: str | None,
        model_override: str | None,
    ) -> tuple[ResolvedRole, float, int]:
        effective_role = role_name or os.environ.get("GRAPH_AGENT_DEFAULT_ROLE", "balanced")
        role = self.roles_data.roles.get(effective_role)
        if role is None:
            raise GatewayRoleNotConfiguredError(
                role_name=effective_role,
                model_override=model_override,
            )

        if model_override is not None and model_override not in self.roles_data.models:
            raise GatewayRoleNotConfiguredError(
                role_name=effective_role,
                model_override=model_override,
            )

        if model_override is not None:
            model_order = [model_override]
            resolved_role_name = f"_model_override::{model_override}"
            active_model_code = model_override
        else:
            model_order = [role.active_model]
            resolved_role_name = effective_role
            active_model_code = role.active_model

        if (
            model_override is None
            and role.model_fallback
            and effective_role not in self.roles_data.single_model_roles
        ):
            model_order.extend(code for code in role.models if code not in model_order)

        call_chain: list[ResolvedProvider] = []
        first_temperature = 0.7
        first_max_tokens = 4096
        for index, model_code in enumerate(model_order):
            role_model = role.models.get(model_code)
            if role_model is None and model_override is not None:
                role_model = RoleModelEntry(
                    providers=list(self.roles_data.models[model_code].providers.keys())
                )
            model_entry = self.roles_data.models.get(model_code)
            if role_model is None or model_entry is None:
                raise GatewayRoleNotConfiguredError(
                    role_name=effective_role,
                    model_override=model_code,
                )
            if index == 0:
                first_temperature = (
                    role_model.temperature
                    if role_model.temperature is not None
                    else (role.temperature if role.temperature is not None else 0.7)
                )
                first_max_tokens = (
                    role_model.max_tokens
                    if role_model.max_tokens is not None
                    else (
                        _provider_max_tokens(
                            model_entry.provider_options or {},
                            role_model.providers,
                        )
                        or role.max_tokens
                        or model_entry.min_max_tokens
                        or 4096
                    )
                )
            for provider_code in role_model.providers:
                provider_entry = self.roles_data.providers.get(provider_code)
                model_name = model_entry.providers.get(provider_code)
                if provider_entry is None or model_name is None:
                    raise GatewayRoleNotConfiguredError(
                        role_name=effective_role,
                        model_override=model_code,
                    )
                call_chain.append(
                    ResolvedProvider(
                        provider_code=provider_code,
                        provider_def=ProviderDef(
                            code=provider_code,
                            **provider_entry.model_dump(exclude_none=True),
                        ),
                        model_name=model_name,
                        model_def=ModelDef(
                            code=model_code,
                            **model_entry.model_dump(exclude_none=True),
                        ),
                        provider_options=(model_entry.provider_options or {}).get(
                            provider_code,
                            {},
                        ),
                    )
                )

        resolved = ResolvedRole(
            role_name=resolved_role_name,
            temperature=first_temperature,
            system_prompt_prefix=role.system_prompt_prefix or "",
            active_model_code=active_model_code,
            model_fallback=role.model_fallback,
            call_chain=call_chain,
        )
        return resolved, first_temperature, first_max_tokens

    def mark_provider_down(self, provider_code: str, model_name: str) -> None:
        """Manually mark a provider/model down in the shared gateway cache."""
        manager = (
            self.client_manager
            if self.client_manager is not None
            else _default_client_manager()
        )
        if hasattr(manager, "mark_provider_down"):
            manager.mark_provider_down(provider_code, RuntimeError("manual mark down"))
        else:
            manager._mark_provider_down(provider_code, model_name)


def _load_default_roles_data() -> RolesData:
    import yaml

    root = Path(__file__).resolve().parents[4]
    payload = yaml.safe_load((root / "config" / "llm_roles.yaml").read_text(encoding="utf-8"))
    return RolesData.model_validate(payload)


def _default_client_manager() -> Any:
    from graph_agent.models.llm_client_manager import LLMClientManager

    return LLMClientManager


def _provider_max_tokens(
    provider_options: dict[str, dict[str, Any]],
    provider_codes: list[str],
) -> int | None:
    for provider_code in provider_codes:
        value = provider_options.get(provider_code, {}).get("max_max_tokens")
        if isinstance(value, int) and value > 0:
            return value
    return None
