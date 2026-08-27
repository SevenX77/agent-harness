import enCanvas from "../locales/en/canvas.json"
import enCopilot from "../locales/en/copilot.json"
import enErrors from "../locales/en/errors.json"
import enSettings from "../locales/en/settings.json"
import enTrace from "../locales/en/trace.json"
import zhCnCanvas from "../locales/zh-CN/canvas.json"
import zhCnCopilot from "../locales/zh-CN/copilot.json"
import zhCnErrors from "../locales/zh-CN/errors.json"
import zhCnSettings from "../locales/zh-CN/settings.json"
import zhCnTrace from "../locales/zh-CN/trace.json"
import enWelcome from "../components/welcome/locales/en.json"
import zhCnWelcome from "../components/welcome/locales/zh-CN.json"
import enPanels from "../components/studio/panels/locales/en.json"
import zhCnPanels from "../components/studio/panels/locales/zh-CN.json"
import enStudioShell from "../components/studio/locales/en.json"
import zhCnStudioShell from "../components/studio/locales/zh-CN.json"
import enRuntimeGate from "../components/locales/en.json"
import zhCnRuntimeGate from "../components/locales/zh-CN.json"

/**
 * The explicit i18next namespace registry.
 *
 * Every namespace this app knows about is imported and listed here BY NAME —
 * no directory globbing, no filesystem scanning. `src/i18n.ts` reads this
 * object as-is for `resources` and derives its `ns` list from it, so
 * registering a namespace is a one-line addition to the two blocks below.
 *
 * Two storage conventions coexist by design, and this file is the seam
 * between them:
 *   - The five namespaces above (`settings`, `errors`, `canvas`, `copilot`,
 *     `trace`) are the original centralized bundles under `src/locales/`.
 *     They stay there — this file does not migrate them.
 *   - `welcome` is co-located with its module at
 *     `src/components/welcome/locales/{en,zh-CN}.json`, the pattern new
 *     modules follow going forward: when a module's code moves, its
 *     translations move with it instead of staying behind in a shared
 *     top-level directory that outlives the feature. `panels` (the
 *     Properties + I/O panels under `components/studio/panels/`) follows
 *     the same co-located pattern. `studioShell` covers the shell furniture
 *     that lives directly in `components/studio/` (not one of its
 *     sub-feature directories): the compile-error drawer, the left icon
 *     rail, the header's home button, and the Monaco editor panel's own
 *     header controls — four different components, one namespace, because
 *     they share that one directory rather than each owning a subfolder of
 *     their own. `runtimeGate` is the same idea one level up: RuntimeGate.tsx
 *     has no dedicated subdirectory either (it sits directly in
 *     `components/` next to its `runtime-gate-auto-restart.ts` helper), so
 *     its bundle sits at `components/locales/` rather than inventing a
 *     directory move this i18n pass has no reason to make.
 * Both shapes plug into i18next the same way — a namespace is just a name
 * plus one JSON bundle per language — so this registry is the only place
 * that needs to know where each namespace's files physically live.
 */
export const namespaceResources = {
  en: {
    settings: enSettings,
    errors: enErrors,
    canvas: enCanvas,
    copilot: enCopilot,
    trace: enTrace,
    welcome: enWelcome,
    panels: enPanels,
    studioShell: enStudioShell,
    runtimeGate: enRuntimeGate,
  },
  "zh-CN": {
    settings: zhCnSettings,
    errors: zhCnErrors,
    canvas: zhCnCanvas,
    copilot: zhCnCopilot,
    trace: zhCnTrace,
    welcome: zhCnWelcome,
    panels: zhCnPanels,
    studioShell: zhCnStudioShell,
    runtimeGate: zhCnRuntimeGate,
  },
} as const
