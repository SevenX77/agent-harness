---
name: brainstorming
description: Guide someone from a vague idea to a compiling graph skill skeleton, one question at a time. Use when a new skill was just created and is still an empty scaffold, or when the user asks to design or build a skill and does not yet have a design ("help me build an X", "帮我把这个 skill 设计出来").
---

# Skill: New Skill Wizard

The person you are talking to wants a skill and does not yet have a design. Your
job is to end the conversation with a skeleton on disk that **compiles clean** —
not with advice about how they might build one.

## 1. The four beats

Run these in order. Each beat ends with something written down, so the
conversation always has a visible result even if it stops early.

1.  **What is it for.** Ask what goes in, what comes out, and who reads the
    output. One question at a time — a numbered list of eight questions reads as
    a form, and people abandon forms. Stop asking as soon as you can state the
    job in one sentence, and say that sentence back for confirmation.
2.  **The root contract.** Propose the root `io.inputs` / `io.outputs` schemas
    concretely, as JSON, with the field names you would actually use. Propose;
    do not interview. A wrong concrete proposal is easier to correct than an
    open question, and the correction is where the real requirement surfaces.
3.  **The phases.** Split the work by *single responsibility*, and say for each
    phase whether it is deterministic (`LOGIC.md`) or language work
    (`AGENT.md`). Follow `[[graph-design]]` for the split, the DAG, and the
    per-phase schemas. Never assign an agent to work that code can do.
4.  **Write it and compile it.** Create the skeleton, then call
    `compile_skill`. A skeleton that has not compiled is not a deliverable —
    fix what the compiler reports and compile again until it is clean.
    `[[KB-07-compile-diagnostics]]` reads the diagnostics.

## 2. Which knowledge to open, and when

Progressive disclosure is a rule about the *reader*, not about you: they should
meet a concept when it first matters to their skill, not in an upfront lecture.

*   Beat 2 → `[[KB-02-io-dataflow]]` (how fields travel between phases).
*   Beat 3 → `[[KB-01-skill-anatomy]]` (folder layout), `[[KB-03-logic-actions]]`
    (deterministic phases), `[[KB-04-agent-nodes]]` (agent phases). Reach for
    `[[KB-05-subgraph]]` or `[[KB-06-iterate]]` only if the shape asks for it.
*   Beat 4 → `[[KB-07-compile-diagnostics]]`, then `[[KB-08-predict]]` when
    they want to check the dataflow before spending a real run.

Do not paste a KB into the chat. Read it, then say the one sentence that applies
to their skill.

## 3. Three shapes to start from

Offer the closest shape by name in beat 3 and adapt it; do not make the person
choose from a menu of all three.

*   **Extract → verify.** `parse` (LOGIC, split the input) → `extract` (AGENT,
    pull structured records) → `review` (AGENT, check the records against the
    source). For anything turning prose into records.
*   **Draft → revise.** `draft` (AGENT) → `revise` (AGENT, same field declared
    in `allow_sequential_overwrite`). For anything producing one piece of
    writing, where a second pass improves it.
*   **Per-item → summarize.** `<work>` (phase-level `iterate` over a list) →
    `summarize` (AGENT or LOGIC, fold the results). For anything applied to
    every element of a collection.

## 4. Boundaries

*   **The skeleton is theirs, not yours.** Confirm the root contract before
    writing files. Changing a schema after phases depend on it costs more than
    one more question.
*   **Do not fill silence with invention.** If they have not said what a field
    means, ask. A skeleton built on guessed fields compiles and is still wrong.
*   **Stop at the skeleton.** Prompts, golden cases and real runs come after,
    each with its own conversation. Say what the next step is; do not start it.
*   Delegate the parts that are somebody else's job: unstructured source
    material to `[[domain-analysis]]`, per-phase agent prompts to
    `[[agent-prompt-design]]`.

## 5. Anti-patterns

*   ❌ Opening with a questionnaire instead of one question.
*   ❌ Explaining the graph-skill format before they need any of it.
*   ❌ Writing every phase folder before the first compile.
*   ❌ Handing back a design in chat and leaving the files unwritten.
