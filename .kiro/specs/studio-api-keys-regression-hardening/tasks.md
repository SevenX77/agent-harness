---
status: Implementing
created: 2026-05-25
owner: Studio
related_design: .kiro/specs/studio-api-keys-regression-hardening/design.md
---

# Studio API Keys Regression Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan intentionally restores frontend parity before v4 API integration.

**Goal:** Restore the deleted API Keys frontend behavior and Tauri paste/double-click safety first, then connect it to v4 endpoint/route registry APIs.

**Architecture:** Execute Phase 1 and Phase 1B before any API integration. Phase 1 restores UI parity using current frontend files and mocked v4-shaped data. Phase 1B fixes Tauri/macOS shortcut behavior and updates the UI spec. Phase 2 implements backend route upsert and frontend v4 API projection.

**Tech Stack:** React + TypeScript + shadcn/ui + Tailwind CSS, FastAPI + Pydantic, Tauri Rust shell, Vitest + Pytest + Playwright.

---

## Phase 1: Frontend Parity First

### Task 1: Lock API Keys Frontend Parity Fixture

**Files:**
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.test.tsx`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.test.tsx`
- Modify: `apps/studio/frontend/src/components/studio/SettingsPage.test.tsx`

- [x] 1.1 Add failing tests that define the restored frontend-only behavior.
  - ProviderCard must render `type="text"` for masked and visible API key states.
  - ProviderCard must expose show/hide/copy controls through `InputGroupButton`.
  - Official provider cards render without Provider Name / Base URL edit controls.
  - Third-party provider flow supports add, cancel, edit fields, and delete confirmation.
  - ManualModelTestPanel supports add/remove rows, loading state, duplicate result rendering, and unmatched route result rendering with mocked responses.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7, 5.8, 5.11_

- [x] 1.2 Run the frontend parity tests and confirm they fail for the current implementation.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/components/studio/api-keys/ProviderCard.test.tsx src/components/studio/api-keys/ManualModelTestPanel.test.tsx src/components/studio/SettingsPage.test.tsx`
  - Expected before implementation: failures for `type="password"` and any missing parity controls.
  - _Requirements: 4.1_

### Task 2: Restore ProviderCard and API Key Input Parity

**Files:**
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx`
- Modify: `apps/studio/frontend/src/index.css`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.test.tsx`

- [x] 2.1 Change API key input to always use `type="text"`.
  - Mask hidden state with CSS class only.
  - Keep actual input value equal to the real credential value.
  - Preserve password-manager suppression attributes.
  - _Requirements: 5.3_

- [x] 2.2 Keep row actions inside local `InputGroup`.
  - Use `InputGroup`, `InputGroupInput`, `InputGroupAddon`, and `InputGroupButton`.
  - Avoid absolute-positioned buttons over inputs.
  - _Requirements: 5.4_

- [x] 2.3 Run ProviderCard tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/components/studio/api-keys/ProviderCard.test.tsx`
  - Expected after implementation: ProviderCard tests pass.
  - _Requirements: 5.3, 5.4, 5.6_

### Task 3: Restore API Keys Page Sections and Third-party Flow

**Files:**
- Modify: `apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ProviderListSkeleton.tsx`
- Modify: `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`
- Modify: relevant tests under `apps/studio/frontend/src/components/studio/`

- [ ] 3.1 Restore Official Providers and Third-party Providers as separate sections.
  - Official cards: Anthropic, OpenAI, Gemini, DeepSeek, Ark.
  - Official endpoint ids: `anthropic-official`, `openai-official`, `gemini-official`, `deepseek-official`, `ark-official`.
  - Third-party flow: add, cancel, edit Provider Name, Base URL, API Key.
  - _Requirements: 5.1, 5.2_

- [ ] 3.2 Restore loading and delete interactions.
  - Use ProviderListSkeleton or equivalent stable skeleton while registry/credentials load.
  - Use `DeleteConfirmDialog` or approved local shadcn/Radix wrapper for destructive deletes.
  - _Requirements: 5.8, 5.11_

