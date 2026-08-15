# Launch the Studio desktop app WITH the CDP debug port (9222) for verification.
# Invoke DETACHED (Start-Process) so background-task shell reaping cannot kill
# the console child tree. Repo root is derived from this file's location:
# .claude/skills/studio-verify/scripts/ -> four levels up.
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=9222"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\.."))
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1 *> "$env:TEMP\studio-dev-cdp.log"
