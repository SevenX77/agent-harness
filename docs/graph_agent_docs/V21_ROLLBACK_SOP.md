# V2.1 Single Skill Rollback SOP

This SOP covers a rollback for one migrated V2.1 skill while the wider V2.1
branch remains active.

## Steps

1. Identify the skill name, owner, production callers, recent deploy SHA, and
   affected paths. Example: `skills/text-segmentation`.
2. Revert only that skill's migration content. Prefer `git revert <skill
   migration commit>`. If the migration was bundled, restore the path with
   `git checkout main -- skills/<skill>/` and commit the rollback explicitly.
3. Run the shadow comparator before merge:
   `python packages/graph-agent/tools/dual_run_shadow.py skills/<skill> --mode idempotency --input-file /tmp/input.json`.
   For legacy schema 2.0 restoration, use the archived schema 2.0 fixture or
   the pre-migration commit as the reference and attach the JSON report.
4. Apply the Studio backend fallback decision. During mixed V2.1/schema 2.0
   rollback windows either disable that skill in Studio, or redeploy backend
   support for both root forms. If neither is ready, stop serving the skill and
   redeploy after the rollback commit lands.
5. Monitor the skill for at least one release window: compile error rate, run
   error rate, P95 latency, finish-task validation failures, and user-visible
   4xx/5xx responses. Page when error rate exceeds 2 percent for 10 minutes or
   any compile failure recurs after rollback.

## CI Workflow Sample

Do not commit this sample as part of prep. T3.3 final can turn it into a real
workflow after the cutover owner approves the rollback gate.

```yaml
name: rollback-skill

on:
  workflow_dispatch:
    inputs:
      skill:
        description: Skill directory under skills/
        required: true
      ref:
        description: Candidate rollback ref
        required: true
  pull_request:
    paths:
      - "skills/**"
      - "packages/graph-agent/**"

jobs:
  validate-rollback:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.ref || github.sha }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e "packages/graph-agent[dev]"
      - run: pytest -m "tier1 or smoke" packages/graph-agent/tests/tools packages/graph-agent/tests/e2e/test_v21_all_skills_smoke.py -q
      - run: python packages/graph-agent/tools/dual_run_shadow.py "skills/${{ inputs.skill }}" --mode idempotency --input-json "{}" --output shadow.json
      - uses: actions/upload-artifact@v4
        with:
          name: rollback-shadow-report
          path: shadow.json
```
