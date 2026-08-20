"""Two handlers on one address means one of them is dead, silently.

Field evidence (2026-08-20). ``routers/runs.py`` registered
``POST /api/skills/{skill_id}/runs/{base_run_id}/compare`` (launch node-compare
side-runs) and ``routers/compare.py`` registered
``POST /api/skills/{skill_id}/runs/{run_id}/compare`` (diff a run against its
golden). ``main.py`` includes ``runs`` first, so Starlette matched it first and
the golden endpoint could never be reached — no error at import, no warning at
startup, nothing in the OpenAPI schema to look at twice. It went unnoticed
because the frontend happened to use the GET variant.

The gate is stated as the rule rather than as "these two must not collide",
because the next collision will be between a different pair. A duplicate is
also the visible half of a naming problem: when one address means two unrelated
things, whichever handler loses is not a bug to be reordered around — the two
resources needed distinct names in the first place.
"""

from __future__ import annotations

import re
from collections import Counter

from app.main import create_app
from fastapi.routing import APIRoute

#: Methods FastAPI adds on its own, which are not part of a handler's identity.
_IMPLICIT_METHODS = frozenset({"HEAD", "OPTIONS"})

#: A path parameter, whatever it is called.
_PARAMETER = re.compile(r"\{[^}]*\}")


def _address_of(path: str) -> str:
    """The URL space a path claims, which is what a request is matched against.

    Two paths that differ only in what they NAME their parameters —
    ``/runs/{run_id}/compare`` and ``/runs/{base_run_id}/compare`` — claim the
    exact same addresses, and Starlette resolves both to whichever was
    registered first. Comparing the literal strings would call them different
    and miss precisely the collision this gate exists to catch.
    """
    return _PARAMETER.sub("{}", path)


def _declared_routes() -> list[tuple[str, str, str]]:
    """Every (method, address, endpoint name) the app actually registers."""
    declared: list[tuple[str, str, str]] = []
    app = create_app()
    for mounted in [app, *(route.app for route in app.routes if hasattr(route, "app"))]:
        for route in getattr(mounted, "routes", []):
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(set(route.methods or ()) - _IMPLICIT_METHODS):
                declared.append((method, _address_of(route.path), route.name))
    return declared


def test_a_path_parameter_name_does_not_change_the_address() -> None:
    assert _address_of("/api/skills/{skill_id}/runs/{run_id}/compare") == _address_of(
        "/api/skills/{skill_id}/runs/{base_run_id}/compare"
    )
    assert _address_of("/api/skills/{skill_id}/runs/compare/{group_id}") != _address_of(
        "/api/skills/{skill_id}/runs/{run_id}/compare"
    )


def test_no_two_handlers_answer_the_same_address() -> None:
    declared = _declared_routes()
    assert declared, "no routes were collected; the fixture would pass on an empty app"

    seen = Counter((method, path) for method, path, _ in declared)
    duplicated = {address for address, count in seen.items() if count > 1}

    collisions = {
        address: sorted(name for method, path, name in declared if (method, path) == address)
        for address in duplicated
    }
    assert not collisions, (
        "these addresses are registered more than once, so all but the first "
        f"handler are unreachable: {collisions}"
    )
