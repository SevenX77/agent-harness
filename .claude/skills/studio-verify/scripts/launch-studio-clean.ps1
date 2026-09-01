# Relaunch the Studio desktop app WITHOUT the CDP debug port - the mandatory
# closing step of a verification session. After the app is up, verify the port
# is really gone: curl http://127.0.0.1:9222/json/version must return 000.
# ASCII only: Windows PowerShell 5.1 decodes a BOM-less .ps1 with the system
# ANSI codepage, and non-ASCII can break the parse (see assert-claim.ps1).

# 'Stop' for the guard only: a guard that cannot even run (renamed, syntax
# error, throwing) must abort the relaunch instead of printing a red line and
# restarting the shared app anyway.
$ErrorActionPreference = 'Stop'
# The board guard is CALLED and its exit code checked - the standard PowerShell
# pairing for "run a script, then act on its result". It must NOT be
# dot-sourced: `exit` inside a dot-sourced file ends only that file, so until
# 2026-08-31 this launcher printed the refusal and restarted the shared app
# without holding cdp-9222 - the 2026-08-15 accident, re-enabled by a calling
# convention. assert-claim.ps1 now also ends the process itself on refusal, so
# this check is the readable contract rather than the only line of defence.
# Exit codes: 4 = the board says this session does not hold cdp-9222,
# 5 = the guard could not ask the board (see assert-claim.ps1).
& (Join-Path $PSScriptRoot 'assert-claim.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Back to the default before the app starts: cargo and Vite write plenty to
# stderr, and under 'Stop' the first such line would abort the launch.
$ErrorActionPreference = 'Continue'

$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = ""
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\.."))
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1 *> "$env:TEMP\studio-dev-clean.log"
