# Dot-source guard for the launchers: they kill and restart the ONE shared app,
# which is the most destructive thing in this skill — doing it to a neighbour's
# running verification wipes their session with no trace. Same rule as
# lease-guard.mjs and the same failure mode behind it (2026-08-15, two agents on
# one debugged window): prove the claim or do not touch it.
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
& bash (Join-Path $RepoRoot "scripts/wt-board.sh") holds cdp-9222
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "refusing to restart the app: this session does not hold cdp-9222."
  Write-Host "  claim it first (and set a session id the board can name you by):"
  Write-Host "    export WT_BOARD_AGENT=<your session id>"
  Write-Host "    scripts/wt-board.sh claim cdp-9222 --ttl 3600 --note `"点验 PR #NNN`""
  exit 4
}
