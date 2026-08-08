import type { ComponentProps } from 'react'
import Editor from '@monaco-editor/react'

export type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
export type MonacoEditor = Parameters<EditorOnMount>[0]
export type MonacoApi = Parameters<EditorOnMount>[1]

// NOTE: there is deliberately NO realtime-lint banner/strip component here.
// The realtime lint surface is inline Monaco markers scoped to the OPEN file
// (`applyLintMarkers(filePath)` in LazyMonacoPanel), plus the canvas node badge
// and Properties field tooltip; the full aggregated list lives in the manual
// Compile drawer (CompileErrorDrawer). A large in-editor banner was removed in
// PR #234 ("real-time lint marks context only, not a global panel mid-edit",
// compile-lint F1) and must not be reintroduced — see the LazyMonacoPanel test
// that locks its absence.
