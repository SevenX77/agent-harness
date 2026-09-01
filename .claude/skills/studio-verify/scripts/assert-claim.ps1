# The gate the two launchers pass through before they kill and restart the ONE
# shared Studio app. That restart is the most destructive thing in this skill:
# done to a neighbour's running verification it wipes their session with no
# trace (2026-08-15, two agents on one debugged window). Same rule as
# lease-guard.mjs, which guards the scripts that DRIVE the window: prove the
# claim or do not touch it.
#
# CONTRACT - each launcher runs this file as a DEDICATED CHILD PROCESS
# (`powershell -NoProfile -ExecutionPolicy Bypass -File assert-claim.ps1`) and
# checks $LASTEXITCODE. Never dot-sourced, and never run in the launcher's own
# process. Its exit code is the whole answer:
#     0   this session holds cdp-9222; the caller may restart the app
#     4   the board answered no (not claimed / expired / held by someone else)
#     5   the guard could not ask the board at all (no Git Bash, no board script)
# Both non-zero codes refuse - failing closed is the point - but they are two
# different problems and used to be reported as one: 4 is discipline (go claim
# the board), 5 is environment (fix this machine), and printing "you do not hold
# cdp-9222" at a session that did hold it sent people looking in the wrong
# place. A refusal ALSO ends the process; see below.
#
# WHY A CHILD PROCESS, AND WHY IT STILL ENDS THAT PROCESS HARD
#   Until 2026-08-31 the launchers DOT-SOURCED this file and it refused with
#   `exit 4`. Measured on Windows PowerShell 5.1.26100.9168: `exit` inside a
#   dot-sourced file ends that file only - the caller runs on and the process
#   exits 0. All three dot-source spellings behave identically (literal path,
#   "$PSScriptRoot\..." string, parenthesised expression), so this was not a
#   typo at one call site. The launchers therefore printed the refusal and
#   restarted the shared app anyway: the guard was decoration, and SKILL.md
#   described an enforcement that did not exist.
#   The first repair over-corrected: it kept the guard in the launcher's own
#   process and refused with [Environment]::Exit, on the theory that a verdict
#   no calling convention can swallow is strictly safer. It is not. Whoever
#   calls the launcher from an EXISTING PowerShell session (`& launch-studio-
#   cdp.ps1` from a prompt or ISE) loses that whole session, and .NET documents
#   that Environment.Exit skips active finally blocks, so the caller cannot even
#   clean up. Measured: with the guard in-process the outer session dies; as a
#   child process it prints its refusal, the launcher aborts with the code, and
#   the session survives.
#   So the boundary moved instead of the mechanism. [Environment]::Exit(N) here
#   now ends ONLY this guard's own child process - which is exactly the
#   invariant lease-guard.mjs has always had: process.exit(4) ends the process
#   that was about to do the driving, and nothing above it. The launcher reads
#   the exit code and stops itself. Nothing a refusal touches outlives the
#   guard's own process.
#   The worry that motivated the over-correction - a future launcher forgetting
#   to check the code - is answered by a test rather than by blast radius:
#   tests/guard-selftest.sh EXECUTES both real launchers, so a missing check
#   shows up as a FAIL.
#
# ASCII ONLY, DELIBERATELY. .gitattributes stores .ps1 without a BOM (repo
# policy: UTF-8 without signature), and Windows PowerShell 5.1 decodes a
# BOM-less .ps1 as the system ANSI codepage - cp936 on this machine. Measured
# 2026-08-31: a U+2014 em dash in a string literal decodes to a GBK lead byte
# that swallows the closing quote, and the whole file fails to PARSE
# ("missing string terminator"). Non-ASCII here does not merely look wrong, it
# can break the guard. Keep every literal and comment in this file ASCII;
# non-ASCII coming from the board is decoded explicitly (see Get-Content below).
$ErrorActionPreference = 'Stop'

$Resource = 'cdp-9222'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$BoardScript = Join-Path $RepoRoot 'scripts\wt-board.sh'
# The launchers are started DETACHED and hidden (SKILL.md step 2), so the
# console this writes to is nobody's screen. Without a file on disk a refusal is
# indistinguishable from "the app is still booting" - failing closed has to be
# diagnosable or the next operator just retries harder.
$GuardLog = Join-Path $env:TEMP 'studio-verify-guard.log'

function Deny {
  param([int]$Code, [string]$Reason, [string[]]$Detail = @())
  $lines = @("refusing to restart the app: $Reason") + $Detail
  # Printed with whatever encoding the console already has. Setting
  # [Console]::OutputEncoding would render the board's non-ASCII (its check
  # mark, a Chinese --note) faithfully, but SetConsoleOutputCP applies to the
  # whole CONSOLE - shared with the shell that called the launcher - and
  # [Environment]::Exit below skips finally blocks, so it could not be put back.
  # A guard does not get to leave the caller's terminal reconfigured; the log
  # file below is the faithful UTF-8 copy.
  foreach ($line in $lines) { Write-Host $line }
  try {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    @("[$stamp] exit $Code") + $lines | Out-File -FilePath $GuardLog -Encoding utf8 -Append
  } catch {
    # A log we cannot write must not turn a refusal into a crash: the refusal
    # itself is carried by the exit code below, not by the log.
    Write-Host "  (could not append to $GuardLog)"
  }
  [Environment]::Exit($Code)
}

$ClaimHelp = @(
  '',
  '  claim it first (and set a session id the board can name you by):',
  '    export WT_BOARD_AGENT=<your session id>',
  "    scripts/wt-board.sh claim $Resource --ttl 3600 --note `"verifying PR #NNN`"",
  '  reading is always allowed without a claim: cdp.mjs / shot.mjs / console.mjs'
)

