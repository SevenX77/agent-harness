"""Studio's side of model naming: hand the gateway the label the user typed.

The naming rules themselves belong to the gateway and are tested there
(``packages/graph-agent-gateway/tests/test_model_naming.py``). What Studio still
owns is the seam: ``display_name`` is a Studio-only field, so the gateway asks
for it as ``provider_label``. Forgetting to pass it raises nothing — the brand
inference just quietly loses a clue — so the seam is guarded here by reading the
call sites rather than by hoping someone notices.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.adapters.gateway import project_model_group_identity, project_model_identity
from app.models.llm_config import ProviderEndpoint, ProviderRoute

_NAMING_FUNCTIONS = {"project_model_identity", "project_model_group_identity"}
_BACKEND_APP = Path(__file__).resolve().parents[2] / "app"


def _call_sites() -> list[tuple[Path, ast.Call]]:
    sites: list[tuple[Path, ast.Call]] = []
    for path in _BACKEND_APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _NAMING_FUNCTIONS
            ):
                sites.append((path, node))
    return sites


def test_every_studio_call_hands_over_the_label_the_user_typed() -> None:
    sites = _call_sites()

    assert sites, "no naming call sites found — did the import style change?"
    missing = [
        f"{path.name}:{node.lineno}"
        for path, node in sites
        if not any(keyword.arg == "provider_label" for keyword in node.keywords)
    ]

    assert not missing, f"call sites drop the endpoint's display_name: {missing}"


def test_the_label_studio_passes_is_the_one_that_reaches_the_projection() -> None:
    """A model id with no brand of its own is named by the provider's label."""

    route = ProviderRoute(
        route_id="provider:large-2411",
        endpoint_id="provider",
        route_slug="large-2411",
        provider_model_id="large-2411",
    )
    endpoint = ProviderEndpoint(
        endpoint_id="provider",
        display_name="Mistral Cloud",
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
    )

    identity = project_model_identity(
        route=route, endpoint=endpoint, provider_label=endpoint.display_name
    )
    group = project_model_group_identity(
        route=route, endpoint=endpoint, provider_label=endpoint.display_name
    )

    assert identity.section_label == "mistral"
    assert group.section_label == "mistral"


def test_studio_keeps_no_vendor_chain_of_its_own() -> None:
    """"Who made this model" is answered once, in the gateway.

    Studio used to keep a second copy of the vendor if-chain
    (``_section_label_from_display_name``, applied OVER the gateway's answer)
    plus an equal-weight majority vote (``_dominant_section_label``) that let
    two endpoint guesses outvote one declared vendor. Both are replaced by the
    gateway's ``elect_model_group_section``. Decision record:
    docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md 决策二.
    """

    source = (_BACKEND_APP / "routers" / "llm.py").read_text(encoding="utf-8")

    assert "_section_label_from_display_name" not in source
    assert "_dominant_section_label" not in source
    assert "elect_model_group_section(" in source
