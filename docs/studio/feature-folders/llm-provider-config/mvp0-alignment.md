# llm-provider-config (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: LLM Role 覆盖、多 Provider API Keys 本地存取、连通性测试面
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL let the PM configure a real LLM path for V2.1 runs instead of relying on mock execution.
Current Settings UI and persistence behavior are in [baseline.md](./baseline.md).

First term: Provider means an API vendor or proxy such as Anthropic, OpenAI, Gemini, DeepSeek, Ark, or OpenRouter.
Role means a semantic use case such as `copilot_chat`, `planner`, or `critic`.
ModelResolver means engine code that turns a role into an actual chat model for runtime.

MVP0 SHOULD keep Settings tabs but make API Keys and LLM Roles clearly connected.
Settings tabs are mounted in `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:41` to `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:80`.
The PM should test providers first, then assign tested models to roles.

MVP0 SHOULD support real tests for Anthropic, OpenAI-compatible, and Gemini-compatible paths.
Current provider test endpoint exists in `apps/studio/backend/app/routers/llm.py:213` to `apps/studio/backend/app/routers/llm.py:265`.
MVP0 SHOULD show status badges for untested, ok, invalid key, rate limited, quota exceeded, timeout, and network error.

MVP0 SHOULD keep API key inputs safe but not use native password fields.
The API key redesign spec says inputs should be `type="text"` with password-manager suppression attributes, see `.kiro/specs/studio-api-keys-redesign/requirements.md:60` to `.kiro/specs/studio-api-keys-redesign/requirements.md:68`.
This avoids browser password manager prompts while still allowing CSS masking.

MVP0 SHOULD make model picker capabilities visible.
Capabilities are model properties such as context window, output limit, tool calling, vision, and thinking/reasoning support.
The roles spec requires capabilities in `.kiro/specs/llm-roles-setting/requirements.md:10` to `.kiro/specs/llm-roles-setting/requirements.md:17`.

MVP0 SHOULD expose per-phase override in Studio.
Per-phase override means a SKILL phase can request a role or model different from the default run model.
Current graph phase data already carries `llm_role`, see `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:162` to `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:184`.
The editor and Canvas should let PM select a role without editing YAML.

## 前端逻辑

MVP0 WILL keep credentials and roles loading in SettingsPage, but add capability-aware selection.
Current credentials load in `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:48` to `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:66`.
Current roles load in `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:68` to `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:83`.

MVP0 SHOULD make provider test the single writer of test outcome fields.
Frontend edits user-owned fields like title/base_url/api_key.
Backend test writes status, message, available models, and capabilities.
The API Keys spec defines this single-writer boundary in `.kiro/specs/studio-api-keys-redesign/round3-design.md:78` to `.kiro/specs/studio-api-keys-redesign/round3-design.md:83`.

MVP0 SHOULD add a model picker component shared by Settings, Canvas phase properties, and editor frontmatter form.

```typescript
export interface ModelCapabilitySummary {
  maxContextTokens?: number;
  maxOutputTokens?: number;
  supportsTools?: boolean;
  supportsVision?: boolean;
  supportsThinking?: boolean;
  raw?: Record<string, unknown>;
}

export interface ProviderModelOption {
  providerId: string;
  providerName: string;
  providerType: "anthropic_compatible" | "openai_compatible" | "google_genai";
  modelId: string;
  label: string;
  status: "available" | "untested" | "unavailable";
  capabilities: ModelCapabilitySummary;
}

export interface ModelPickerProps {
  value?: { roleName?: string; providerId?: string; modelId?: string };
  requiredCapabilities?: Partial<ModelCapabilitySummary>;
  onChange(next: { roleName?: string; providerId?: string; modelId?: string }): void;
}
```

MVP0 SHOULD preserve existing role utilities and extend them.
Current role draft helpers are in `apps/studio/frontend/src/components/studio/settings/role-utils.ts:7` to `apps/studio/frontend/src/components/studio/settings/role-utils.ts:82`.
MVP0 SHOULD add validation that selected model exists in provider `available_models`.

MVP0 SHOULD support role chain testing.
The role spec calls for chain aggregation and max concurrency of 3 in `.kiro/specs/llm-roles-setting/design.md:78` to `.kiro/specs/llm-roles-setting/design.md:82`.
The UI should test model fallbacks in order and show which provider will be used first.

## 后端功能

MVP0 WILL align backend provider config with engine ModelResolver.
Current credentials save to `~/.studio/llm_credentials.json`, see `apps/studio/backend/app/services/llm_credentials.py:26` to `apps/studio/backend/app/services/llm_credentials.py:30`.
Current credential writes are atomic and permissioned in `apps/studio/backend/app/services/llm_credentials.py:121` to `apps/studio/backend/app/services/llm_credentials.py:147`.

MVP0 SHOULD evaluate whether API keys move to Tauri Keychain.
Keychain means the OS-managed secure credential store.
If MVP0 keeps file storage, the document must explicitly mark it as local-dev storage with 0600 permissions.
Workspace filesystem system-level planning is [workspace-file-system mvp0](../../system-level/workspace-file-system/mvp0-alignment.md).

MVP0 SHOULD return available models and capabilities from provider tests.
Current test saves test result into provider state, see `apps/studio/backend/app/services/llm_credentials.py:71` to `apps/studio/backend/app/services/llm_credentials.py:118`.
API Keys round 3 wants GET /models probing and capabilities collection, see `.kiro/specs/studio-api-keys-redesign/round3-design.md:158` to `.kiro/specs/studio-api-keys-redesign/round3-design.md:213`.

