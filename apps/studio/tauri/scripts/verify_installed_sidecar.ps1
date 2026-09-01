<#
.SYNOPSIS
  Installs the freshly built Windows package and proves the installed app finds
  the files it resolves at runtime inside its own install directory.

.DESCRIPTION
  A Tauri release build that is missing its resources does not fail loudly. When
  the packaged resource root has no `vendor/`, `resource_root_for_runtime_mode`
  (apps/studio/tauri/src/sidecar.rs) falls back to `default_tauri_dir()`, which
  is `env!("CARGO_MANIFEST_DIR")` -- the absolute path of the source tree ON THE
  MACHINE THAT COMPILED IT, baked into the binary. That path still exists on the
  builder's own box, so a broken package launches perfectly there and fails only
  for a user who has no `D:\coding\agent-harness\...` directory.

  Building an installer therefore proves nothing on its own. This script closes
  that gap by installing the artifact and asserting that everything the app
  resolves from its resource root -- the sidecar's interpreter, vendored
  site-packages and backend, plus the one-click CLI installer script -- lands
  UNDER the install directory. It is the difference between "the bundler
  produced a file" and "the file installs a working app".

  The install target is passed explicitly with NSIS's `/D=`, into a throwaway
  directory, for two reasons. It keeps the check hermetic: Tauri's NSIS script
  reuses whatever `InstallLocation` a previous install recorded in the registry,
  so without `/D=` the result depends on leftovers from earlier runs. And it
  keeps the check safe on a developer's machine: it can never overwrite a real
  installation of the app.

  Written to the Windows PowerShell 5.1 subset (no ternary, no `??`, no
  `-AsHashtable`) so it runs both under CI's `pwsh` and under the stock
  `powershell.exe` on a dev box, where pwsh may not be installed at all.
#>
[CmdletBinding()]
param(
    # Defaults to the bundle directory `cargo tauri build --bundles nsis` writes.
    [string] $BundleDir = (Join-Path $PSScriptRoot '..\target\release\bundle\nsis')
)

$ErrorActionPreference = 'Stop'

function Fail([string] $message) {
    Write-Host "FAIL: $message" -ForegroundColor Red
    exit 1
}

$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)
Write-Host "Looking for an installer under $BundleDir"

$setup = Get-ChildItem -Path $BundleDir -Filter '*-setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $setup) { Fail "no *-setup.exe in $BundleDir -- the bundler produced no installer" }
Write-Host ("Installer: {0} ({1:N1} MB)" -f $setup.Name, ($setup.Length / 1MB))

$installDir = Join-Path ([System.IO.Path]::GetTempPath()) 'studio-package-check'
if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }

