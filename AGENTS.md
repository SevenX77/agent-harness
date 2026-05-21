# Agent Harness Project Rules

## Studio Frontend UI

- Before changing `apps/studio/frontend` UI, read `docs/development/FRONTEND_UI_SPEC.md`, especially section 2.
- First search `apps/studio/frontend/src/components/ui/` for an existing shadcn/ui or Radix wrapper. Prefer those components over custom interaction code.
- If a needed primitive is missing, add the shadcn/ui-style wrapper under `src/components/ui/` before using it in business components.
- Use semantic design tokens and existing component variants. Do not hardcode hex colors or one-off Tailwind palette colors.
- For collapsible, modal, dropdown, select, tooltip, tabs, alert, and confirmation interactions, use the local `@/components/ui/*` wrappers unless there is a specific product reason not to.
- In status updates for UI work, name the design-system component being used when one applies.
- Before finishing frontend changes, run the app and personally inspect the changed screen in a browser or Tauri shell. Click through every touched interactive workflow, including the main success path and obvious cancel/error states when feasible, and report that manual verification; tests and builds alone are not enough.

## Studio Tauri Dev

- Standard startup is documented in `apps/studio/tauri/README.md`: `cd apps/studio/tauri && cargo tauri dev`.
- Prefer one Tauri dev session only. It owns both Vite and the dynamic FastAPI sidecar.
- If using a non-default Vite port, ensure backend CORS allows the exact frontend origin via `STUDIO_CORS_EXTRA_ORIGINS` or a checked-in config change.
