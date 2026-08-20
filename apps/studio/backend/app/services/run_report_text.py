"""How the run report prints one message it did not write.

Provider errors, engine violations and validator complaints all arrive as
someone else's text: any length, any newlines, any punctuation. The report
prints them so a reader can recognise which failure this was — not so they can
read it in full, which is what `trace.jsonl` is for and what the report already
links to.

There is one rule and it lives here, because the report leaked it three
different ways before: the Failure section clipped a `message` but not the
`errors` list beside it, the Routes table printed a decision's reason whole,
and the unmet-settings table printed the same reason whole a second time.

Design: `docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md`
RUN_EXECUTION-9.
"""

from __future__ import annotations

#: How much of one message the report prints. RUN_EXECUTION-9 fixes this at 200
#: characters: a measured `protocol_violation` ran to several thousand, and
#: printing it whole pushed every other failure in the same section off screen.
MESSAGE_BUDGET = 200


def one_line(text: str) -> str:
    """Enough of a message to recognise it, on a single line.

    Collapsing whitespace is not cosmetic: the report is markdown, where a
    newline inside a bullet or a table row ends that row, so a message
    containing one does not merely look untidy — it truncates the structure
    around it and takes the rest of the line with it.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= MESSAGE_BUDGET:
        return collapsed
    return collapsed[:MESSAGE_BUDGET].rstrip() + "…"


def table_cell(text: str) -> str:
    """`one_line`, plus the escaping a cell needs to stay one cell.

    A markdown row is delimited by ``|``. A provider message that happens to
    contain one silently splits the row into extra columns, so every later cell
    in that row shifts under the wrong heading — a table that is quietly wrong
    is worse than one that is obviously truncated.
    """
    return one_line(text).replace("|", r"\|")


__all__ = ["MESSAGE_BUDGET", "one_line", "table_cell"]
