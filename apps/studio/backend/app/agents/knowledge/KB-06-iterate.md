---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-02-io-dataflow
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §7

# KB-06: Iterate Loops & Batches

The `iterate` block defines loop and batch behaviors. It can be declared globally in `GRAPH.md` (`[[KB-01-skill-anatomy]]`) to run the entire skill iteratively, or locally in any phase frontmatter (`LOGIC.md`, `SUBGRAPH.md`, or `SKILL.md`) to run a single phase node iteratively.

*Note: The fields `batch:` and `iterator:` are obsolete and prohibited.*

## 1. Batch Mode (Parallel Map)
Batch mode executes parallel operations over an array field.

```yaml
# Example: Batch iteration in frontmatter
iterate:
  mode: batch
  over: chapters
  item_var: chapter
  range: [0, 9] # Optional: 0-indexed slice limits (inclusive)
  concurrency: 4 # Optional: Maximum parallel cycles
```

### Batch Fields:
*   `mode`: Must be `"batch"`.
*   `over`: The blackboard array field path to iterate over (`[[KB-02-io-dataflow]]`).
*   `item_var`: The variable name of the current array item injected into the local blackboard slice.
*   `range`: A list of two integers representing the slice interval (e.g., `[1, 10]`).
*   `concurrency`: Integer >= 1. Limits parallel threads.

## 2. Loop Mode (Serial Accumulation)
Loop mode executes serial iterations where each step depends on or accumulates data from the previous steps.

```yaml
# Example: Loop iteration with accumulator in frontmatter
iterate:
  mode: loop
  over: paragraphs
  item_var: paragraph
  accumulate:
    var: collected_summaries
    init: []
    from: summary
    merge: append
```

### Loop Fields:
*   `mode`: Must be `"loop"`.
*   `over` / `item_var` / `range`: Same as Batch mode.
*   `accumulate`: Required block specifying state accumulation.

### Accumulate Fields:
*   `var`: The variable name for the accumulated state injected into the local blackboard.
*   `init`: The initial value (e.g., `[]`, `{}`, `""`, `0`).
*   `from`: The name of the phase output field from which the incremental value is collected.
*   `merge`: The merge strategy. Supported values are:
    *   `append`: Appends the increment value to an array.
    *   `extend`: Extends the array with another array.
    *   `merge`: Merges two dictionaries.
    *   `replace`: Overwrites the accumulator value with the latest output value.

## 3. Strict Compile Constraints
*   **Item Variable Presence**: All iterate definitions must contain `item_var`.
*   **Accumulator Presence**: Loop mode must contain `accumulate` with a defined `accumulate.var`.
*   **Target Validity**: The `over` path must resolve to a valid array-type field on the blackboard at compilation time.
