# Launch the Studio desktop app WITH the CDP debug port (9222) for verification.
# Invoke DETACHED (Start-Process) so background-task shell reaping cannot kill
# the console child tree. Repo root is derived from this file's location:
# .claude/skills/studio-verify/scripts/ -> four levels up.
# ASCII only: Windows PowerShell 5.1 decodes a BOM-less .ps1 with the system
# ANSI codepage, and non-ASCII can break the parse (see assert-claim.ps1).

# 'Stop' for the guard only: a guard that cannot even be started must abort the
# launch instead of printing a red line and restarting the shared app anyway.
$ErrorActionPreference = 'Stop'
# The board guard runs as its OWN CHILD PROCESS and this launcher acts on its
# exit code - the standard PowerShell pairing for "run a script, then act on its
# result". Two things it must not be:
#   - dot-sourced: `exit` inside a dot-sourced file ends only that file, so
#     until 2026-08-31 this launcher printed the refusal and restarted the
#     shared app anyway - the 2026-08-15 accident, re-enabled by a calling
#     convention;
#   - run in THIS process: the guard refuses by ending its process, and anyone
#     who calls this launcher from an existing PowerShell session would lose
#     that whole session (and its finally blocks) instead of just the launch.
# A child process gives the refusal teeth without that blast radius.
# Exit codes: 4 = the board says this session does not hold cdp-9222,
# 5 = the guard could not ask the board (see assert-claim.ps1).
#
# The interpreter is resolved ABSOLUTELY rather than through PATH - the same
# lesson the guard learned about bash, and the third time a PATH assumption has
# bitten this chain: a detached launcher's PATH is not the developer's shell's.
# This host's own executable is the right one by construction, whatever it is
# called or wherever it lives.
$interpreter = (Get-Process -Id $PID).Path
if (-not $interpreter) { $interpreter = Join-Path $PSHOME 'powershell.exe' }
& $interpreter -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'assert-claim.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Back to the default before the app starts: cargo and Vite write plenty to
# stderr, and under 'Stop' the first such line would abort the launch.
$ErrorActionPreference = 'Continue'

$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=9222"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\.."))
# Same absolute interpreter as the guard, for the same reason: this script runs
# detached, and it must not need PATH to find the shell it was started by.
& $interpreter -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1 *> "$env:TEMP\studio-dev-cdp.log"
