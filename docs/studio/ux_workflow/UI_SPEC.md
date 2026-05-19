# Skill Studio · UI Specification

> Living spec, evolves with the `apps/studio/uikit/` sandbox. Phase A locks each section as the corresponding sandbox slice ships. Phase B (migration into `apps/studio/frontend/`) treats this doc as the contract.

## §0 Scope and source of truth

- **Visual baseline**: shadcn `radix-mira` preset (preset id `b38miVIYq`, deep indigo-violet primary on neutral grays, light + dark, 0.625rem radius, Inter Variable + JetBrains Mono Variable, lucide icons).
- **Layout baseline**: v0 mockup at `temp/ai-agent.zip` (Workspace shell = top Header, left Toolbar rail, collapsible left context panel, ReactFlow canvas, fixed right Copilot rail).
- **Functional baseline**: 6-node workflow defined in `docs/studio/ux_workflow/00_INDEX_AND_OVERVIEW.md` through `06_EVAL_AND_PUBLISH.md`.
- **Sandbox**: `apps/studio/uikit/` (Vite + React + shadcn), serves at `http://0.0.0.0:55424` for review.
- **Token source**: `apps/studio/uikit/src/index.css` is canonical for color / radius / font tokens; this doc names and explains them, but **values live in CSS** to avoid drift.

## §1 Color tokens

All colors use `oklch()`, defined as CSS variables in two scopes: `:root` (light mode) and `.dark` (dark mode). Tailwind 4 `@theme inline` bridges them as utility classes (`bg-background`, `text-foreground`, `border-border`, etc.).

### §1.1 Semantic palette

| Semantic name      | CSS variable             | Light mode value         | Dark mode value          | Use for                                          |
|--------------------|--------------------------|--------------------------|--------------------------|--------------------------------------------------|
| `background`       | `--background`           | `oklch(1 0 0)` (white)   | `oklch(0.145 0 0)` (near-black) | App canvas background.                    |
| `foreground`       | `--foreground`           | `oklch(0.145 0 0)`       | `oklch(0.985 0 0)`       | Primary ink on background.                       |
| `card`             | `--card`                 | `oklch(1 0 0)`           | `oklch(0.205 0 0)`       | Raised surfaces (nodes, panels, dialogs).        |
| `card-foreground`  | `--card-foreground`      | `oklch(0.145 0 0)`       | `oklch(0.985 0 0)`       | Ink on card.                                     |
| `popover`          | `--popover`              | `oklch(1 0 0)`           | `oklch(0.205 0 0)`       | Floating overlays (dropdowns, tooltips, popovers). |
| `popover-foreground` | `--popover-foreground` | `oklch(0.145 0 0)`       | `oklch(0.985 0 0)`       | Ink on popover.                                  |
| `primary`          | `--primary`              | `oklch(0.457 0.24 277.023)` (indigo-violet) | `oklch(0.398 0.195 277.366)` | Brand color: primary buttons, focused inputs, running pulse, active node ring. |
| `primary-foreground` | `--primary-foreground` | `oklch(0.962 0.018 272.314)` | `oklch(0.962 0.018 272.314)` | Ink on primary fill.                          |
| `secondary`        | `--secondary`            | `oklch(0.967 0.001 286.375)` | `oklch(0.274 0.006 286.033)` | Soft surface for secondary action / chip.    |
| `secondary-foreground` | `--secondary-foreground` | `oklch(0.21 0.006 285.885)` | `oklch(0.985 0 0)` | Ink on secondary.                              |
| `muted`            | `--muted`                | `oklch(0.97 0 0)`        | `oklch(0.269 0 0)`       | Disabled / informational surfaces.               |
| `muted-foreground` | `--muted-foreground`     | `oklch(0.556 0 0)`       | `oklch(0.708 0 0)`       | Secondary ink (labels, captions).                |
| `accent`           | `--accent`               | `oklch(0.97 0 0)`        | `oklch(0.269 0 0)`       | Hover surface in menus / lists.                  |
| `accent-foreground`| `--accent-foreground`    | `oklch(0.205 0 0)`       | `oklch(0.985 0 0)`       | Ink on accent.                                   |
| `destructive`      | `--destructive`          | `oklch(0.577 0.245 27.325)` (vermilion) | `oklch(0.704 0.191 22.216)` | Destructive action / error state.       |
| `border`           | `--border`               | `oklch(0.922 0 0)`       | `oklch(1 0 0 / 10%)`     | Default hairline rule.                           |
| `input`            | `--input`                | `oklch(0.922 0 0)`       | `oklch(1 0 0 / 15%)`     | Input field border.                              |
| `ring`             | `--ring`                 | `oklch(0.708 0 0)`       | `oklch(0.556 0 0)`       | Focus-visible outline (not primary — neutral ring per radix-mira). |

