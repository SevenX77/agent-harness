"""Credential provider implementations for registry snapshots."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import SecretStr

from graph_agent_gateway.registry.contracts import CredentialDescriptor, CredentialProviderProtocol
from graph_agent_gateway.registry.schema import ProviderEndpoint
from graph_agent_gateway.registry.storage import compute_credential_fingerprint


class EndpointCredentialProvider:
    """Resolve endpoint-backed credential refs without putting secrets on routes."""

    def __init__(self, endpoints: Mapping[str, ProviderEndpoint]) -> None:
        self._endpoints_by_ref: dict[str, ProviderEndpoint] = {}
        for endpoint in endpoints.values():
            self._endpoints_by_ref[f"endpoint:{endpoint.endpoint_id}"] = endpoint
            if endpoint.credential_ref:
                self._endpoints_by_ref[endpoint.credential_ref] = endpoint

    def describe(self, ref: str) -> CredentialDescriptor:
        endpoint = self._endpoints_by_ref.get(ref)
        if endpoint is None:
            return CredentialDescriptor(ref=ref, exists=False, status="missing")
        secret = endpoint.api_key
        exists = bool(secret and secret.get_secret_value())
        return CredentialDescriptor(
            ref=ref,
            exists=exists,
            status="available" if exists else "missing",
            fingerprint=compute_credential_fingerprint(endpoint),
            scope=endpoint.endpoint_id,
        )

    def get(self, ref: str) -> SecretStr:
        endpoint = self._endpoints_by_ref.get(ref)
        if endpoint is None:
            raise KeyError(ref)
        secret = endpoint.api_key
        if secret is None or not secret.get_secret_value():
            raise KeyError(ref)
        return secret


class FallbackCredentialProvider:
    """Try a host provider first, then endpoint-backed migration storage."""

    def __init__(
        self,
        primary: CredentialProviderProtocol,
        fallback: CredentialProviderProtocol,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def describe(self, ref: str) -> CredentialDescriptor:
        try:
            descriptor = self._primary.describe(ref)
        except Exception:
            descriptor = None
        if descriptor is not None and descriptor.exists:
            return descriptor
        return self._fallback.describe(ref)

    def get(self, ref: str) -> SecretStr | str:
        try:
            return self._primary.get(ref)
        except Exception:
            return self._fallback.get(ref)
