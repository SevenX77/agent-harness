# The gate the two launchers pass through before they kill and restart the ONE
# shared Studio app. That restart is the most destructive thing in this skill:
# done to a neighbour's running verification it wipes their session with no
# trace (2026-08-15, two agents on one debugged window). Same rule as
# lease-guard.mjs, which guards the scripts that DRIVE the window: prove the
# claim or do not touch it.
#
# CONTRACT - this file is CALLED, never dot-sourced, and its exit code is the
# whole answer:
#     0   this session holds cdp-9222; the caller may restart the app
#     4   the board answered no (not claimed / expired / held by someone else)
#     5   the guard could not ask the board at all (no Git Bash, no board script)
# Both non-zero codes refuse - failing closed is the point - but they are two
# different problems and used to be reported as one: 4 is discipline (go claim
# the board), 5 is environment (fix this machine), and printing "you do not hold
# cdp-9222" at a session that did hold it sent people looking in the wrong
# place. A refusal ALSO ends the process; see below.
#
# WHY A REFUSAL ENDS THE PROCESS INSTEAD OF ONLY RETURNING 4
#   Until 2026-08-31 the launchers DOT-SOURCED this file and it refused with
#   `exit 4`. Measured on Windows PowerShell 5.1.26100.9168: `exit` inside a
#   dot-sourced file ends that file only - the caller runs on and the process
#   exits 0. All three dot-source spellings behave identically (literal path,
#   "$PSScriptRoot\..." string, parenthesised expression), so this was not a
#   typo at one call site. The launchers therefore printed the refusal and
#   restarted the shared app anyway: the guard was decoration, and SKILL.md
#   described an enforcement that did not exist.
#   [Environment]::Exit(N) is the one form no calling convention can swallow -
#   not dot-sourcing, not `&`, not try/catch, not trap - and it is the direct
#   analogue of what already works in lease-guard.mjs: process.exit(4) ends the
#   same process that would otherwise do the damage. The launchers' own
#   $LASTEXITCODE check is kept as the readable contract and as the second net
#   if this line is ever softened back into `exit`.
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
  # Only on the refusal path, and only because this process is about to end:
  # the board's own output carries non-ASCII (its check mark, a Chinese --note)
  # and the inherited console codepage would replace it with question marks.
  # Never done on the allow path - SetConsoleOutputCP is shared with children,
  # and the app the launcher then starts must keep the console it expects.
  try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
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
$stdout = [System.IO.Path]::GetTempFileName()
$stderr = [System.IO.Path]::GetTempFileName()
try {
  $probe = Start-Process -FilePath $bash `
    -ArgumentList @($BoardScript, 'holds', $Resource) `
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

# $null (the board never reported a code) counts as a refusal: an unanswerable
# question is not permission to restart someone else's window.
if ($null -eq $boardExit -or $boardExit -ne 0) {
  Deny 4 "this session does not hold $Resource." (@($boardSays | ForEach-Object { "  $_" }) + $ClaimHelp)
}
exit 0