### §1.2 Sidebar sub-palette

The Toolbar rail and Copilot rail use the `sidebar-*` token scope (slightly distinct from main canvas, supports nested visual hierarchy):

| Token                       | Light                     | Dark                      |
|-----------------------------|---------------------------|---------------------------|
| `--sidebar`                 | `oklch(0.985 0 0)`        | `oklch(0.205 0 0)`        |
| `--sidebar-foreground`      | `oklch(0.145 0 0)`        | `oklch(0.985 0 0)`        |
| `--sidebar-primary`         | `oklch(0.511 0.262 276.966)` | `oklch(0.585 0.233 277.117)` |
| `--sidebar-primary-foreground` | `oklch(0.962 0.018 272.314)` | `oklch(0.962 0.018 272.314)` |
| `--sidebar-accent`          | `oklch(0.97 0 0)`         | `oklch(0.269 0 0)`        |
| `--sidebar-accent-foreground` | `oklch(0.205 0 0)`      | `oklch(0.985 0 0)`        |
| `--sidebar-border`          | `oklch(0.922 0 0)`        | `oklch(1 0 0 / 10%)`      |
| `--sidebar-ring`            | `oklch(0.708 0 0)`        | `oklch(0.556 0 0)`        |

### §1.3 Chart palette (5-stop indigo-violet ramp)

For Trace event sparklines, token-usage charts, and graph mini-map intensity:

| Token       | Value                          | Position on ramp   |
|-------------|--------------------------------|--------------------|
| `--chart-1` | `oklch(0.785 0.115 274.713)`   | Lightest, low-chroma indigo |
| `--chart-2` | `oklch(0.585 0.233 277.117)`   | Mid-light violet            |
| `--chart-3` | `oklch(0.511 0.262 276.966)`   | Mid-deep violet             |
| `--chart-4` | `oklch(0.457 0.24 277.023)`    | Same as `--primary`         |
| `--chart-5` | `oklch(0.398 0.195 277.366)`   | Deepest violet              |

### §1.4 Status semantics (locked here, NOT in CSS)

For node and run status, map to existing tokens (do not invent new ones for slice 1):

| Status      | Token                  | Where it shows                                   |
|-------------|------------------------|--------------------------------------------------|
| `idle`      | `border` + `muted-foreground` | Inactive node, never-run trace row.         |
| `running`   | `primary` (pulsing)    | Currently-executing node, live trace row.        |
| `success`   | TBD slice 3+ (likely emerald via chart palette extension or new `--success` token) | Compiled node, passed validator, success run. |
| `error`     | `destructive`          | Failed node, error trace, destructive button.    |
| `paused`    | TBD slice 3+ (likely amber) | HitL breakpoint, manual pause.              |
| `breakpoint`| TBD slice 3+           | Resume-able node after failure.                  |

> **Open**: `success` / `paused` / `breakpoint` need dedicated tokens. radix-mira preset only ships neutral + primary + destructive. We will add `--success` (emerald, slice 3) and `--warning` (amber, slice 3) as semantic tokens then; preset's chart-1..5 violet ramp covers visualization but not status semantics.

## §2 Typography

Two variable fonts loaded via `@fontsource-variable/*`:

| Stack     | Font                          | Tailwind class    | Token              | Use for                                 |
|-----------|-------------------------------|-------------------|--------------------|-----------------------------------------|
| Sans      | Inter Variable                | `font-sans` (default) | `--font-sans`  | Body, UI labels, headings, dialog copy. |
| Mono      | JetBrains Mono Variable       | `font-mono`       | `--font-mono`      | Code, file paths, node IDs, trace events, token counts, keyboard shortcuts. |

Heading and body use the same family (Inter); hierarchy comes from weight + size, not font swap. This matches Vercel / Linear / shadcn defaults and stays distinctive enough due to Inter Variable's weight axis.

**Size scale** (Tailwind 4 defaults; no override):

| Class      | Size (rem / px) | Line height | Use                                |
|------------|-----------------|-------------|------------------------------------|
| `text-xs`  | 0.75rem / 12px  | 1rem        | Trace events, badges, captions.    |
| `text-sm`  | 0.875rem / 14px | 1.25rem     | UI body, panel titles, button.     |
| `text-base`| 1rem / 16px     | 1.5rem      | Dialog body, paragraph text.       |
| `text-lg`  | 1.125rem / 18px | 1.75rem     | Subheading.                        |
| `text-xl`  | 1.25rem / 20px  | 1.75rem     | Section heading (Copilot welcome). |
| `text-2xl` | 1.5rem / 24px   | 2rem        | Page heading (Home / Dashboard).   |

**Weight axis**:

- `font-normal` (400): body
- `font-medium` (500): UI labels, button labels, panel titles
- `font-semibold` (600): emphasis, headings
- `font-bold` (700): rarely; reserved for Home page hero

