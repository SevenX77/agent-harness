# skill-lifecycle (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 新技能引导创建向导、模板复用、批处理测试、Golden 历史对比、导入 / 导出
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make the full V2.1 skill lifecycle possible from Studio: create, edit, run, inspect, test, compare, export.
Current lifecycle UI is documented in [baseline.md](./baseline.md).

First term: lifecycle means everything around a skill besides one edit operation.
It includes creation, import, template selection, batch test, golden comparison, publish/export, and delete.

MVP0 SHOULD mount `SkillCreatorWizard` as the primary create flow.
Current WelcomePage uses `NewSkillDialog`, while `SkillCreatorWizard` exists but is not mounted; see `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:43`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:350`, and `apps/studio/frontend/src/components/creator/SkillCreatorWizard.tsx:25`.

MVP0 SHOULD make the wizard create V2.1 directory skills.
A created skill must include `GRAPH.md`, `io/inputs.json`, `io/outputs.json`, and phase files.
The current generator still emits graph frontmatter into markdown, see `apps/studio/frontend/src/templates/skillMdGenerator.ts:68` to `apps/studio/frontend/src/templates/skillMdGenerator.ts:95`.

MVP0 SHOULD show templates as V2.1 templates, not legacy `*.SKILL.md` only.
Current backend template service scans `*.SKILL.md`, see `apps/studio/backend/app/services/templates.py:15` to `apps/studio/backend/app/services/templates.py:30`.
MVP0 templates should scaffold a directory tree.

MVP0 SHOULD keep import from local directory.
WelcomePage already calls `selectSkillDirectory` and posts `/skills`, see `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:127` to `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:159`.
MVP0 SHOULD validate imported V2.1 structure and show repair suggestions.

MVP0 SHOULD turn batch testing into a PM-visible quality gate.
Current BatchRunner lets users select test inputs and run batch, see `apps/studio/frontend/src/components/playground/BatchRunner.tsx:22` to `apps/studio/frontend/src/components/playground/BatchRunner.tsx:112`.
MVP0 SHOULD show pass/fail by fixture, golden diff summary, and first failing phase.

MVP0 SHOULD support export/import zip for V2.1 skill directories.
Publish zip exists today in backend, see `apps/studio/backend/app/services/artifact_registry.py:91` to `apps/studio/backend/app/services/artifact_registry.py:127`.
MVP0 SHOULD expose it as "Export" in Studio, with import validation on the reverse path.

## 前端逻辑

MVP0 WILL replace single-file creation assumptions with a V2.1 scaffold plan.
Current `useSkillCreator` manages step/data/submitting/error, see `apps/studio/frontend/src/hooks/useSkillCreator.ts:9` to `apps/studio/frontend/src/hooks/useSkillCreator.ts:27`.
Current step validation is in `apps/studio/frontend/src/hooks/useSkillCreator.ts:105` to `apps/studio/frontend/src/hooks/useSkillCreator.ts:143`.

MVP0 SHOULD make wizard steps match the MVP0 goal.
Step 1: choose template.
Step 2: define skill name and inputs.
Step 3: create first phase and phase type.
Step 4: choose LLM role if SKILL phase.
Step 5: preview generated file tree.

```typescript
export type V21PhaseTemplateType = "logic" | "subgraph" | "skill";

export interface V21SkillCreateDraft {
  skillId: string;
  name: string;
  description?: string;
  templateId?: string;
  inputs: Array<{ name: string; type: "string" | "number" | "boolean" | "object" | "array"; required: boolean }>;
  outputs: Array<{ name: string; type: string; required: boolean }>;
  phases: Array<{
    id: string;
    name: string;
    type: V21PhaseTemplateType;
    llmRole?: string;
    dependsOn: string[];
    prompt?: string;
    subSkillRef?: string;
  }>;
}

export interface V21ScaffoldPreview {
  files: Array<{ path: string; content: string; role: string }>;
  warnings: string[];
}
```

MVP0 SHOULD open created skills directly into Canvas + Editor.
Canvas owns graph view.
Editor owns file tree.
The lifecycle flow should not stop at a success toast.

MVP0 SHOULD make batch testing reusable.
Current `useBatchRun` tracks selected inputs and batch status, see `apps/studio/frontend/src/hooks/useBatchRun.ts:12` to `apps/studio/frontend/src/hooks/useBatchRun.ts:90`.
MVP0 SHOULD add fixture grouping, run-all, rerun-failed, and compare-to-golden actions.

MVP0 SHOULD show golden diff as a lifecycle quality artifact.
Trace owns event display, but lifecycle owns "is this skill ready?".
Current TracePanel has Compare and Golden buttons, see `apps/studio/frontend/src/components/TracePanel.tsx:56` to `apps/studio/frontend/src/components/TracePanel.tsx:75`.

## 后端功能

MVP0 WILL add a V2.1 scaffold path to skill creation.
Current `POST /api/skills` route exists in `apps/studio/backend/app/routers/skills.py:81` to `apps/studio/backend/app/routers/skills.py:95`.
Current `create_new_skill` either imports non-empty directories or scaffolds default files, see `apps/studio/backend/app/services/skills.py:443` to `apps/studio/backend/app/services/skills.py:492`.

MVP0 SHOULD make backend the owner of directory scaffold writes.
This aligns with the audit concern that `.workspace` and template directory creation need clear ownership.
The audit calls this out in `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:65` to `docs.backup-2026-05-20/archive/2026-05-19-studio-baseline-audit.md:82`.

MVP0 SHOULD generate V2.1 files from templates.
Template service currently reads markdown templates, see `apps/studio/backend/app/services/templates.py:15` to `apps/studio/backend/app/services/templates.py:30`.
MVP0 SHOULD add directory templates under a known templates root and return tree previews to frontend.

MVP0 SHOULD integrate compile after create/import.
The created skill should compile or return structured compile issues before opening.
Compile endpoint is already available in `apps/studio/backend/app/routers/skills.py:108` to `apps/studio/backend/app/routers/skills.py:118`.

MVP0 SHOULD keep batch run backend but add golden-aware summaries.
`RunManager.start_batch_run` already creates runs for each input, see `apps/studio/backend/app/services/run_manager.py:335` to `apps/studio/backend/app/services/run_manager.py:352`.
`get_batch_status` aggregates run metadata, see `apps/studio/backend/app/services/run_manager.py:354` to `apps/studio/backend/app/services/run_manager.py:385`.

MVP0 SHOULD build golden diff on phase outputs, not only final state.
Engine state-and-io mvp0 defines phase outputs and isolation, see [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).
Current golden diff recursively compares final state in `apps/studio/backend/app/services/golden_diff.py:68` to `apps/studio/backend/app/services/golden_diff.py:160`.

## API

MVP0 SHOULD keep existing lifecycle APIs and add V2.1-specific scaffold/import/export contracts.
Existing routes include templates, create, delete, publish, batch, golden, and compare; see `apps/studio/backend/app/routers/templates.py:10` to `apps/studio/backend/app/routers/templates.py:15`, `apps/studio/backend/app/routers/skills.py:81` to `apps/studio/backend/app/routers/skills.py:95`, and `apps/studio/backend/app/routers/skills.py:245` to `apps/studio/backend/app/routers/skills.py:280`.

```typescript
export interface CreateV21SkillRequest {
  draft: V21SkillCreateDraft;
  targetDirectory?: string;
  compileAfterCreate: boolean;
}

