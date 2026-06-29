param(
  [int]$SidecarPort = 8787
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $RepoRoot "apps/studio/tauri/scripts/dev_studio.js"

$env:STUDIO_SIDECAR_PORT = "$SidecarPort"
node $Launcher --port $SidecarPort
