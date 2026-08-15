---
name: agent-prompt-design
description: Author and repair agent-phase SKILL.md prompts — which body tag owns which content, brevity discipline for role/goal, protocols as the single rule authority, and the anti-patterns that corrupt the runtime template.
---

# Skill: Agent Node Prompt Design (SKILL.md authoring)

This skill defines how to write the body of an agent phase `SKILL.md`. Field
grammar and structure live in `[[KB-04-agent-nodes]]`; this skill covers what
CONTENT belongs in each tag and why.

## 1. Where your words actually go (the nested runtime template)

At runtime the engine composes the final system prompt from a fixed cognitive
template (engine `graph_agent/cognitive/prompt.py`). Your SKILL.md body fills
ONLY the business slots; the framework injects all execution discipline around
them. Never restate what the framework already injects.

| You write (SKILL.md) | Runtime slot it lands in | Your job there |
| --- | --- | --- |
| body `<role>` | `<role>` | business persona, one sentence |
| body `<goal>` | `<goal>` | outcome definition + input meanings, one short block |
| body `<step id="Sn" name="...">` | suggested-steps list inside `<thinking_style>` | ordered procedure (advisory) |
| body `<protocol id="Pn">` | rule list inside `<protocol_citation>` | binding rules the model must cite as `[protocol:Pn]` |
| body `<example id="...">` | `<examples>` | business-logic comprehension aids |
| frontmatter `references` | `<knowledge_base>` | pre-read material + `read_reference` registry |
| frontmatter `io.outputs` | `<exit_contract>` (auto-generated) | THE single output-format authority |

Framework-owned slots you must NOT duplicate in the body: thinking style,
ambiguity feedback (the `log_ambiguity` loop), protocol-citation mechanics,
`finish_task` reminders, and the exit contract. Writing "think before acting"
or "you must call finish_task with ..." in the body is noise at best and a
contradiction at worst.

## 2. Slot duties and brevity discipline

*   **`<role>` — exactly one sentence.** Who the agent is in the business
    domain. No procedure, no rules, no backstory.
*   **`<goal>` — one short block.** What outcome counts as done, plus one line
    per input variable explaining what it is for. **Hard rule: no steps, no
    classification criteria, no judgment rules in `<goal>`.** If you are
    writing "how", it belongs in `<step>`; if you are writing "must / never",
    it belongs in `<protocol>`. A `<goal>` that keeps growing is the most
    common way iterative edits rot a prompt.
*   **`<step>` — procedure only.** One action per step, in execution order.
    Steps reference rules, they do not restate them: write "classify each span
    per [protocol:P1]", not a second copy of the P1 definition. A rule defined
    in both a step and a protocol WILL diverge under future edits.
*   **`<protocol>` — the single authority for every business rule.** Atomic
    (one rule, one id), binding, citable. When a rule needs teaching material
    to be applied correctly (criteria expansions, easy-to-misjudge
    counter-examples), that teaching text is part of the rule — keep it in the
    protocol or in a registered reference; deleting it changes model behavior.
*   **`<example>` — business comprehension only.** Boundary cases, tricky
    classifications, worked judgments. **Never an output-format mold**: the
    runtime template explicitly instructs the model not to copy example
    structure, and the format authority is `io.outputs` → `<exit_contract>`.
    An example whose content is "the finish_task arguments must look like this
    JSON" is a defect — it competes with the exit contract, and when the two
    drift apart the prompt contradicts itself.

## 3. Output contract and validator layering

*   `io.outputs` declares the fields the agent itself must author via
    `finish_task`. Steps and examples must agree with it — never instruct the
    model to submit a subset or superset of the declared required fields.
    **Check this mechanically, do not eyeball it**: write down
    `io.outputs.required`, write down every output field the body names, and
    require the two lists to be equal. A body that names one field while
    `required` declares four is the common shape, and it survives review
    because each half reads perfectly on its own — the contradiction exists
    only between them, and the model meets it as a rendered `<exit_contract>`
    demanding four fields under a `<goal>` that asked for one.
*   Do not hand-write format instructions in the body; the exit contract
    renders the schema. (`<exit_contract>` in the body is forbidden by spec.)
*   `validator.py` (`validator: true`) is for shape only: types, enums,
    ranges, index continuity, and mechanical enrichment per the runtime
    contract in `[[KB-03-logic-actions]]`. Semantic quality judgment — "is this
    output GOOD" — belongs to a review agent phase and golden evaluation
    (`[[KB-10-golden]]`), never to the validator. Any validator assertion that a
    predict stub cannot satisfy but a real output can (or vice versa) is a
    layering bug, not a strictness feature.

## 4. Golden alignment

*   Design the prompt so its outputs are easy to evaluate. Prefer structured /
    enumerated outputs over free-text fields (`[[KB-10-golden]]`).
*   Restrict variance with structured fields rather than prose exhortations.

## 5. Iteration loop

*   Use actual blackboard input payloads to test predictions
    (`[[KB-08-predict]]`).
*   Modify only one prompt instruction or output key at a time, testing the
    impact before making further changes.
*   Encode a failed case's correction into the slot that owns it: a
    misjudgment becomes a protocol refinement or a boundary example — never a
    patch sentence appended to `<goal>`.

## 6. Anti-pattern checklist

*   ❌ **Goal stuffing**: steps, criteria, or rule text accumulated in
    `<goal>`. Symptom: `<goal>` longer than a short paragraph.
*   ❌ **Format-mold examples**: an `<example>` that exists to show the
    finish_task payload shape.
*   ❌ **Rule duplication**: the same business rule stated in a step and a
    protocol (or in two protocols).
*   ❌ **Framework restatement**: thinking / finish_task / ambiguity
    discipline rewritten in the body.
*   ❌ **Hand-written `<exit_contract>` or wrapper tags** (`<steps>`,
    `<protocols>`, `<examples>`) — forbidden by spec.
*   ❌ **Semantic assertions in validator.py** (exact line counts, quality
    thresholds on real content) — they belong to review prompts and golden.
*   ❌ **Putting input payload content in the body — pasted OR expanded.**
    The engine already hands the model the phase's entire declared input slice
    as a JSON message on the first turn (`[[KB-02-io-dataflow]]` §2), so a
    `{some_input}` reference written in `<goal>` is not "how the data gets
    there" — it is a SECOND full copy of a value the model already has. Name
    the variable and say what it is for; never expand it. Expanding a large
    field (a chapter, a document, a transcript) also splits the sentence it
    sits in: the reader — and the model — meets the verb, then thousands of
    characters of payload, then finally the object it was supposed to act on.
*   ❌ **Conversational filler** that does not change model output behavior.
