# Bad samples

This directory is reserved for skill shapes we explicitly want the
compiler (and Studio) to flag as anti-patterns.

The first batch lands under Task 8.1 once the legacy
`skills/story-deconstruction/` orchestrator has been migrated off by
all in-repo callers. Candidates:

* `story-deconstruction-python-glue/` — the old
  `tools: [script.orchestrator.*]` dispatcher pattern that the new
  subgraph-composed version under
  `skills/examples/subgraph-sample/story-deconstruction/` replaces
  (Task 8.2).

Until then this directory stays empty so Task 5.6
(`bad-samples/` compiler test suite) has a stable location to grow
into.
