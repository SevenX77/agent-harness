"""One cheap question, asked before the expensive one.

A route can refuse a request over a single setting. Finding that out from the
real call means paying for the whole request first — and on a long task, two
minutes of work before the failure lands. So before the call goes out, the same
request is sent asking for one token: same builder, same settings, same route.

A refusal here is not a route that is down. It is a question with a follow-up:
ask again with the preferences dropped, and if that answers, ask once per
preference to find out which one the route will not take. Only then is there
anything to say about the settings, and it is said before the long call starts
rather than after it dies.

What this cannot do is notice a setting that was accepted and then ignored —
one token is not enough answer to observe that. That verdict belongs to the
moment the real answer closes (decision doc D5).

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from graph_agent_gateway.call_settings import CallSettings
from graph_agent_gateway.registry import ResolvedRoute
from graph_agent_gateway.resolve import classify_exception
from graph_agent_gateway.route_chat_model_factory import provider_request_keys

logger = logging.getLogger(__name__)

# Short enough to cost nothing, non-empty because some providers reject a blank
# turn before they ever look at the settings under test.
_QUESTION: Sequence[BaseMessage] = (HumanMessage(content="."),)


@dataclass(frozen=True)
class ProbeVerdict:
    """What the cheap question established about this call's settings.

    ``answers_without_them`` is the whole point: it says the route is willing to
    do the work, so a refusal is about the request rather than the route.
    ``refused`` names the preferences to leave off, empty when the route took
    everything — or when the route refuses regardless, which is not the
    settings' fault and is left to the caller's own failure handling.

    ``refusal`` is the provider's own exception, kept rather than flattened to
    a string: what to do about a route that refuses regardless is a question
    only the caller's error classification can answer.
    """

    answers_without_them: bool
    refused: tuple[str, ...]
    refusal: BaseException | None = None


def build_probe_model(
    route: ResolvedRoute,
    settings: CallSettings,
    *,
    factory: Any,
    timeout_seconds: float | None = None,
) -> BaseChatModel:
    """The chat model the probe asks with — built exactly like the call's.

    The builder is handed in rather than made here: the probe and the call it
    precedes have to come off the same one, or the probe is again asking about
    a request nobody is going to send.
    """
    built: BaseChatModel = factory.build(
        route,
        timeout_seconds=timeout_seconds,
        **settings.as_cheap_question().build_kwargs(),
    )
    return built


def probe_call_settings(
    route: ResolvedRoute,
    settings: CallSettings,
    *,
    factory: Any,
    timeout_seconds: float | None = None,
) -> ProbeVerdict:
    """Ask the route whether it takes this call's settings, for one token.

    ``timeout_seconds`` is the policy's probe timeout: a question asked to save
    a long call must not itself be allowed to take as long as one.
    """
    refusal = _ask(route, settings.as_cheap_question(), factory, timeout_seconds)
    if refusal is None:
        return ProbeVerdict(answers_without_them=True, refused=())

    if classify_exception(refusal, route_id=route.route_id).scope != "request":
        # The provider never got as far as reading this request — a credential,
        # a missing model, a busy endpoint. Asking again with fewer settings
        # would spend a second question on a route that has not objected to any
        # of them.
        return ProbeVerdict(answers_without_them=False, refused=(), refusal=refusal)

    # The route refuses either way, so the settings are not what is wrong with
    # this request, and the caller's own route handling has to decide.
    refuses_regardless = not settings.preference_names or (
        _ask(route, settings.without_preferences().as_cheap_question(), factory, timeout_seconds) is not None
    )
    if refuses_regardless:
        return ProbeVerdict(answers_without_them=False, refused=(), refusal=refusal)

    # Only settings that reach this protocol's request are worth a question:
    # one that has no place in the body would be asked about in a request
    # identical to the one just accepted, and answered the same way.
    carried = provider_request_keys(str(route.protocol))
    refused = tuple(
        name
        for name in settings.preference_names
        if name in carried
        and _ask(route, settings.as_cheap_question(about=name), factory, timeout_seconds) is not None
    )
    return ProbeVerdict(answers_without_them=True, refused=refused, refusal=refusal)


def _ask(
    route: ResolvedRoute,
    question: CallSettings,
    factory: Any,
    timeout_seconds: float | None,
) -> BaseException | None:
    """Send one question; hand back what refused it, or nothing."""
    model = factory.build(route, timeout_seconds=timeout_seconds, **question.build_kwargs())
    try:
        for _ in model.stream(list(_QUESTION)):
            break
    except Exception as exc:  # noqa: BLE001 - the refusal is the answer
        logger.info(
            "phase=settings_probe action=refused route=%s settings=%s error=%s",
            route.route_id,
            ",".join(question.preference_names) or "<none>",
            str(exc)[:300],
        )
        return exc
    return None
