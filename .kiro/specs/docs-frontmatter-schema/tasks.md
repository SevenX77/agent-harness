# Tasks: Docs Frontmatter Schema

## T1. Write frontmatter Pydantic model

- Owner: a1
- Target file:
  - `tools/docs_frontmatter_validator.py`
- Implement:
  - `DocsFrontmatter` model
  - `category: Literal["Concept", "Task", "Reference", "Tutorial"]`
  - `status: Literal["Draft", "Active", "Deprecated"] = "Active"`
  - `last_updated` `YYYY-MM-DD` validator
  - list validators for `authors` and `related_specs`
- Tests:
  - valid minimal frontmatter
  - invalid enum
  - missing required field
  - invalid date string

## T2. Write validator script

- Owner: a1
- Target file:
  - `tools/docs_frontmatter_validator.py`
- Implement:
  - discovery for `docs/engine`, `docs/architecture`, `docs/studio`
  - forbidden path filters for skill files, fixtures, backup dirs, `.kiro/specs`
  - leading YAML frontmatter parser
  - `path:line` error output
  - non-zero exit on validation failures
- Tests:
  - temp docs tree with valid and invalid files
  - forbidden `GRAPH.md` ignored
  - missing frontmatter reported

## T3. Pre-commit hook integration

- Owner: a1
- Target files:
  - `.pre-commit-config.yaml` if present
  - project hook docs if pre-commit config is absent
- Implement:
  - hook id `docs-frontmatter`
  - files regex `^docs/(engine|architecture|studio)/.*\.md$`
  - no auto-fix behavior
- Verification:
  - local pre-commit run on changed docs
  - unchanged non-doc files ignored

## T4. Migrate existing docs frontmatter

- Owner: a1
- Target roots:
  - `docs/engine/**/*.md`
  - `docs/architecture/**/*.md`
  - `docs/studio/**/*.md`
- Scope estimate:
  - 26 engine docs outside `skill-spec`
  - 13 engine `skill-spec` docs
  - 4 architecture docs
  - 29 studio docs
  - total about 72 markdown files
- Implement:
  - add required fields to each document
  - choose Diátaxis category per design.md batches
  - add `related_specs` for docs governed by `.kiro/specs/`
- Verification:
  - validator passes on all target roots
  - no graph skill fixture files receive frontmatter

## T5. CI integration

- Owner: a1
- Target files:
  - `.github/workflows/ci.yml`
  - optional quality-gates docs
- Implement:
  - add validator step for `tools/docs_frontmatter_validator.py`
  - run after lint and before tests that depend on docs metadata
  - fail on missing or invalid frontmatter
- Verification:
  - CI fails on an intentionally invalid sample in a local dry run
  - CI passes after migration

## T6. Temporary allowlist removal

- Owner: a1
- Condition:
  - Only needed if migration is split across PRs.
- Implement:
  - if an allowlist exists, every entry must have an owner and removal task
  - remove allowlist when T4 is complete
- Verification:
  - validator has no silent skips except explicitly forbidden file classes.