**Numeric tracking**: Tailwind defaults (no `tracking-tight` / `tracking-wide` globally). Override only at component level for special cases (e.g., uppercase mini-labels use `tracking-wider`).

## §3 Radius, spacing, motion

### §3.1 Radius scale

Base `--radius: 0.625rem` (10px). Tailwind exposes a 7-step scale derived from it:

| Class         | Value                       | Use                                          |
|---------------|-----------------------------|----------------------------------------------|
| `rounded-sm`  | `calc(var(--radius) * 0.6)` ≈ 6px  | Inputs, small chips, kbd.            |
| `rounded-md`  | `calc(var(--radius) * 0.8)` ≈ 8px  | Buttons, badges, cards (small).      |
| `rounded-lg`  | `var(--radius)` = 10px              | Cards, dropdowns, popovers (default). |
| `rounded-xl`  | `calc(var(--radius) * 1.4)` ≈ 14px | Dialogs, sheets.                     |
| `rounded-2xl` | `calc(var(--radius) * 1.8)` ≈ 18px | Hero / Empty state containers.       |
| `rounded-3xl` | `calc(var(--radius) * 2.2)` ≈ 22px | Rarely; large media frames.          |
| `rounded-4xl` | `calc(var(--radius) * 2.6)` ≈ 26px | Reserved.                            |

### §3.2 Spacing

Tailwind 4 default 4px grid (`1` = 0.25rem). No override. Common values in Studio:

| Token | Pixels | Use                                       |
|-------|--------|-------------------------------------------|
| `1`   | 4px    | Icon-text gap, tight inline.              |
| `1.5` | 6px    | Small button gap.                         |
| `2`   | 8px    | Panel item vertical padding.              |
| `3`   | 12px   | Card padding, panel header gap.           |
| `4`   | 16px   | Dialog body padding, section break.       |
| `6`   | 24px   | Page padding, large section break.        |
| `8`   | 32px   | Hero spacing on Home / Empty state.       |

### §3.3 Motion

Animations come from `tw-animate-css` (auto-installed by `shadcn`). Use semantic class names, not raw `transition-*`:

| Token / Class              | Duration  | Easing       | Use                                  |
|----------------------------|-----------|--------------|--------------------------------------|
| `transition-colors`        | 150ms     | default      | Hover / focus color changes.         |
| `transition-all` (avoid)   | —         | —            | Only when truly multi-property.      |
| `animate-in slide-in-from-right` | 200ms | ease-out    | Copilot rail open, Sheet open.       |
| `animate-in fade-in`       | 150ms     | ease-out     | Dialog open, tooltip show.           |
| `animate-out fade-out`     | 150ms     | ease-in      | Dialog close, tooltip hide.          |

**Pulse for "running" node** (slice 3+ will define): `animate-pulse` is too generic; will define a custom keyframe `pulse-primary` that breathes the primary ring at 1.4s cycle.

### §3.4 Z-index scale (lock here)

Avoid raw `z-[N]` everywhere; use named layers:

| Layer       | Tailwind  | Use                                |
|-------------|-----------|------------------------------------|
| Base        | `z-0`     | Default content stack.             |
| Sticky      | `z-10`    | Sticky panel headers.              |
| Header bar  | `z-20`    | Top header above content.          |
| Dropdown    | `z-30`    | Dropdown / popover above header.   |
| Overlay     | `z-40`    | Floating Copilot button.           |
| Modal       | `z-50`    | Dialog / Sheet / AlertDialog.      |
| Toast       | `z-[60]`  | Sonner toaster, top of everything. |

## §4 Component recipes

> Filled per slice. Each component locks: variants, states, sizes, slot interactions, a11y notes.

- [ ] **§4.1 Button** (slice 2)
- [ ] **§4.2 Input / Textarea** (slice 2)
- [ ] **§4.3 Badge (status mapping)** (slice 2)
- [ ] **§4.4 Header / Top bar** (slice 3)
- [ ] **§4.5 Toolbar rail** (slice 3)
- [ ] **§4.6 Copilot right rail** (slice 4)
- [ ] **§4.7 Workspace shell + Resizable panels** (slice 5)
- [ ] **§4.8 Skill node (canvas, 6 states)** (slice 6)
- [ ] **§4.9 Trace timeline event row** (slice 7)
- [ ] **§4.10 Edge inspector popover** (slice 8)
- [ ] **§4.11 Prompt Inspector dialog (3 tabs)** (slice 8)
- [ ] **§4.12 Diff viewer + Judge report** (slice 9)
- [ ] **§4.13 Publish dialog** (slice 9)
- [ ] **§4.14 Home / Dashboard** (slice 10)

## §5 Layout shell

