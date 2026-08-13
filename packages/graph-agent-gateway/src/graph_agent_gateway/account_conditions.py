"""The words providers use for conditions that are true of the account.

A balance and a key are properties of the account behind an endpoint, not of
the request that happened to hit them: they answer the same way for every model
and every prompt. Two places in this package have to recognise them — the probe
judge, deciding what an answer settled, and the runtime classifier, deciding
whether the next route deserves a try — and both used to carry their own copy of
the wording, which is how the same message came to mean different things
depending on which one read it.

What makes these two conditions one vocabulary rather than a grab bag: neither
of them is about the request. That is also the boundary — "this model does not
take images" and "this parameter is unknown" are about the request, they answer
differently for the next model or the next call, and they stay with whichever
consumer needs them.

The markers grow from wording observed on real providers. HTTP status codes are
the reason this file exists at all: the conventional codes (401 for a key, 402 /
403 for a balance) are a convention providers are free to ignore, and they do —
Anthropic answers an exhausted balance with HTTP 400, Google answers a rejected
key with HTTP 400 — so the body is the only place left where the condition is
stated.
"""

from __future__ import annotations

from typing import Final

BILLING_MARKERS: Final[tuple[str, ...]] = (
    "credit balance",
    "insufficient balance",
    "insufficient credit",
    "insufficient funds",
    "insufficient quota",
    "insufficient_quota",
    "purchase credits",
    "quota exceeded",
    "billing",
)
"""An account that cannot pay for the call.

Live: Anthropic answers HTTP 400 `invalid_request_error`, "Your credit balance
is too low to access the Anthropic API." — where the convention would be 402.
Both spellings of the quota marker are kept on purpose: one consumer reads a
provider's `code` field (`insufficient_quota`), the other reads prose.
"""

CREDENTIAL_MARKERS: Final[tuple[str, ...]] = (
    "api key not valid",
    "api_key_invalid",
)
"""A key the provider will not accept.

Live 2026-08-12, gemini-official × gemini-3.5-flash: HTTP 400 INVALID_ARGUMENT,
message "API key not valid. Please pass a valid API key.", and
`details[0].reason` = `API_KEY_INVALID` — where DeepSeek answers the same
situation with HTTP 401 on the same day. Both spellings are here because the
two are different fields, not synonyms: the identifier is what a provider means
for a program to read, the sentence is what it wrote for a person.
"""


def says_any(text: str, markers: tuple[str, ...]) -> bool:
    """Whether an already-lowercased error text contains any of these markers.

    Each caller assembles the text from whatever it holds — a parsed JSON body,
    or the two fields an exception carried — because those really are different
    inputs. What must not differ is the vocabulary they are tested against.
    """

    return any(marker in text for marker in markers)
