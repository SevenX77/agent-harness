"""Structured gateway exceptions."""

from __future__ import annotations

from typing import Any


class GatewayError(Exception):
    """Base class for gateway failures with a stable error code."""

    code: str

    def __init__(
        self,
        message: str,
        *,
        code: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.context = dict(context or {})
        super().__init__(f"{code} {message}")


class AllProvidersFailedError(GatewayError):
    """All provider/model candidates in one fallback chain failed."""

    def __init__(
        self,
        role_name: str,
        provider_errors: list[dict[str, Any]],
        *,
        phase_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        provider_codes = [str(item.get("provider", "")) for item in provider_errors]
        message = (
            f"All providers failed for role={role_name}: "
            f"{len(provider_errors)} provider candidates failed"
        )
        payload = {
            "role_name": role_name,
            "phase_name": phase_name or "<gateway>",
            "failed_provider_codes": provider_codes,
            "last_error_chain": provider_errors,
            **dict(context or {}),
        }
        super().__init__(
            message,
            code="[F-v3-gateway-all-providers-failed]",
            context=payload,
        )


class GatewayResolverMissingError(GatewayError):
    """A phase requiring an LLM ran without a model resolver dependency."""

    def __init__(self, *, phase_name: str | None = None) -> None:
        super().__init__(
            "model_resolver is required for LLM/Agent phases",
            code="[F-v3-gateway-resolver-missing]",
            context={
                "phase_name": phase_name or "<unknown>",
                "required_dependency": "model_resolver",
            },
        )


class GatewayRoleNotConfiguredError(GatewayError):
    """The requested role or model override is not present in the registry."""

    def __init__(
        self,
        *,
        role_name: str | None = None,
        model_override: str | None = None,
    ) -> None:
        context = {
            "role_name": role_name,
            "model_override": model_override,
        }
        super().__init__(
            "gateway role/model is not configured",
            code="[F-v3-gateway-role-not-configured]",
            context=context,
        )
