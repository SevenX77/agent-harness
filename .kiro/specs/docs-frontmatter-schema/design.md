# Design: Docs Frontmatter Schema

## 1. 目标

给 `docs/engine/`, `docs/architecture/`, `docs/studio/` 内的说明文档建立统一 YAML frontmatter。目标是让文档具备稳定分类、状态、更新时间和 cross-link 元数据, 方便后续导航、校验和迁移。

本 spec 只管文章性 Markdown 文档。它不改变 graph skill 文件格式, 不给 `GRAPH.md`, `LOGIC.md`, `SKILL.md`, `SUBGRAPH.md`, 项目根 `README.md` 或 fixture markdown 注入 frontmatter。

## 2. Frontmatter 字段 schema

```yaml
---
title: "Human-readable title"
description: "One-sentence summary"
category: "Concept"
status: "Active"
last_updated: "2026-05-23"
authors:
  - "a1 Codex"
related_specs:
  - ".kiro/specs/engine-mvp0-rebuild-v030/tasks.md"
---
```

### `title`

- 类型: `string`
- 必填: 是
- 约束: trim 后非空; 应与页面 H1 含义一致, 但不要求逐字相同。
- 作用: 文档索引、导航标题、验证器错误提示。

### `description`

- 类型: `string`
- 必填: 是
- 约束: trim 后非空; 建议一句话, 不写实现细节长段落。
- 作用: 目录摘要和搜索结果预览。

### `category`

- 类型: enum
- 必填: 是
- 允许值:
  - `Concept`
  - `Task`
  - `Reference`
  - `Tutorial`
- 作用: 采用 Diátaxis 分类。`Concept` 解释概念和模型; `Task` 描述操作流程; `Reference` 是字段/API/规范清单; `Tutorial` 是教学 walkthrough。

### `status`

- 类型: enum
- 必填: 是
- 默认: `Active`
- 允许值:
  - `Draft`
  - `Active`
  - `Deprecated`
- 作用: 标识文档生命周期。新文档未验证时用 `Draft`; 现行源文档用 `Active`; 旧语义保留但不推荐使用时用 `Deprecated`。

### `last_updated`

- 类型: date string
- 必填: 是
- 约束: `YYYY-MM-DD`; 由人工或迁移脚本写入。
- 作用: stale docs 检查、review 优先级和索引排序。

### `authors`

- 类型: `list[string]`
- 必填: 否
- 默认: `[]`
- 约束: 每项 trim 后非空。
- 作用: 记录主要撰写者或责任 agent; 不用于权限控制。

### `related_specs`

- 类型: `list[string]`
- 必填: 否
- 默认: `[]`
- 约束: 每项是 repo-relative path 或 stable spec id; 路径存在性由 validator 检查。
- 作用: 连接 `.kiro/specs/` 决策与 docs 说明文档。

## 3. 适用范围

必须迁移的目录:

- `docs/engine/**/*.md`
- `docs/architecture/**/*.md`
- `docs/studio/**/*.md`

只迁移说明文档。`docs/engine/skill-spec/*.md` 属于 reference 文档, 应迁移并标 `category: Reference`。

## 4. 严禁范围

不得注入 frontmatter 的文件:

- graph skill 文件: `GRAPH.md`, `LOGIC.md`, `SKILL.md`, `SUBGRAPH.md`
- repo 根 `README.md` 或包 README
- fixture / sample skill 内的 markdown
- `.kiro/specs/**` 本身
- `docs.backup-*` 备份目录

原因: 这些文件要么有自己的 parser, 要么是输入 fixture。额外 frontmatter 会改变被测文本或 graph skill 语义。

## 5. 迁移路径

当前候选文件来自:

```bash
find docs/engine docs/architecture docs/studio -type f -name '*.md' | sort
```

迁移批次:

### Batch 1: engine overview / feature docs

