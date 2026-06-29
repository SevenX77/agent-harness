// Validator file authoring helper (a single sibling file per phase).
//
// Ground truth (docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md §1 + engine
// validator_contract.py): when a phase declares `validator: true`, the engine runs
// the sibling `phases/<phase_id>/validator.py`, whose entrypoint is
// `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict` — return
// None to pass, or a dict of errors to reject. Studio creates the file from a
// passing stub; the same file/flag mechanism is shared by all three phase kinds.

/** `phases/<phaseId>/validator.py` — the sibling file backing a phase validator. */
export function validatorFilePath(phaseId: string): string {
  return `phases/${phaseId}/validator.py`
}

/**
 * Load-safe stub for a new validator file: exports `validate` with the engine
 * signature and passes by default (returns None), so creating it never fails
 * compile or rejects output until the author fills in real rules.
 */
export function validatorStubContent(): string {
  return [
    "from __future__ import annotations",
    "",
    "",
    "def validate(output: dict, state_slice: dict, **kwargs) -> None | dict:",
    '    """TODO: validate this phase\'s output.',
    "",
    "    Return None to pass, or a dict describing what failed to reject the output",
    "    (rejection is routed back to an agent as retry feedback, or fails compile",
    "    for logic / subgraph phases).",
    '    """',
    "    return None",
    "",
  ].join("\n")
}