# NSIS takes everything after `/D=` literally to the end of the command line, so
# the switch must come last and the path must NOT be quoted -- even when it
# contains spaces. That rules out passing the switches as separate list
# elements: PowerShell quotes any element containing a space when it assembles
# the command line, and NSIS would then read the quote as part of the directory
# name. One pre-joined string is handed over instead.
$arguments = "/S /D=$installDir"
Write-Host "Installing silently into $installDir"
$process = Start-Process -FilePath $setup.FullName `
    -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -ne 0) { Fail "installer exited with code $($process.ExitCode)" }

if (-not (Test-Path $installDir)) {
    Fail "installer reported success but nothing was written to $installDir"
}

$exe = Get-ChildItem -Path $installDir -Filter '*.exe' | Select-Object -First 1
if (-not $exe) { Fail "no executable in $installDir" }
Write-Host "Installed: $($exe.Name)"

# The three paths the sidecar derives from its resource root, named exactly as
# sidecar.rs builds them: `vendor/python/<triple>/python.exe`,
# `vendor/site-packages`, and `vendor/backend`.
#
# On Windows the resource root IS the install directory -- Tauri's NSIS installer
# lays bundled resources out beside the executable, with no `resources/`
# subdirectory (that is a macOS `.app` shape). Getting this wrong is not a
# theoretical risk: the first version of this script looked under `resources\`,
# found nothing, and reported a perfectly good package as broken.
#
# The fourth entry is not the sidecar's. The one-click CLI installer button
# resolves ITS script the same way -- `cli_installer_script()` in
# apps/studio/tauri/src/lib.rs looks under
# `<resource root>/vendor/resources/scripts/` -- and it fails differently from
# the other three: a missing sidecar is an app that will not start, while a
# missing installer script leaves a button on screen that is guaranteed to
# answer `installer script missing at ...` the moment anyone presses it. That
# was every packaged build for an unknown length of time, and nothing in this
# check could see it, because the check only ever asked about the sidecar
# (ledger D1). What both questions have in common is the one this script
# exists to ask: does the INSTALLED app find the files it resolves at runtime.
$required = [ordered]@{
    'python interpreter'     = Join-Path $installDir 'vendor\python\x86_64-pc-windows-msvc\python.exe'
    'vendored site-packages' = Join-Path $installDir 'vendor\site-packages'
    'vendored backend'       = Join-Path $installDir 'vendor\backend'
    'CLI installer script'   = Join-Path $installDir 'vendor\resources\scripts\install-claude-code-wsl.ps1'
}

$missing = @()
foreach ($name in $required.Keys) {
    if (Test-Path $required[$name]) {
        Write-Host "  OK   $name"
    } else {
        Write-Host "  MISS $name -> $($required[$name])" -ForegroundColor Red
        $missing += $name
    }
}
if ($missing.Count -gt 0) {
    Fail ("the installed app is missing: {0}. It would still start on the machine that built it, because sidecar.rs falls back to the compile-time source path -- which is exactly the failure this check exists to catch." -f ($missing -join ', '))
}

# The point of the whole exercise: every resolved path is inside the install
# directory, not somewhere on the build machine.
foreach ($name in $required.Keys) {
    $resolved = (Resolve-Path $required[$name]).Path
    if (-not $resolved.StartsWith($installDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        Fail "$name resolved to $resolved, outside the install directory $installDir"
    }
}

# `import graph_agent` is what the sidecar does first. A site-packages directory
# that exists but holds no engine passes every check above and still cannot run.
#
# Printing where the import RESOLVED, rather than just that it worked, is what
# makes this the real test: it is the same question the whole script asks -- did
# the app load its own bundled copy, or something that happens to be on this
# machine -- answered by the interpreter itself.
$env:PYTHONPATH = $required['vendored site-packages']
$probe = 'import graph_agent, graph_agent_gateway; print(graph_agent.__file__)'
$resolvedEngine = & $required['python interpreter'] -c $probe
if ($LASTEXITCODE -ne 0) {
    Fail "the installed interpreter cannot import the vendored engine (see the traceback above)"
}
if (-not $resolvedEngine.StartsWith($installDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail "the installed interpreter imported graph_agent from $resolvedEngine, outside the install directory"
}
Write-Host "  OK   installed interpreter imports graph_agent from $resolvedEngine"

# The installed app must be able to say WHICH engine it carries, not only that it
# carries one. On a developer's box the launcher gate answers that by comparing
# the snapshot against the working tree (`ensure_vendor.js`); a user has no
# working tree, so the stamp `build_vendor.py` writes into the snapshot is the
# only thing that can name the sources the shipped engine came from -- in the
# app's own logs, and in any bug report about it. Asserting it here is what keeps
# the release chain from quietly shipping an anonymous snapshot: this job runs a
# real `tauri build`, so a stamp missing from the package means the build step
# that writes it did not run.
$stampPath = Join-Path $required['vendored site-packages'] 'vendor-stamp.json'
if (-not (Test-Path $stampPath)) {
    Fail "the installed snapshot carries no vendor-stamp.json, so nothing can say which engine sources it holds"
}
$stamp = Get-Content $stampPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($stamp.source_digest)) {
    Fail "vendor-stamp.json names no source_digest, so it attests to nothing"
}
Write-Host ("  OK   snapshot stamped: sources {0}, built {1}, python {2}" -f `
    $stamp.source_digest.Substring(0, 12), $stamp.built_at, $stamp.python_version)

# Nothing a user downloads should be an archive the BUILD needed. `vendor/` is
# shipped whole (`bundle.resources: vendor/**/*`), so anything left in it rides
# along: the download cache used to sit at `vendor/downloads/` and put 48.9 MB
# of .tar.gz/.tar.xz into a 154.7 MB installer -- a third of it, for files
# nothing opens after the build (ledger D4). The cache now lives outside the
# payload; this makes that stay true.
$archives = Get-ChildItem $installDir -Recurse -File -Include '*.tar.gz', '*.tar.xz', '*.tar.bz2' -ErrorAction SilentlyContinue
if ($archives) {
    foreach ($a in $archives) {
        Write-Host ("  SHIPPED {0} ({1:N1} MB)" -f $a.FullName.Substring($installDir.Length), ($a.Length / 1MB)) -ForegroundColor Red
    }
    Fail "the installer carries build-cache archives. They are inputs the build already consumed; shipping them makes every user download them again for nothing."
}
Write-Host "  OK   no build-cache archives shipped"

Write-Host ""
Write-Host "PASS: the installed app resolves its sidecar inside $installDir" -ForegroundColor Green

# Put the machine back. On CI the runner is thrown away either way, but a
# developer runs this on the box they work on, and an install that stays behind
# leaves half a gigabyte in TEMP plus an uninstall entry in the registry
# pointing at a directory that will eventually vanish. Best-effort on purpose:
# the verdict above is already decided, and a stubborn uninstaller must not be
# able to turn a passing check into a failing one.
$uninstaller = Join-Path $installDir 'uninstall.exe'
if (Test-Path $uninstaller) {
    try {
        Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -ErrorAction Stop
    } catch {
        Write-Host "note: could not run the uninstaller ($($_.Exception.Message))"
    }
}
if (Test-Path $installDir) {
    Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
}
