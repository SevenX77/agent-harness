---
status: Draft
created: 2026-05-27
owner: Studio
related_requirements: .kiro/specs/studio-llm-roles-frontend-cutover/requirements.md
---

# Studio LLM Roles Frontend Cutover Research

## Existing State

The current LLM Roles page already has the desired broad visual structure:

- left Settings navigation
- role sections for Graph Agent Roles and Copilot Roles
- right `Available Models` sidebar
- role cards with model fallback switch, Test button, and action menu
- pointer-based drag fallback for Tauri/WebKit

The remaining problem is not the broad layout. It is data ownership:

- the old frontend relied on `CredentialsState.available_models`
- the new backend owns `ModelGroup`, provider model options, provider state, role fit, and materialization
- frontend must stop inferring model identity or provider status from raw strings

## Current Gap

The existing `studio-llm-roles-model-groups` spec has backend and gateway phases plus broad frontend Phase 8/9 tasks. That is not enough to manage the current desired workflow:

- one frontend change at a time
- user confirms each phase
- commit after each confirmation
- maximum revert space

This spec narrows the frontend work into six PR-sized units.

## Design System Notes

The page must continue following `docs/development/FRONTEND_UI_SPEC.md`:

- use local shadcn/Radix wrappers
- use `Tag` for provider/model/vendor entity labels
- use `Badge` for status badges
- use `CatalogAccordion` for role sections
- use `Dialog`, `DropdownMenu`, `DeleteConfirmDialog`, `Tooltip`, and `Field` where those interactions appear
- use semantic tokens only
- verify real browser/Tauri UI before finishing a phase

## Non-Goals

1. Do not redesign the page layout from scratch.
2. Do not expose route/endpoint/canonical terminology in primary UI.
3. Do not add a bundle creation prompt during normal drag/drop.
4. Do not use frontend canonicalization as the authoritative model grouping or display-name system.
5. Do not mix API Keys regression work into LLM Roles frontend commits.

## Why This Is Separate From Gateway Boundary Work

The frontend needs Studio Backend DTOs. Gateway runtime schema must not be treated as a UI source. The separate `studio-gateway-runtime-schema-boundary` spec defines that deeper cleanup. This frontend cutover can proceed only when the backend offers stable Studio-owned display and projection fields, or it must keep any frontend fallback explicitly temporary and non-authoritative.

