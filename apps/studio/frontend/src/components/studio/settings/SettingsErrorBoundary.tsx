// Settings-tab render boundary: the generic ErrorBoundary under a settings-specific
// name, so one crashing tab shows a fallback card instead of a white screen. All
// behaviour lives in ErrorBoundary; this is just the named seam the settings shell
// wraps each tab with.
export { ErrorBoundary as SettingsErrorBoundary } from "@/components/ErrorBoundary"
