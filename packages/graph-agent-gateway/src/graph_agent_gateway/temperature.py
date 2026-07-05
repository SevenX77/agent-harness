"""Temperature scale policy for gateway runtime calls."""

from __future__ import annotations

AUTHORED_TEMPERATURE_MAX = 2.0

_PROVIDER_TEMPERATURE_MAX_BY_PROTOCOL = {
    "anthropic_compatible": 1.0,
    "openai_compatible": 2.0,
    "ark_runtime": 2.0,
    "google_genai": 2.0,
    "wavespeed_any_llm": 2.0,
}


def provider_temperature_from_authored(
    temperature: float | int | None,
    protocol: str,
) -> float | None:
    """Map Studio's authored 0..2 temperature onto a provider protocol scale."""

    if temperature is None:
        return None
    provider_max = _PROVIDER_TEMPERATURE_MAX_BY_PROTOCOL.get(
        protocol,
        AUTHORED_TEMPERATURE_MAX,
    )
    return float(temperature) * provider_max / AUTHORED_TEMPERATURE_MAX
