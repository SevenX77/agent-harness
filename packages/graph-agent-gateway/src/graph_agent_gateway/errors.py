"""Structured gateway exceptions."""

from __future__ import annotations

from typing import Any

from graph_agent import ModelProviderError


class GatewayError(ModelProviderError):
    """Base class for gateway failures with a stable error code.

    Membership of the engine's public error catalog is a contract, not a
    convenience: ``docs/engine/public-api-contract.md`` states as a
    postcondition of ``ModelProviderError`` that this class and its leaves are
    ``isinstance(..., ModelProviderError)``, so a host catches one of five
    families instead of a long tail of leaves. That is why the import below is
    unconditional. It used to sit behind a ``try/except`` that fell back to
    ``RuntimeError``, which turned a missing dependency into a second, silent
    mode where the documented postcondition simply did not hold and a caller's
    ``except ModelProviderError`` stopped catching anything. The dependency is
    declared in this package's ``pyproject.toml``; if it is absent the install
    is broken and should say so here.
    """

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
        super().__init__(f"{code} {message}", context=self.context)


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
            "gateway role/route is not configured",
            code="[F-v3-gateway-role-not-configured]",
            context=context,
        )
