# LLM Registry & Roles V2 Strategy

> **Superseded (2026-05-30):** The active platform direction is
> [`LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md`](./LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md).
> This older strategy is retained for historical context only. Its catalog ownership,
> credential, retry, readiness, and multi-client boundary guidance is no longer
> authoritative.

## 1. Core Principles
- **Knowledge-First**: Use a centralized, versioned "Golden Database" (Catalog) to minimize redundant probing.
- **Tiered Verification**: Separate basic connectivity (Ping) from deep capability verification (Contract Testing).
- **Non-Blocking Guidance**: Provide rich linting and warnings for capability mismatches, but allow the user to proceed if they accept the risk.
- **Lazy Deep Probing**: Perform expensive/complex capability verification only when a model is actually assigned to a Role.

---

## 2. The "Golden Database" (Model Catalog)
The "Golden Database" resides in the `graph-agent-gateway` or `studio` repository (e.g., `packages/graph-agent-gateway/src/graph_agent_gateway/registry/catalog.yaml`).

### Data Schema: Knowledge Lake Approach
To handle extreme variability, we store two tiers of data:
1. **Normalized Capabilities**: Standardized keys (e.g., `thinking_protocol`) used by the engine and UI.
2. **Raw Observations**: The complete, unedited JSON payload from `/models` and probe responses stored in `metadata.raw_observations`.

```yaml
models:
  - id_pattern: "claude-3-5-sonnet-.*"
    canonical_id: "claude-sonnet-3.5"
    capabilities:
      thinking: true # Normalized
    # All other provider-specific fields are preserved in the DB
    provider_specific_fields: 
      anthropic_beta: ["max-tokens-32k", "thinking-2024-12-04"]
      supports_json_mode_switch: true
```

---

## 3. Tiered Probing System

### L1: Connectivity Probe (Discovery Phase)
- **Goal**: Verify API Key + Base URL + Model ID availability.
- **Trigger**: API Key setup or "Refresh Models".
- **Action**: A minimal 1-token completion request (`max_tokens=1`).
- **Result**: `ok`, `unauthorized`, `not_found`, or `network_error`.

### L2: Capability Contract Probe (Role Config Phase)
- **Goal**: Verify if the model actually behaves as expected for specific features.
- **Trigger**: Model assigned to a Role, or manual "Deep Test" button.
- **Tests**:
  - **Thinking/Reasoning**: Verify output contains thinking blocks or reasoning metadata.
  - **Structured Output**: Verify JSON schema enforcement.
  - **Tool Calling**: Verify the model emits valid tool calls.

### L3: Bound & Limit Probe (Optional/Deep)
- **Goal**: Verify the actual limits (e.g., does it really support 128k context?).
- **Trigger**: Manual diagnostic action.

---

## 4. Autonomous Provider Intelligence Agent (Skill)

To avoid manual coding for every new model, we introduce a **Provider Intelligence Skill**.

### Workflow:
1. **Trigger**: A new model is discovered that doesn't match the Golden Database.
2. **Research (Agent)**:
   - Use `web-access` to search official documentation for the model ID.
   - Extract parameters like "Thinking budget", "JSON mode flags", and "Reasoning effort levels".
3. **Analysis (Agent)**:
   - Compare documentation vs. API response (`/models`).
   - Run **L2 Probe** to confirm behavior.
4. **Normalization**:
   - The Agent uses an internal LLM to map raw provider fields to our **Canonical Schema**.
   - Example: "Provider X uses `enable_thought`" -> Maps to `thinking_protocol: true`.
5. **Validation & Commit**:
   - Agent generates a **Registry Update Proposal** for review.
   - Once approved, the verified entry is committed to the global `catalog.yaml`.

---

## 5. Data Integrity & Precedence
To ensure accuracy when multiple sources exist, the system follows these precedence rules:
1. **L2/L3 Probe Results (Empirical)**: Real-world tests using the user's specific API key and route.
2. **Golden Database (Catalog)**: Human/Agent curated model specs.
3. **L1 Discovery Metadata**: Raw data returned by the provider's `/models` endpoint.
4. **Protocol Defaults**: General assumptions based on the protocol (e.g., OpenAI, Anthropic).

---

## 6. UX Workflow & Architecture

### Phase 1: API Key & Discovery (Inventory)
1. **User adds/updates API Key**.
2. **Pull Golden Database**: Fetch the latest catalog from the remote repository.
3. **Model Discovery**: Call `/models` on the provider.
4. **Data Import**: 
   - If `model_id` matches a Golden Database entry, import all capabilities/parameters automatically.
   - Mark as `verified_from_catalog`.
5. **Fallback L1**:
   - For unknown models (not in DB), run **L1 Probe**.
   - If success, mark as `available_unverified`.
   - If fail, mark as `offline`.

### Phase 2: LLM Roles & Materialization (Execution)
1. **User assigns a model to a Role** (e.g., "Fast" role requires `thinking: warn`).
2. **Deep Probe (L2)**:
   - System checks if the model has been L2-probed for the required capabilities.
   - If not, trigger background L2 probe or prompt user to "Verify Capabilities".
3. **Lint & Warn**:
   - Compare `Golden Database` / `Probe Results` with `Role Requirements`.
   - **Scenario**: Role requires `thinking`, but model catalog says `false` or Probe failed.
   - **Action**: Display a **Warning Icon/Tooltip**. "Warning: This model may not support thinking blocks. Output quality might be degraded."
   - **No Blocking**: User can still save and run.

---

## 5. Technical Implementation Map

| Component | Path | Responsibility |
|---|---|---|
| **Catalog** | `packages/graph-agent-gateway/.../catalog.yaml` | The remote source of truth for model specs. |
| **Discovery Service** | `apps/studio/backend/app/services/llm_import_drafts.py` | Pulls catalog, matches models, runs L1. |
| **L2 Prober** | `apps/studio/backend/app/services/copilot_test.py` | Executes contract-based deep probes. |
| **Lint Engine** | `packages/graph-agent-gateway/.../registry/lint.py` | Cross-checks Role requirements vs Route capabilities. |
| **Storage** | `~/.studio/llm_credentials.json` | Persists `probed_verified` or `catalog_verified` markers. |

---

## 6. Diagnosis of Current Gaps
- **Missing Catalog**: Current `capabilities.py` uses hardcoded logic; needs to move to the `catalog.yaml` model.
- **Soft Probing**: Existing probe doesn't distinguish between L1 and L2.
- **UI Decoupling**: API Key page and Roles page need clearer separation of "Discovery" vs "Verification".
