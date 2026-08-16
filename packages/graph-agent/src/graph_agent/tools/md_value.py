"""How a Markdown value that is declared to be a list gets read.

``finish_task(business_data_md=...)`` is Markdown whose values are plain text,
so a list has to be recognised from the way it is written. Three parsers need
that judgement — ``tools/md_to_json.parse_md`` (the phase output parser),
``tools/dynamic_schema`` (``<output_example>`` field defaults) and
``cognitive/md2json`` (the finish_task tool) — and this module is the single
place where it is decided.

The rule, in order:

1. A value that **announces structure** — a fenced block, or text that both
   opens and closes as a JSON literal — is read as JSON.
2. Anything else is a comma-separated list, which is the shape the exit
   contract teaches (``cognitive/prompt.py`` renders ``- <field>: <值>``).
3. A value that announced structure and then failed to parse is returned
   **unchanged**. It is never downgraded into comma-separated fragments.

Rule 3 is the whole point. Splitting ``["a", "b", "c"]`` on commas yields
``['["a"', '"b"', '"c"]']`` — three strings that satisfy a ``list[str]`` schema
perfectly while meaning nothing, so validation waves them through and the
damage surfaces much later, or never. Returning the text intact makes schema
validation say "this is not a list", which is a correction the agent can act on.

Borrowed from YAML 1.2 (§7.3.3, plain scalars may not begin with the flow
indicators ``[`` ``{``): brackets at the edges are a *structure indicator*, and
a malformed flow collection is an error rather than a lenient scalar. Rejected
from it: YAML forbids commas in plain scalars outright and requires quoting,
which would break the comma form this engine actively teaches its models; and
YAML raises, while here the producer is an LLM whose only feedback channel is
the schema-validation diagnostic loop — ``parse_md`` is documented as never
raising — so an unreadable value is handed to validation instead.

Borrowed from ``json.loads``: parsing is all-or-nothing, never a best-effort
fragment.
"""

from __future__ import annotations

import json
from typing import Any

_JSON_OPENERS = ("[", "{")
_JSON_CLOSERS = ("]", "}")
_FENCE = "```"


def strip_outer_fence(value: str) -> str:
    """Return the payload of a closed ``` fence, or the value unchanged."""
    stripped = value.strip()
    if not stripped.startswith(_FENCE):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == _FENCE:
        return "\n".join(lines[1:-1]).strip()
    return stripped


def looks_like_json_literal(value: str) -> bool:
    """True when the value opens with ``[``/``{`` and closes with ``]``/``}``.

    Requiring a delimiter at BOTH ends is deliberate. Triggering on the opening
    bracket alone would misread values that are genuinely comma-separated but
    whose first item happens to be bracketed, such as ``[a](u1), [b](u2)``.

    The two ends are not required to match: ``[1, 2}`` announces structure just
    as loudly as ``[1, 2]`` does, and it is malformed, so it must reach the
    refusal path rather than be split into ``['[1', '2}']``.
    """
    stripped = strip_outer_fence(value)
    return stripped.startswith(_JSON_OPENERS) and stripped.endswith(_JSON_CLOSERS)


def parse_list_value(raw: str) -> Any:
    """Read one Markdown value that the schema declares to be a list.

    Returns the parsed JSON when the value announced structure, the comma-split
    list when it is plain text, and the ORIGINAL text when structure was
    announced but could not be parsed — see this module's docstring for why the
    last case must not fall back to comma splitting.
    """
    value = raw.strip()
    if value.startswith(_FENCE) or looks_like_json_literal(value):
        try:
            return json.loads(strip_outer_fence(value))
        except json.JSONDecodeError:
            return value
    return [part.strip() for part in value.split(",") if part.strip()]


__all__ = ["looks_like_json_literal", "parse_list_value", "strip_outer_fence"]
