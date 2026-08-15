# Relaunch the Studio desktop app WITHOUT the CDP debug port — the mandatory
# closing step of a verification session. After the app is up, verify the port
# is really gone: curl http://127.0.0.1:9222/json/version must return 000.
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = ""
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\.."))
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1 *> "$env:TEMP\studio-dev-clean.log"
