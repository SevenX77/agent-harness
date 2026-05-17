# V2.1 Final Cutover PR Meta Draft

Copy this into the T3.3 final PR body after T2.2/T2.10 decisions are closed.

## Freeze Notice

V2.1 is a hard cutover for graph-agent skills. During the merge window:

- Pause frontend single-file skill editing APIs. Directory-based V2.1 authoring
  is the source of truth.
- Keep template APIs on the legacy path until the follow-up Studio editor work
  lands.
- Treat Studio preview as read-mostly for migrated skills.
- Recommended freeze window: 2 hours before merge through 4 hours after deploy.
- Notify PM, skill owners, Studio owners, and on-call before merge.

Suggested notice:

> V2.1 graph-agent cutover is entering freeze. Skill edits and template changes
> are paused until validation completes. Existing runs may continue; new changes
> require cutover owner approval.

## Acceptance Checklist

1. `skills/hello-world` compiles and assembles.
2. `skills/producer` compiles and assembles.
3. `skills/text-segmentation` compiles and assembles.
4. `skills/event-extraction` compiles and assembles.
5. `skills/batch-analysis` compiles and assembles.
6. `skills/global-synthesis` compiles and assembles.
7. `skills/product-manual` compiles and assembles.
8. `skills/examples/subgraph-sample/story-deconstruction` compiles and assembles.
9. No source under `skills/_v2_pending` is included in final smoke.
10. Root `SKILL.md` schema 2.0 paths are blocked by V2.1 loader tests.
11. `depends_on` is required in `GraphPhaseRef` Pydantic schema.
12. First phase entries declare `depends_on=""` explicitly.
13. Backend skill detail includes `graph_topology`.
14. Backend skill detail includes V2.1 node schema.
15. Backend V2.1 node schema exposes `graph_phase_ref.required.depends_on`.
16. Backend IO schema preview returns inputs and outputs.
17. Studio single-file create/update endpoints reject V2.1 directory edits.
18. Template API legacy behavior is called out as deferred.
19. Tier 1 shadow comparator runs and uploads JSON diff reports.
20. All-skills smoke compiles and assembles every current V2.1 graph.
21. Graph-agent V2.1 tests pass.
22. Studio backend tests pass with known xfail documented.
23. Rollback owner has rehearsed single-skill and full-branch rollback commands.

Validation commands:

```bash
pytest packages/graph-agent/tests/tools/test_dual_run_shadow.py packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q
pytest packages/graph-agent/tests/core/test_v21_loader.py packages/graph-agent/tests/core/test_v21_ast_schema.py -q
.venv/bin/python -m pytest apps/studio/backend/tests -q -x
```

## Rollback Runbook

Full rollback:

1. Revert the T3.x feature branch merge commit.
2. Revert backend cutover commits that route `compile_skill` and `run_skill` to
   the V2.1 root.
3. Restore schema 2.0 root `SKILL.md` imports and any frontend calls that still
   require single-file editing.
4. Run backend tests and legacy graph-agent smoke before redeploy.
5. Announce freeze lift only after compile/run error rates return to baseline.

Single-skill rollback:

Use `docs/graph_agent_docs/V21_ROLLBACK_SOP.md`.