- `docs/engine/MVP0-DECISIONS-EXPLAINED-2026-05-21.md`
- `docs/engine/MVP0-PROGRESS-2026-05-21.md`
- `docs/engine/execution-runtime/{baseline,logic-explained,mvp0-alignment}.md`
- `docs/engine/graph-agent-gateway/{INDEX,baseline,logic-explained,mvp0-alignment}.md`
- `docs/engine/skill-compilation/{baseline,logic-explained,mvp0-alignment}.md`
- `docs/engine/skill-resolution/{baseline,logic-explained,mvp0-alignment}.md`
- `docs/engine/state-and-io-contract/{baseline,logic-explained,mvp0-alignment}.md`
- `docs/engine/tracing-and-observability/{baseline,logic-explained,mvp0-alignment}.md`

Recommended category:

- `logic-explained.md`, `baseline.md`, `mvp0-alignment.md`: `Concept`
- `INDEX.md`: `Reference`
- progress / decisions reports: `Reference`

### Batch 2: engine skill-spec reference docs

- `docs/engine/skill-spec/README.md`
- `docs/engine/skill-spec/01-physical-layout.md`
- `docs/engine/skill-spec/02-graph-md-spec.md`
- `docs/engine/skill-spec/03-logic-md-spec.md`
- `docs/engine/skill-spec/04-subgraph-md-spec.md`
- `docs/engine/skill-spec/05-agent-md-spec.md`
- `docs/engine/skill-spec/06-cognitive-template-spec.md`
- `docs/engine/skill-spec/07-mention-syntax-spec.md`
- `docs/engine/skill-spec/08-resource-mechanisms-spec.md`
- `docs/engine/skill-spec/09-builtin-modules-spec.md`
- `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md`
- `docs/engine/skill-spec/11-error-code-spec.md`
- `docs/engine/skill-spec/12-compile-runtime-flow-spec.md`

Recommended category: `Reference`.

### Batch 3: architecture docs

- `docs/architecture/agent-cognitive-architecture/{baseline,mvp0-alignment}.md`
- `docs/architecture/prod-dev-separation/{baseline,mvp0-alignment}.md`

Recommended category: `Concept`.

### Batch 4: Studio docs

- `docs/studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md`
- `docs/studio/feature-folders/*/{baseline,mvp0-alignment}.md`
- `docs/studio/system-level/*/{baseline,mvp0-alignment}.md`
- `docs/studio/ux_workflow/00_INDEX_AND_OVERVIEW.md`
- `docs/studio/ux_workflow/01_DISCOVERY_AND_INIT.md`
- `docs/studio/ux_workflow/02_EDIT_AND_COMPILE.md`
- `docs/studio/ux_workflow/03_PREDICT_AND_BASELINE.md`
- `docs/studio/ux_workflow/04_RUN_AND_TRACE.md`
- `docs/studio/ux_workflow/05_DEBUG_AND_RESUME.md`
- `docs/studio/ux_workflow/06_EVAL_AND_PUBLISH.md`

Recommended category:

- feature/system baseline/alignment: `Concept`
- ux workflow: `Task` or `Tutorial`, depending on whether the page is an executable workflow.
- requirements cleanup file: `Reference`.

## 6. 校验机制

新增 validator 脚本建议路径:

```text
tools/docs_frontmatter_validator.py
```

Validator responsibilities:

1. Discover only allowed docs roots: `docs/engine`, `docs/architecture`, `docs/studio`.
2. Exclude forbidden file names and backup / fixture directories.
3. Parse leading YAML frontmatter block.
4. Validate fields with a Pydantic model:
   - required fields present
   - enum values valid
   - `last_updated` matches `YYYY-MM-DD`
   - `authors` and `related_specs` are lists of strings
5. Validate `related_specs` paths exist when repo-relative.
6. Print `path:line` style errors and exit non-zero.

Pre-commit hook:

```yaml
- id: docs-frontmatter
  name: docs frontmatter schema
  entry: python tools/docs_frontmatter_validator.py
  language: system
  files: ^docs/(engine|architecture|studio)/.*\.md$
```

CI integration:

- Add a quality-gates step after `ruff check` and before docs build.
- The step should run the same script without auto-fix.
- Migration PR may allow a temporary allowlist only if every allowlisted file has a tracking task in `.kiro/specs/docs-frontmatter-schema/tasks.md`.