# Git for Windows' bash, resolved by ABSOLUTE PATH first and by PATH only as a
# fallback. Two reasons, both measured:
#   - a detached `Start-Process powershell` does not necessarily carry Git Bash
#     on PATH, so a PATH-only lookup made the guard refuse with "you do not hold
#     cdp-9222" at a session that did hold it (2026-08-31);
#   - C:\Windows\System32\bash.exe is the WSL launcher, and WSL cannot resolve
#     the Windows path this guard hands to wt-board.sh, so a PATH hit there is
#     worse than no hit at all. It is skipped by rule, not by luck.
# Nothing needs to be done about `git` itself: Git Bash prepends its own
# /mingw64/bin:/usr/bin to PATH whatever the parent's PATH was, so wt-board.sh
# finds git even when the launcher inherited an empty PATH (measured the same
# day, which is why there is no PATH fixup here).
function Resolve-GitBash {
  $candidates = @()
  foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
    if ($base) {
      $candidates += (Join-Path $base 'Git\bin\bash.exe')
      $candidates += (Join-Path $base 'Programs\Git\bin\bash.exe')
    }
  }
  # Whatever git this machine actually uses knows where its own bash lives.
  $git = Get-Command git.exe -ErrorAction SilentlyContinue
  if ($git -and $git.Source) {
    $candidates += (Join-Path (Split-Path (Split-Path $git.Source -Parent) -Parent) 'bin\bash.exe')
  }
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  }
  $onPath = Get-Command bash.exe -ErrorAction SilentlyContinue
  $system32 = Join-Path $env:SystemRoot 'System32'
  if ($onPath -and $onPath.Source -and
      -not $onPath.Source.StartsWith($system32, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $onPath.Source
  }
  return $null
}

$bash = Resolve-GitBash
if (-not $bash) {
  Deny 5 "cannot ask the runtime resource board - no Git Bash on this machine." @(
    '  probed: %ProgramFiles%\Git\bin\bash.exe, %LOCALAPPDATA%\Programs\Git\bin\bash.exe,',
    '          <dir of git.exe>\..\bin\bash.exe, then bash.exe on PATH',
    '          (System32\bash.exe is the WSL launcher and is deliberately ignored)',
    '  this is an environment problem, not a claim problem: install Git for Windows',
    '  or run the launcher from a shell whose PATH has its bash.'
  )
}
if (-not (Test-Path -LiteralPath $BoardScript -PathType Leaf)) {
  Deny 5 "cannot ask the runtime resource board - $BoardScript is missing." @(
    '  the guard locates the repo root four levels up from its own directory;',
    '  a copy of this script moved elsewhere cannot find the board.'
  )
}

# Start-Process -Wait -PassThru rather than the call operator: on Windows
# PowerShell 5.1 redirecting a native command's stderr with `2>&1` wraps every
# line in a NativeCommandError and reports failure even on exit 0, so the exit
# code and the diagnostic text have to be collected out of band.
# -WorkingDirectory is load-bearing: wt-board.sh locates the board through `git
# rev-parse`, and with a cwd outside the repo (a detached launcher inherits
# whatever cwd it was spawned in) it dies with "not a git repository" - a
# refusal for a reason that has nothing to do with the claim.
#
# The argument list is ONE string with the script path quoted BY HAND. Windows
# PowerShell 5.1 joins an -ArgumentList array with spaces and adds no quoting of
# its own, so a repo living under a path with a space (C:\Users\Jane Doe\...)
# reached bash as two fragments: measured, bash reported
# "...\scratchpad\probe\space: No such file or directory". Forward slashes
# because a quoted Windows path ending in a backslash would escape the closing
# quote under MSVC-style command-line parsing; MSYS bash takes D:/... happily.
$boardArgument = '"' + $BoardScript.Replace('\', '/') + '"' + " holds $Resource"
$stdout = [System.IO.Path]::GetTempFileName()
$stderr = [System.IO.Path]::GetTempFileName()
try {
  $probe = Start-Process -FilePath $bash -ArgumentList $boardArgument `
    -WorkingDirectory $RepoRoot -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  $boardExit = $probe.ExitCode
  $boardSays = @()
  foreach ($stream in @($stderr, $stdout)) {
    if (Test-Path -LiteralPath $stream) {
      # -Encoding UTF8 because wt-board.sh writes UTF-8; without it PowerShell
      # would decode the board's own words with the ANSI codepage.
      $boardSays += @(Get-Content -LiteralPath $stream -Encoding UTF8 |
                      Where-Object { $_.Trim() -ne '' })
    }
  }
} finally {
  Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
}

# 126/127 are the shell's own "could not execute / not found" codes, which
# wt-board.sh itself never returns (it answers 0 or 1). Seeing one means bash
# could not run the board script at all - an environment failure wearing the
# board's exit code. Reporting that as 4 is what made a broken argument list
# look like "you did not claim it", so the two are separated here.
if ($boardExit -eq 126 -or $boardExit -eq 127) {
  Deny 5 "cannot ask the runtime resource board - bash could not execute it (exit $boardExit)." (
    @($boardSays | ForEach-Object { "  $_" }) + @(
      '  the board script exists but bash could not run it; this is an',
      '  environment problem, not a claim problem.'
    )
  )
}

# $null (the board never reported a code) counts as a refusal: an unanswerable
# question is not permission to restart someone else's window.
if ($null -eq $boardExit -or $boardExit -ne 0) {
  Deny 4 "this session does not hold $Resource." (@($boardSays | ForEach-Object { "  $_" }) + $ClaimHelp)
}
exit 0