> Locked at slice 2. Implementation: `apps/studio/uikit/src/components/studio/workspace.tsx`.

### §5.1 Shell grid (vertical stack inside `h-screen w-screen`)

```
┌────────────────────────────────────────────────────────────────┐
│ Header                                              44px       │
├────┬─────────────────┬───────────────────────┬────────────────┤
│ T  │   Left          │                       │   Copilot      │
│ b  │   Panel         │     Canvas            │   rail         │
│ 48 │  (resizable,    │   (resizable,         │  (resizable,   │
│ px │   conditional)  │    always present)    │   togglable)   │
│    │                 │                       │                │
└────┴─────────────────┴───────────────────────┴────────────────┘
```

- **Header** — fixed `h-11` (44px), full width, never resizes. Owns project name, status badge, primary actions (Predict / Run), Copilot toggle, theme toggle, user menu.
- **Toolbar rail** — fixed `w-12` (48px), full height of body row, never resizes. Vertical icon nav for left-panel switching + global Add Node + Help.
- **Body row** — `flex-1 flex min-h-0`. Toolbar sits to the left of a `<ResizablePanelGroup direction="horizontal">`.

### §5.2 ResizablePanelGroup (horizontal, `autoSaveId="studio-workspace-h"`)

Three logical panels, conditionally mounted by stable `id` so `react-resizable-panels` can persist sizes across mount/unmount cycles:

| `id`        | `order` | `defaultSize` | `minSize` | `maxSize` | Mount condition         |
|-------------|---------|---------------|-----------|-----------|-------------------------|
| `left-panel`| 1       | 20            | 14        | 35        | `activePanel !== null`  |
| `canvas`    | 2       | 60            | 30        | —         | always                  |
| `copilot`   | 3       | 20            | 18        | 35        | `copilotOpen`           |

Sizes are **percent of the body row**, not pixels — `react-resizable-panels` API. Unit anchors:

- Left panel at `defaultSize=20` ≈ 280px on a 1440px desktop (matches v0's 280px initial). minSize floor ≈ 200px, maxSize ceiling ≈ 500px.
- Copilot rail at `defaultSize=20` ≈ 280px. minSize floor ≈ 250px, maxSize ceiling ≈ 500px.
- Canvas always takes whatever's left, minimum ≈ 420px.

### §5.3 Conditional mount contract

- Each `<ResizablePanel>` has a stable `id` + `order` so the group can rehydrate sizes after `left-panel` or `copilot` is unmounted/remounted.
- `<ResizableHandle>` is always rendered as a sibling **after** its preceding panel when both sides are mounted. Never render a handle adjacent to an unmounted panel.
- No `withHandle` decoration in v1 — the 1px border-themed handle (built into shadcn primitive) is sufficient at this density.

### §5.4 Toggle entry points (single source per toggle)

- **Left panel** is opened/closed via the Toolbar rail buttons (`assets`/`timeline`/`properties`/`editor`). Clicking the same active tool toggles it off. The Panel's own `X` close button calls `onPanelChange(null)`.
- **Copilot rail** is toggled via the Header right-side `Sparkles` button (replaces the v0 floating round button). The rail's own `X` button also closes it. Header button is `aria-pressed={copilotOpen}` and switches between `ghost`/`secondary` to indicate state.

### §5.5 Drag handle behavior

- Cursor: `col-resize` while hovering / dragging the handle (provided by primitive).
- Focus ring: shadcn `ring`/`ring-1` on `focus-visible` (primitive default).
- No body-wide cursor lock or `select-none` overlay needed — `react-resizable-panels` handles it internally.

## §6 Accessibility

> Locked at slice 4+.

- Focus rings use `ring` token (neutral, not primary) per radix-mira preset.
- All interactive surfaces hit-target ≥ 32px (Toolbar rail icons currently 32px = `size-8`).
- ARIA labels on icon-only buttons (already present in v0 Toolbar via `<Tooltip>`).
- Keyboard shortcuts surface in CommandPalette (`/`) and ShortcutsCheatSheet (`?`).

## §7 RTL / i18n

> Decided at slice 1: RTL is **disabled** in this version. `components.json` writes `rtl: false`. Tailwind logical properties (`ms-*` / `me-*` / `ps-*` / `pe-*`) still preferred over directional (`ml-*` / `mr-*`) so future RTL flip costs less.

## §8 Source of truth references

- Token CSS: `apps/studio/uikit/src/index.css`
- shadcn config: `apps/studio/uikit/components.json`
- Layout shell: `apps/studio/uikit/src/components/studio/workspace.tsx`
- 6-node workflow: `docs/studio/ux_workflow/0[0-6]_*.md`
- Audit log (24 items): in conversation `2026-05-10`, to be ported here at Phase A end as `§9 Resolved audit items` once each is fixed and locked.