- [x] 3.3 Run settings/API Keys frontend tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/components/studio/SettingsPage.test.tsx src/components/studio/api-keys/*.test.tsx`
  - Expected after implementation: API Keys UI parity tests pass.
  - _Requirements: 5.1, 5.2, 5.8, 5.11_

### Task 4: Restore ManualModelTestPanel UI Without New API

**Files:**
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.test.tsx`
- Modify: `apps/studio/frontend/src/api/llm.test.ts` only for fixture behavior if needed

- [ ] 4.1 Restore the input-style Manual model probing UI.
  - Supports multiple model id rows.
  - Supports add/remove row controls.
  - Shows testing state and per-model result rows.
  - Does not claim persistence unless response came from route-backed state.
  - _Requirements: 5.7_

- [ ] 4.2 Preserve Phase 1 fixture behavior without adding backend endpoints.
  - `getNotableModels()` may remain a local fixture for suggestions only.
  - `testProviderModels()` can remain a known stub during Phase 1, but UI must label unmatched models as not registered, not success.
  - _Requirements: 5.7_

- [x] 4.3 Run ManualModelTestPanel tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/components/studio/api-keys/ManualModelTestPanel.test.tsx`
  - Expected after implementation: Manual panel UI parity tests pass.
  - _Requirements: 5.7_

### Task 5: Manual Frontend Parity Verification

**Files:**
- No production file edits unless verification finds frontend parity defects.

- [x] 5.1 Start or connect to the local frontend.
  - Preferred if Tauri is available: `cd apps/studio/tauri && cargo tauri dev`
  - Browser fallback acceptable for Phase 1 layout parity only.
  - _Requirements: 4.5, 5.12_

- [x] 5.2 Verify API Keys page interactions before API integration.
  - Official providers visible.
  - Third-party add/cancel/edit/delete confirm works.
  - API key paste into input works in browser path.
  - Show/hide/copy controls clickable.
  - Manual probing add/remove rows works.
  - Narrow viewport has no horizontal overflow.
  - _Requirements: 5.1, 5.2, 5.4, 5.7, 5.12_

## Phase 1B: Tauri Paste and Double-click Regression

These tasks are part of frontend restoration and must be completed before Phase 2 API work.

### Task 10: Restore No-native-Edit Tauri Menu Invariant

**Files:**
- Modify: `apps/studio/tauri/src/lib.rs`
- Modify: Rust tests in `apps/studio/tauri/src/lib.rs`

- [x] 10.1 Replace native Edit submenu invariant with no-native-Edit custom menu.
  - Keep default macOS menu disabled.
  - Keep App/File/View/Window/Help menus.
  - Remove tests that require native Edit menu.
  - _Requirements: 1.1, 1.4_

- [x] 10.2 Run Tauri targeted tests.
  - Run: `cargo test --manifest-path apps/studio/tauri/Cargo.toml macos_menu_spec_omits_native_edit_menu_to_avoid_double_click_alerts`
  - Expected after implementation: Tauri menu invariant tests pass.
  - _Requirements: 1.1, 1.4_

### Task 11: Add Editable Paste Shortcut Fallback

**Files:**
- Create: `apps/studio/frontend/src/hooks/useEditablePasteShortcut.ts`
- Modify: `apps/studio/frontend/src/App.tsx`
- Create: `apps/studio/frontend/src/hooks/useEditablePasteShortcut.test.ts`
- Modify: `apps/studio/frontend/tests/e2e/native-double-click.spec.ts`

- [x] 11.1 Add failing tests for editable paste.
  - Focused input receives `Cmd+V` / `Ctrl+V` through tested shortcut helpers.
  - Clipboard text is inserted once.
  - Non-editable chrome remains guarded by double-click guard.
  - _Requirements: 1.2, 1.3, 1.5_

- [x] 11.2 Implement editable paste shortcut fallback.
  - Scope to editable targets only.
  - Use clipboard read during user gesture.
  - Insert via input/textarea selection APIs and dispatch input event.
  - _Requirements: 1.2, 1.3_

- [x] 11.3 Run frontend shortcut tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/hooks/useEditablePasteShortcut.test.ts`
  - Run: `pnpm --dir apps/studio/frontend exec playwright test tests/e2e/native-double-click.spec.ts`
  - Expected after implementation: paste and double-click guard tests pass.
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

### Task 12: Update FRONTEND_UI_SPEC

**Files:**
- Modify: `docs/development/FRONTEND_UI_SPEC.md`

- [x] 12.1 Replace the native Edit submenu rule.
  - Document that Tauri macOS shell omits native Edit submenu to avoid the double-click alert sound path.
  - Document that focused editable paste is handled by the tested frontend/Tauri shortcut path.
  - _Requirements: 4.2_

- [x] 12.2 Verify the spec no longer contradicts `14f8e36`.
  - Run: `rg -n "native .*Edit|Edit submenu|Cmd\\+V|double-click" docs/development/FRONTEND_UI_SPEC.md`
  - Expected after implementation: wording matches no-native-Edit + paste fallback strategy.
  - _Requirements: 4.2_

## Phase 2: v4 API Integration

### Task 6: Backend Model List Parser Returns All Model IDs

**Files:**
- Modify: `apps/studio/backend/app/services/copilot_test.py`
- Modify: `apps/studio/backend/tests/services/test_copilot_test.py`

- [ ] 6.1 Write failing parser tests.
  - OpenAI/Anthropic shape: `{"data": [{"id": "a"}, {"id": "b"}]}` returns `("a", "b")`.
  - Gemini shape: `{"models": [{"name": "models/gemini-2.5-pro"}, {"name": "gemini-2.5-flash"}]}` returns `("gemini-2.5-pro", "gemini-2.5-flash")`.
  - Duplicate ids are de-duped in order.
  - Malformed entries are ignored.
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 6.2 Implement list-capable `PingResult`.
  - Keep `model_seen` compatibility as first model id.
  - Replace `_first_model_id` usage with all-model parser.
  - _Requirements: 2.1, 2.4_

- [ ] 6.3 Run parser tests.
  - Run: `pytest apps/studio/backend/tests/services/test_copilot_test.py -q`
  - Expected after implementation: parser tests pass.
  - _Requirements: 2.1, 2.2, 2.3_

### Task 7: Backend Endpoint Test Upserts ProviderRoutes

**Files:**
- Modify: `apps/studio/backend/app/services/llm_credentials.py`
- Modify: `apps/studio/backend/app/routers/llm.py`
- Modify: `apps/studio/backend/tests/routers/test_llm_registry_api.py`

- [ ] 7.1 Extract or reuse route creation logic from v3-to-v4 migration.
  - Use `_route_slug`.
  - Use `canonicalize_model`.
  - Use `normalize_route_capabilities`.
  - Preserve existing route metadata on duplicate model ids.
  - _Requirements: 2.5, 2.6_

- [ ] 7.2 Update `POST /api/llm/endpoints/{endpoint_id}/test`.
  - On successful model list, update endpoint status and upsert route candidates.
  - On invalid key, keep endpoint failed and do not add routes.
  - _Requirements: 2.4, 2.9_

- [ ] 7.3 Run backend router tests.
  - Run: `pytest apps/studio/backend/tests/routers/test_llm_registry_api.py -q`
  - Expected after implementation: route upsert, duplicate preservation, and invalid-key tests pass.
  - _Requirements: 2.4, 2.5, 2.6, 2.9_

### Task 8: Frontend TestProvider Uses v4 Registry Routes

**Files:**
- Modify: `apps/studio/frontend/src/api/llm.ts`
- Modify: `apps/studio/frontend/src/api/llm.test.ts`
- Modify: `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`
- Modify: relevant API Keys tests

- [ ] 8.1 Write failing frontend API tests for v4 flow.
  - `testProvider()` calls endpoint upsert, endpoint test, then refreshes/merges registry routes.
  - `available_models` comes from all routes for the endpoint.
  - `available_sdks` is `[endpoint.protocol]`.
  - _Requirements: 2.8, 5.5, 5.6, 5.9_

- [ ] 8.2 Implement v4 registry projection after Test.
  - Do not use old `/providers/test` or `/credentials` paths.
  - Do not overwrite in-progress local form fields with older backend response.
  - _Requirements: 2.8, 3.4, 5.9, 5.10_

- [ ] 8.3 Run frontend API tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/api/llm.test.ts src/components/studio/SettingsPage.test.tsx`
  - Expected after implementation: v4 Test projection passes.
  - _Requirements: 2.8, 5.5, 5.6, 5.9_

### Task 9: Manual Probing Scheme B Integration

**Files:**
- Modify: `apps/studio/frontend/src/api/llm.ts`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.tsx`
- Modify: `apps/studio/frontend/src/components/studio/api-keys/ManualModelTestPanel.test.tsx`
- Modify: `apps/studio/frontend/src/api/llm.test.ts`

- [ ] 9.1 Replace local-success behavior with route-candidate probing.
  - Match entered model id to existing route for the provider endpoint.
  - For matched route, call `POST /api/llm/routes/{route_id}/probe`.
  - Refresh registry after probe.
  - For unmatched model id, show not-registered result.
  - _Requirements: 5.7, 5.9_

- [ ] 9.2 Run Manual probing integration tests.
  - Run: `pnpm --dir apps/studio/frontend exec vitest run src/api/llm.test.ts src/components/studio/api-keys/ManualModelTestPanel.test.tsx`
  - Expected after implementation: no local-only append; refresh-backed route results pass.
  - _Requirements: 5.7, 5.9_

## Final Verification

- [ ] 13.1 Run backend targeted tests.
  - `pytest apps/studio/backend/tests/services/test_copilot_test.py apps/studio/backend/tests/routers/test_llm_registry_api.py -q`

- [ ] 13.2 Run frontend targeted tests.
  - `pnpm --dir apps/studio/frontend exec vitest run src/api/llm.test.ts src/components/studio/SettingsPage.test.tsx src/components/studio/api-keys/*.test.tsx src/hooks/useEditablePasteShortcut.test.ts`

- [ ] 13.3 Run frontend typecheck.
  - `pnpm --dir apps/studio/frontend exec tsc -b --noEmit`

- [ ] 13.4 Run Tauri checks.
  - `cargo test --manifest-path apps/studio/tauri/Cargo.toml`
  - `cargo check --manifest-path apps/studio/tauri/Cargo.toml`

- [ ] 13.5 Run manual app verification.
  - Start: `cd apps/studio/tauri && cargo tauri dev`
  - Verify API Keys workflows: paste, show/hide/copy, Test success/error, Manual probing, third-party add/cancel/delete, refresh persistence, double-click no alert sound, narrow viewport no overflow.

- [ ] 13.6 Compare frontend parity against reference commit.
  - Run: `git diff 33a4135..HEAD -- apps/studio/frontend/src/components/studio/api-keys/`
  - Confirm any differences are intentional v4 DTO adaptations, not missing deleted UI behavior.
