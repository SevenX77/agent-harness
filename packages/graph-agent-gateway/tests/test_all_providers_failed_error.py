"""
Test: test_all_providers_failed_error.py
Covers: design.md §1.3 (structured provider error payload) +
tasks.md α3 (gateway failure codes) +
requirements.md §3 R[NEW]-Gateway-02.
"""

from __future__ import annotations


def test_all_providers_failed_error_exposes_standard_payload() -> None:
    from graph_agent_gateway.exceptions import AllProvidersFailedError

    exc = AllProvidersFailedError(
        role_name="balanced",
        phase_name="draft",
        provider_errors=[
            {
                "provider": "openai/gpt-5",
                "error_type": "RateLimitError",
                "message": "quota exceeded",
            },
            {
                "provider": "anthropic/claude-opus",
                "error_type": "TimeoutError",
                "message": "request timed out",
            },
        ],
    )

    assert exc.code == "[F-v3-gateway-all-providers-failed]"
    assert exc.context["role_name"] == "balanced"
    assert exc.context["phase_name"] == "draft"
    assert exc.context["failed_provider_codes"] == [
        "openai/gpt-5",
        "anthropic/claude-opus",
    ]
    assert exc.context["last_error_chain"] == [
        {
            "provider": "openai/gpt-5",
            "error_type": "RateLimitError",
            "message": "quota exceeded",
        },
        {
            "provider": "anthropic/claude-opus",
            "error_type": "TimeoutError",
            "message": "request timed out",
        },
    ]
    assert "balanced" in str(exc)
    assert "2 provider candidates failed" in str(exc)


def test_resolver_missing_error_uses_v3_gateway_code() -> None:
    from graph_agent_gateway.exceptions import GatewayResolverMissingError

    exc = GatewayResolverMissingError(phase_name="draft")

    assert exc.code == "[F-v3-gateway-resolver-missing]"
    assert exc.context == {
        "phase_name": "draft",
        "required_dependency": "model_resolver",
    }
    assert "[F-v3-gateway-resolver-missing]" in str(exc)


def test_role_not_configured_error_uses_v3_gateway_code() -> None:
    from graph_agent_gateway.exceptions import GatewayRoleNotConfiguredError

    exc = GatewayRoleNotConfiguredError(role_name="premium", model_override="BAD_MODEL")

    assert exc.code == "[F-v3-gateway-role-not-configured]"
    assert exc.context == {
        "role_name": "premium",
        "model_override": "BAD_MODEL",
    }
    assert "[F-v3-gateway-role-not-configured]" in str(exc)