MVP0 SHOULD make LLM roles file validation strict.
Current roles service validates provider/model references before save, see `apps/studio/backend/app/services/llm_roles.py:56` to `apps/studio/backend/app/services/llm_roles.py:80`.
MVP0 SHOULD additionally validate capability requirements when a role is used by a phase that requires tools or thinking.

MVP0 SHOULD expose a runtime resolution endpoint for Studio diagnostics.
This endpoint should not call the model.
It should explain which provider/model a role resolves to and why.
Engine runtime will use ModelResolver in [execution-runtime mvp0](../../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明).

## API

MVP0 SHOULD extend existing LLM APIs.
Frontend LLM API types currently live in `apps/studio/frontend/src/api/llm.ts:3` to `apps/studio/frontend/src/api/llm.ts:160`.
Current credentials functions are in `apps/studio/frontend/src/api/llm.ts:163` to `apps/studio/frontend/src/api/llm.ts:183`.
Current roles functions are in `apps/studio/frontend/src/api/llm.ts:199` to `apps/studio/frontend/src/api/llm.ts:212`.

```typescript
export interface ProviderCredentialRecord {
  id: string;
  name: string;
  providerKey: string;
  providerType: "anthropic_compatible" | "openai_compatible" | "google_genai";
  baseUrl?: string;
  apiKey: string;
  lastTestStatus: "untested" | "ok" | "invalid_key" | "rate_limited" | "quota_exceeded" | "timeout" | "network_error";
  lastTestAt?: string;
  lastTestMessage?: string;
  lastErrorCode?: string;
  availableModels: ProviderModelOption[];
}

export interface TestProviderRequest {
  providerId: string;
  providerKey: string;
  providerType: ProviderCredentialRecord["providerType"];
  baseUrl?: string;
  apiKey?: string;
}

export interface TestProviderResponse {
  status: ProviderCredentialRecord["lastTestStatus"];
  latencyMs?: number;
  message?: string;
  errorCode?: string;
  availableModels: ProviderModelOption[];
}
```

MVP0 SHOULD add role resolution API.

```typescript
export interface ResolveRoleRequest {
  roleName: string;
  phaseId?: string;
  requiredCapabilities?: Partial<ModelCapabilitySummary>;
}

export interface ResolveRoleResponse {
  roleName: string;
  selected?: ProviderModelOption;
  fallbackChain: ProviderModelOption[];
  warnings: string[];
  errors: string[];
}

export async function resolveRole(request: ResolveRoleRequest): Promise<ResolveRoleResponse>;
```

Proposed REST signatures:

```http
POST /api/llm/providers/test
TestProviderRequest -> TestProviderResponse

POST /api/llm/roles/resolve
ResolveRoleRequest -> ResolveRoleResponse
```

MVP0 SHOULD expose per-phase override save through editor/canvas file writes, not a separate hidden settings mutation.
The phase file remains the source of truth.

## Data Model / State

MVP0 SHOULD align frontend and backend models around provider identity.
Provider id identifies a credential instance.
Provider key identifies vendor metadata.
This distinction is emphasized in `.kiro/specs/studio-api-keys-redesign/round3-design.md:87` to `.kiro/specs/studio-api-keys-redesign/round3-design.md:105`.

Current backend credential model is in `apps/studio/backend/app/models/llm_config.py:127` to `apps/studio/backend/app/models/llm_config.py:133`.
Current roles model is in `apps/studio/backend/app/models/llm_config.py:136` to `apps/studio/backend/app/models/llm_config.py:224`.
MVP0 SHOULD extend these without letting frontend write test outcome fields directly.

```typescript
export interface LlmProviderConfigState {
  credentials: ProviderCredentialRecord[];
  roles: Record<string, {
    roleName: string;
    allowFallback: boolean;
    models: Array<{
      modelId: string;
      providerIds: string[];
      temperature?: number;
      maxTokens?: number;
      requiredCapabilities?: Partial<ModelCapabilitySummary>;
    }>;
  }>;
  selectedRole?: string;
  testingProviderId?: string;
  resolvingRoleName?: string;
}
```

MVP0 SHOULD treat capabilities as open dictionaries.
The roles design recommends schema-less capabilities in `.kiro/specs/llm-roles-setting/design.md:27` to `.kiro/specs/llm-roles-setting/design.md:34`.
The UI can normalize common keys while preserving raw provider metadata.

## Cross-feature interaction

### LLM role resolution owner {#cross-llm-role-resolution}

LLM provider config owns provider credentials, roles, model tests, and role resolution diagnostics.
Engine execution uses the resolved model through [execution-runtime mvp0](../../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明).
Copilot uses the `copilot_chat` role through [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-provider-role).

### Phase override UI {#cross-llm-phase-override}

Canvas and multi-file editor can expose per-phase role selection.
The saved value belongs in V2.1 phase files and is edited through [multi-file-editor mvp0](../multi-file-editor/mvp0-alignment.md#cross-editor-save-compile).
Canvas display is in [canvas-topology mvp0](../canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch).

### Provider errors in trace {#cross-llm-trace-errors}

Runtime provider failures SHOULD surface in Trace as actionable events.
Trace display is owned by [trace-visualization mvp0](../trace-visualization/mvp0-alignment.md#cross-trace-provider-errors).

### Secure storage boundary {#cross-llm-secure-storage}

Credential storage is a workspace/system-level concern when moving to keychain.
See [workspace-file-system mvp0](../../system-level/workspace-file-system/mvp0-alignment.md).
