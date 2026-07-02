param(
  [int]$SidecarPort = 8787
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $RepoRoot "apps/studio/tauri/scripts/dev_studio.js"

# Cross-platform bottom line (docs/development/CROSS_PLATFORM.md): every
# Python child in the dev tree writes UTF-8, not the locale codepage.
$env:PYTHONUTF8 = "1"
$env:STUDIO_SIDECAR_PORT = "$SidecarPort"
node $Launcher --port $SidecarPort