export interface CreateV21SkillResponse {
  skillId: string;
  rootPath: string;
  createdFiles: Array<{ path: string; hash: string; role: string }>;
  compile: {
    ok: boolean;
    issues: Array<{ severity: "error" | "warning"; message: string; filePath?: string; line?: number }>;
  };
}

export interface V21TemplateSummary {
  templateId: string;
  name: string;
  description?: string;
  tags: string[];
  previewFiles: string[];
}
```

Proposed lifecycle signatures:

```http
GET /api/templates/v21
V21TemplateSummary[]

POST /api/skills/v21
CreateV21SkillRequest -> CreateV21SkillResponse

POST /api/skills/{skill_id}/export
{ format: "zip"; includeRuns?: boolean } -> { artifactId: string; downloadUrl: string }

POST /api/skills/import
multipart/form-data zip -> CreateV21SkillResponse
```

Batch/golden MVP0 shape:

```typescript
export interface BatchQualitySummary {
  batchId: string;
  skillId: string;
  status: "queued" | "running" | "success" | "failed";
  items: Array<{
    inputId: string;
    runId?: string;
    status: "queued" | "running" | "success" | "failed";
    firstFailedPhaseId?: string;
    goldenDiff?: { changedFields: number; summary: string };
  }>;
}
```

## Data Model / State

MVP0 SHOULD make lifecycle state explicit.

```typescript
export interface SkillLifecycleState {
  skills: Array<{ skillId: string; name: string; rootPath: string; v21: boolean }>;
  createDraft?: V21SkillCreateDraft;
  scaffoldPreview?: V21ScaffoldPreview;
  importing?: { fileName: string; status: "validating" | "creating" | "failed" };
  exportingSkillId?: string;
  batchQualityById: Record<string, BatchQualitySummary>;
}
```

MVP0 SHOULD treat template as source metadata, not a live dependency.
After scaffold, the skill directory owns its files.
The template id can stay in metadata for provenance, but editing should not mutate the template.

MVP0 SHOULD keep skill summary/detail compatibility.
Current `SkillSummary` and `SkillDetail` are defined in `apps/studio/frontend/src/api/types.ts:60` to `apps/studio/frontend/src/api/types.ts:69` and `apps/studio/frontend/src/api/types.ts:383` to `apps/studio/frontend/src/api/types.ts:403`.
MVP0 can add fields but should not make the welcome page depend on opened editor state.

MVP0 SHOULD make golden data phase-aware.
Current golden baseline copies run final state and metadata, see `apps/studio/backend/app/services/golden_diff.py:34` to `apps/studio/backend/app/services/golden_diff.py:65`.
Phase-aware golden should store final state plus selected phase outputs so failures point to the step that changed.

## Cross-feature interaction

### Lifecycle V2.1 create owner {#cross-lifecycle-v21-create}

Skill lifecycle owns V2.1 scaffold, import, template selection, and initial open.
Canvas displays the created graph through [canvas-topology mvp0](../canvas-topology/mvp0-alignment.md#cross-canvas-phase-create).
Editor displays the created files through [multi-file-editor mvp0](../multi-file-editor/mvp0-alignment.md#cross-editor-v21-file-tree).

### Lifecycle golden batch owner {#cross-lifecycle-golden-batch}

Skill lifecycle owns batch test quality summary and golden readiness.
Trace owns detailed event and compare display in [trace-visualization mvp0](../trace-visualization/mvp0-alignment.md#cross-trace-golden).
Engine state outputs come from [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

### Lifecycle role defaults {#cross-lifecycle-role-defaults}

Skill lifecycle can suggest default `llm_role` for new SKILL phases.
The valid role registry is owned by [llm-provider-config mvp0](../llm-provider-config/mvp0-alignment.md#cross-llm-role-resolution).

### Lifecycle Copilot onboarding {#cross-lifecycle-copilot-onboarding}

After creating a skill, lifecycle may open Copilot with a seeded prompt like "help me refine this first phase".
Copilot owns the chat and edit loop in [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-lifecycle-help).
