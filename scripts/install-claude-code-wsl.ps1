<#
.SYNOPSIS
  One-shot(ish) bootstrap for Studio's code assistant menu: WSL2 + Ubuntu +
  systemd + tmux + claude CLI + Codex CLI + ah, with Windows'
  proxy/timezone/locale mirrored in, so the interactive master ah spawns can
  reach the network and don't sit behind a locale/tz mismatch.

.DESCRIPTION
  ah's own installer only installs the `ah`/`ahd` binaries themselves — it
  does not provision WSL2, tmux, provider CLIs, or auth (verified via
  `ah doctor`, which only diagnoses; there is no `ah install`/`--fix`). This
  script covers everything ah's installer does NOT, so the launcher Studio's
  assistant menu drives (apps/studio/tauri/src/lib.rs) has a working `ah` plus
  provider CLIs waiting for it inside WSL.

  Ownership split (this script is deliberately in two parts):

    PART A — ah runtime prerequisites (WSL2, distro, systemd, mirrored
      networking, tz/locale/proxy, tmux). These architecturally belong in
      ah's own installer; we've filed that as a handoff requirement
      (docs/handoffs/ah-installer-provisioning-and-master-defaults.md, Req 1).
      Until ah owns them, this script provisions them as a TEMPORARY BRIDGE —
      when ah's installer provisions its own runtime, delete PART A and let
      PART B's `ah` install pull it in.

    PART B — Studio's own provider layer (install ah, install the claude and
      Codex CLIs, subscription auth). This is Studio's permanent responsibility
      and stays here regardless of ah — the provider CLI and the user's login
      are explicitly NOT ah's job (handoff Non-Goals).

  Idempotent — safe to re-run at any point; each step checks before acting.

  Two steps are genuinely gated behind one-time HUMAN action and cannot be
  scripted around (OS security boundaries, not a shortcut we skipped):
    1. Installing the WSL2 feature requires a reboot before WSL is usable.
    2. The first-ever claude/Codex login is an interactive OAuth flow (opens
       your browser) — there is no non-interactive way to mint that session.
  When the script hits either gate, it prints exactly what to do and exits
  cleanly (not an error) — re-run the same command afterward to continue.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-claude-code-wsl.ps1
#>

param(
  [string]$Distro = "Ubuntu-24.04"
)

$ErrorActionPreference = "Stop"

function Write-Part($msg) { Write-Host "`n########## $msg ##########" -ForegroundColor Magenta }
function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "    already done: $msg" -ForegroundColor DarkGray }
function Write-Warn2($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }

function Test-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Wsl {
  # No 2>&1 here on purpose: in PS 5.1, redirecting a native command's stderr
  # wraps each line as a NativeCommandError and (with $ErrorActionPreference
  # = "Stop") throws even on informational stderr output — regardless of the
  # caller's own -AllowFail intent. Native stderr is already visible to the
  # user without redirection; only stdout needs capturing here.
  param([string[]]$WslArgs, [switch]$AllowFail)
  $out = & wsl.exe @WslArgs
  if ($LASTEXITCODE -ne 0 -and -not $AllowFail) {
    throw "wsl.exe $($WslArgs -join ' ') failed (exit $LASTEXITCODE)"
  }
  return $out
}

# Two things baked into every in-distro command:
#  - PATH: non-interactive `bash -lc` doesn't source ~/.bashrc, so claude/ah
#    (under ~/.local/bin / ~/.cargo/bin) aren't on PATH unless we prepend it
#    (a missing prefix at one call site is what made the claude-CLI presence
#    check misfire on the first real run of this script).
#  - `cd "$HOME"`: run every ah command from a NEUTRAL cwd, never the ambient
#    Windows dir this script was launched from. ah otherwise surfaces/records
#    the launch cwd as a project (`ah doctor` -> `permissions:cwd - <repo>`,
#    and bare ah commands persist per-cwd daemon state) — filed upstream as
#    handoff Req 3; keeping cwd neutral here avoids binding ah to the repo.
$PathPrefix = 'export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"; cd "$HOME"; '

function Invoke-InDistro {
  param([string]$Bash, [switch]$AllowFail)
  return Invoke-Wsl -WslArgs @("-d", $Distro, "-u", "root", "-e", "bash", "-lc", ($PathPrefix + $Bash)) -AllowFail:$AllowFail
}

function Test-ProviderCliInteropHijack {
  param([string]$Command)
  $bash = @'
cmd_path="$(command -v __COMMAND__ 2>/dev/null || true)"
entry="$HOME/.local/bin/__COMMAND__"
for candidate in "$cmd_path" "$entry"; do
  [ -n "$candidate" ] || continue
  [ -e "$candidate" ] || [ -L "$candidate" ] || continue
  target="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
  case "$target" in
    /mnt/*)
      printf 'HIJACKED %s -> %s\n' "$candidate" "$target"
      exit 0
      ;;
  esac
done
printf 'OK\n'
'@.Replace("__COMMAND__", $Command)
  return Invoke-InDistro $bash -AllowFail
}

function Test-ClaudeReusableAuth {
  $bash = @'
cred="$HOME/.claude/.credentials.json"
if [ -f "$cred" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$cred" <<'PY'
import json
import sys

try:
    oauth = json.load(open(sys.argv[1], encoding="utf-8")).get("claudeAiOauth") or {}
except Exception:
    sys.exit(1)

sys.exit(0 if (oauth.get("accessToken") or oauth.get("refreshToken")) else 1)
PY
  if [ "$?" -eq 0 ]; then
    printf 'PRESENT\n'
    exit 0
  fi
fi
printf 'MISSING\n'
'@
  return Invoke-InDistro $bash -AllowFail
}

function ConvertTo-BashSingleQuoted {
  param([string]$Value)
  return "'" + ($Value -replace "'", "'`"`"'") + "'"
}

# --- Windows Timezone -> IANA lookup (subset covering the zones users are
# actually likely to be in; unmapped falls back to Etc/UTC with a warning
# rather than guessing). Source: CLDR windowsZones.xml, common entries only.
$TzMap = @{
  "UTC"                             = "Etc/UTC"
  "GMT Standard Time"                = "Europe/London"
  "W. Europe Standard Time"          = "Europe/Berlin"
  "Central Europe Standard Time"     = "Europe/Budapest"
  "Romance Standard Time"            = "Europe/Paris"
  "China Standard Time"              = "Asia/Shanghai"
  "Tokyo Standard Time"              = "Asia/Tokyo"
  "Korea Standard Time"              = "Asia/Seoul"
  "Taipei Standard Time"             = "Asia/Taipei"
  "Singapore Standard Time"          = "Asia/Singapore"
  "India Standard Time"              = "Asia/Kolkata"
  "AUS Eastern Standard Time"        = "Australia/Sydney"
  "New Zealand Standard Time"        = "Pacific/Auckland"
  "Eastern Standard Time"            = "America/New_York"
  "Central Standard Time"            = "America/Chicago"
  "Mountain Standard Time"           = "America/Denver"
  "Pacific Standard Time"            = "America/Los_Angeles"
  "Alaskan Standard Time"            = "America/Anchorage"
  "Hawaiian Standard Time"           = "Pacific/Honolulu"
  "SA Eastern Standard Time"         = "America/Sao_Paulo"
  "Russian Standard Time"            = "Europe/Moscow"
  "Arabian Standard Time"            = "Asia/Dubai"
  "SE Asia Standard Time"            = "Asia/Bangkok"
}

function Resolve-Iana([string]$WindowsTzId) {
  if ($TzMap.ContainsKey($WindowsTzId)) { return $TzMap[$WindowsTzId] }
  return $null
}

Write-Host "Studio / Claude + Codex (via ah) WSL bootstrap" -ForegroundColor White
Write-Host "distro: $Distro`n"

# ---------------------------------------------------------------------------
# ===========================================================================
# PART A — ah runtime prerequisites (TEMPORARY BRIDGE; belongs in ah's own
# installer, see docs/handoffs/ah-installer-provisioning-and-master-defaults.md
# Req 1). Delete this whole part once ah's installer provisions its own runtime.
# ===========================================================================
Write-Part "PART A: ah runtime prerequisites (should move into ah's installer)"

Write-Step "A1 WSL2 feature"
& wsl.exe --status | Out-Null
if ($LASTEXITCODE -ne 0) {
  if (-not (Test-Admin)) {
    Write-Warn2 "WSL2 is not installed and this needs Administrator rights."
    Write-Host "    Re-run this script from an elevated (Run as Administrator) PowerShell." -ForegroundColor Yellow
    exit 1
  }
  Write-Host "    WSL2 not found — installing (this needs a REBOOT before it can continue)."
  & wsl.exe --install --no-distribution
  Write-Host "`n  >>> WSL2 was just installed. Please REBOOT your computer, then run" -ForegroundColor Yellow
  Write-Host "  >>> this exact command again to continue." -ForegroundColor Yellow
  exit 0
}
Write-Ok "WSL2 present"

# ---------------------------------------------------------------------------
Write-Step "A2 $Distro distro"
$distros = (& wsl.exe -l -q) -replace "`0", ""
if ($distros -notcontains $Distro) {
  Write-Host "    installing $Distro (no interactive first-user wizard — we drive it as root)..."
  & wsl.exe --install -d $Distro --no-launch
  if ($LASTEXITCODE -ne 0) { throw "wsl --install -d $Distro failed (exit $LASTEXITCODE)" }
  Write-Ok "$Distro installed"
} else {
  Write-Skip "$Distro already registered"
}
# The shipped "Open in Claude Code" launcher calls `wsl.exe -e ...` with no
# -d flag, i.e. it always targets the DEFAULT distro — keep them in sync.
& wsl.exe --set-default $Distro | Out-Null
Write-Ok "$Distro set as default WSL distro"
# Warm it up once so root is reachable for the rest of this script.
Invoke-InDistro "true" | Out-Null

# ---------------------------------------------------------------------------
Write-Step "A3 systemd + mirrored networking (may require one wsl --shutdown)"
$needsRestart = $false

$wslConf = Invoke-InDistro "cat /etc/wsl.conf 2>/dev/null || true" -AllowFail
if (($wslConf -join "`n") -notmatch "systemd\s*=\s*true") {
  Invoke-InDistro "printf '[boot]\nsystemd=true\n' >> /etc/wsl.conf"
  Write-Ok "enabled systemd in /etc/wsl.conf"
  $needsRestart = $true
} else {
  Write-Skip "systemd already enabled"
}

$wslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"
$wslConfigLines = @()
if (Test-Path $wslConfigPath) { $wslConfigLines = Get-Content $wslConfigPath }
$hasWsl2Section = $false
$hasMirrored = $false
foreach ($line in $wslConfigLines) {
  if ($line -match "^\s*\[wsl2\]") { $hasWsl2Section = $true }
  if ($line -match "^\s*networkingMode\s*=\s*mirrored") { $hasMirrored = $true }
}
if (-not $hasMirrored) {
  if (-not $hasWsl2Section) {
    $wslConfigLines += ""
    $wslConfigLines += "[wsl2]"
    $wslConfigLines += "networkingMode=mirrored"
  } else {
    # append networkingMode right after the existing [wsl2] header
    $newLines = @()
    foreach ($line in $wslConfigLines) {
      $newLines += $line
      if ($line -match "^\s*\[wsl2\]") { $newLines += "networkingMode=mirrored" }
    }
    $wslConfigLines = $newLines
  }
  Set-Content -Path $wslConfigPath -Value $wslConfigLines -Encoding utf8
  Write-Ok "enabled mirrored networking in $wslConfigPath (lets WSL reach your Windows-side proxy + localhost)"
  $needsRestart = $true
} else {
  Write-Skip "mirrored networking already configured"
}

if ($needsRestart) {
  Write-Host "    restarting WSL to apply systemd/networking changes..."
  & wsl.exe --shutdown
  Start-Sleep -Seconds 3
  Invoke-InDistro "true" | Out-Null
  Write-Ok "WSL restarted"
}

# ---------------------------------------------------------------------------
Write-Step "A4 timezone (mirrors Windows -> WSL)"
$winTz = (Get-TimeZone).Id
$iana = Resolve-Iana $winTz
if ($null -eq $iana) {
  Write-Warn2 "no IANA mapping for Windows timezone '$winTz' — leaving WSL's timezone as-is"
} else {
  Invoke-InDistro "ln -sf /usr/share/zoneinfo/$iana /etc/localtime"
  Write-Ok "WSL timezone -> $iana (from Windows '$winTz')"
}

# ---------------------------------------------------------------------------
Write-Step "A5 locale"
$winLocale = (Get-WinSystemLocale).Name  # e.g. "zh-CN", "en-US"
$glibcLocale = ($winLocale -replace "-", "_") + ".UTF-8"
Invoke-InDistro "apt-get update -y -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq locales >/dev/null"
Invoke-InDistro "locale-gen en_US.UTF-8 '$glibcLocale' >/dev/null 2>&1 || locale-gen en_US.UTF-8 >/dev/null"
Invoke-InDistro "update-locale LANG=en_US.UTF-8"
Write-Ok "generated en_US.UTF-8 + $glibcLocale"

# ---------------------------------------------------------------------------
Write-Step "A6 proxy (mirrors your Windows system proxy into WSL, if one is set)"
$proxyKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$proxySettings = Get-ItemProperty -Path $proxyKey -ErrorAction SilentlyContinue
$profileScript = "/etc/profile.d/studio-proxy.sh"
if ($proxySettings -and $proxySettings.ProxyEnable -eq 1 -and $proxySettings.ProxyServer) {
  $proxyUrl = "http://$($proxySettings.ProxyServer)"
  $script = "printf 'export HTTP_PROXY=$proxyUrl\nexport HTTPS_PROXY=$proxyUrl\nexport http_proxy=$proxyUrl\nexport https_proxy=$proxyUrl\nexport NO_PROXY=localhost,127.0.0.1,::1\nexport no_proxy=localhost,127.0.0.1,::1\n' > $profileScript"
  Invoke-InDistro $script
  Write-Ok "WSL will use Windows' system proxy ($($proxySettings.ProxyServer))"
} else {
  Invoke-InDistro "rm -f $profileScript" -AllowFail | Out-Null
  Write-Skip "no system proxy enabled on Windows — nothing to mirror"
}

# ---------------------------------------------------------------------------
Write-Step "A7 base packages (tmux, curl, python3)"
Invoke-InDistro "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tmux ca-certificates curl python3 >/dev/null"
Write-Ok "tmux + curl + python3 present"

# ===========================================================================
# PART B — Studio's own provider layer. Permanent; stays regardless of ah.
# Installs ah (whose installer would, post handoff Req 1, pull in PART A
# itself), the provider CLIs, and subscription logins. Provider CLI + auth are
# explicitly NOT ah's job (handoff Non-Goals).
# ===========================================================================
Write-Part "PART B: Studio's provider layer (ah + claude + Codex + auth)"

Write-Step "B1 ah + provider CLIs"
$minAhVersion = [Version]"1.3.4"
$ahVer = Invoke-InDistro "command -v ah >/dev/null 2>&1 && ah --version | awk '{print `$2}' || echo MISSING" -AllowFail
$ahVerText = (($ahVer -join "")).Trim()
$installAh = $false
if ($ahVerText -match "MISSING" -or [string]::IsNullOrWhiteSpace($ahVerText)) {
  $installAh = $true
} else {
  try {
    $installAh = ([Version]$ahVerText) -lt $minAhVersion
  } catch {
    $installAh = $true
  }
}
if ($installAh) {
  Invoke-InDistro "curl --proto '=https' --tlsv1.2 -LsSf https://github.com/SevenX77/ah/releases/latest/download/ah-installer.sh | sh"
  Invoke-InDistro "systemctl --user stop 'ah-*.service' 2>/dev/null || true; pkill -x ahd 2>/dev/null || true; find ~/.local/state/ah -name ahd.sock -type s -delete 2>/dev/null || true" -AllowFail | Out-Null
  $ahVerAfter = Invoke-InDistro "ah --version | awk '{print `$2}'" -AllowFail
  Write-Ok "ah installed/updated ($ahVerAfter)"
} else {
  Write-Skip "ah present ($ahVer)"
}

$claudePresent = Invoke-InDistro "command -v claude >/dev/null 2>&1 && echo PRESENT || echo MISSING" -AllowFail
$claudeHijack = Test-ProviderCliInteropHijack "claude"
if (($claudePresent -join "") -match "MISSING") {
  Invoke-InDistro "curl -fsSL https://claude.ai/install.sh | bash"
  Write-Ok "claude CLI installed"
} elseif (($claudeHijack -join "`n") -match "HIJACKED") {
  Invoke-InDistro "curl -fsSL https://claude.ai/install.sh | bash"
  Write-Ok "repaired hijacked claude entry ($($claudeHijack -join ' '))"
} else {
  $claudeVer = Invoke-InDistro "claude --version" -AllowFail
  Write-Skip "claude CLI present ($claudeVer)"
}

$codexWinBin = Join-Path $env:LOCALAPPDATA "Programs\OpenAI\Codex\bin\codex.exe"
if (-not (Test-Path $codexWinBin)) {
  Write-Host "    installing the Codex CLI on Windows (auth source of truth)..."
  $previousCodexNonInteractive = $env:CODEX_NON_INTERACTIVE
  $env:CODEX_NON_INTERACTIVE = "1"
  try {
    Invoke-RestMethod -Uri "https://chatgpt.com/codex/install.ps1" | Invoke-Expression
  } finally {
    if ($null -eq $previousCodexNonInteractive) {
      Remove-Item Env:\CODEX_NON_INTERACTIVE -ErrorAction SilentlyContinue
    } else {
      $env:CODEX_NON_INTERACTIVE = $previousCodexNonInteractive
    }
  }
  Write-Ok "Windows Codex CLI installed"
} else {
  $codexWinVer = & $codexWinBin --version
  Write-Skip "Windows Codex CLI present ($codexWinVer)"
}

$codexWslPresent = Invoke-InDistro "command -v codex >/dev/null 2>&1 && echo PRESENT || echo MISSING" -AllowFail
$codexWslHijack = Test-ProviderCliInteropHijack "codex"
if (($codexWslPresent -join "") -match "MISSING") {
  Invoke-InDistro "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"
  Write-Ok "WSL Codex CLI installed"
} elseif (($codexWslHijack -join "`n") -match "HIJACKED") {
  Invoke-InDistro "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"
  Write-Ok "repaired hijacked codex entry ($($codexWslHijack -join ' '))"
} else {
  $codexWslVer = Invoke-InDistro "codex --version" -AllowFail
  Write-Skip "WSL Codex CLI present ($codexWslVer)"
}

# ---------------------------------------------------------------------------
Write-Step "B2 auth (subscription login — not an API key)"
$winClaudeCredPath = Join-Path $env:USERPROFILE ".claude\.credentials.json"
$claudeCredUsable = $false
if (Test-Path $winClaudeCredPath) {
  try {
    $oauth = (Get-Content -Path $winClaudeCredPath -Raw | ConvertFrom-Json).claudeAiOauth
    $claudeCredUsable = [bool]($oauth.accessToken -or $oauth.refreshToken)
  } catch {
    $claudeCredUsable = $false
  }
}
if (-not $claudeCredUsable) {
  Write-Warn2 "Claude auth is not ready: sign in to Claude Code on Windows, then re-run this script."
  Write-Host "      Studio uses Windows Claude's normal login file as the single auth source." -ForegroundColor Yellow
  Write-Host "      It does not require a WSL Claude login and does not copy .credentials.json." -ForegroundColor Yellow
  exit 0
} else {
  $wslClaudeCredPath = "/mnt/" + $env:USERPROFILE.Substring(0,1).ToLower() + ($env:USERPROFILE.Substring(2) -replace "\\", "/") + "/.claude/.credentials.json"
  $quotedClaudeCredPath = ConvertTo-BashSingleQuoted $wslClaudeCredPath
  Invoke-InDistro "mkdir -p ~/.claude && ln -sfn $quotedClaudeCredPath ~/.claude/.credentials.json"
  $claudeAuth = Test-ClaudeReusableAuth
  if (($claudeAuth -join "") -match "PRESENT") {
    Write-Ok "linked Windows Claude login into WSL"
  } else {
    Write-Warn2 "Windows Claude credentials were linked, but WSL could not read a usable Claude login."
    exit 0
  }
}
$winCodexAuthPath = Join-Path $env:USERPROFILE ".codex\auth.json"
if (Test-Path $winCodexAuthPath) {
  $wslCodexAuthPath = "/mnt/" + $env:USERPROFILE.Substring(0,1).ToLower() + ($env:USERPROFILE.Substring(2) -replace "\\", "/") + "/.codex/auth.json"
  Invoke-InDistro "mkdir -p ~/.codex && cp '$wslCodexAuthPath' ~/.codex/auth.json && chmod 600 ~/.codex/auth.json"
  Write-Ok "copied your Windows Codex login into WSL"
} else {
  Write-Warn2 "one-time manual step needed — Codex auth must be created on Windows first:"
  Write-Host "      1. Open a NEW PowerShell and run:" -ForegroundColor Yellow
  Write-Host "         & '$codexWinBin' login --device-auth" -ForegroundColor Yellow
  Write-Host "      2. Complete the browser login." -ForegroundColor Yellow
  Write-Host "      3. Re-run this exact script — it will copy the login into WSL." -ForegroundColor Yellow
  exit 0
}

# ---------------------------------------------------------------------------
Write-Step "verify"
$doctor = Invoke-InDistro "ah doctor" -AllowFail
Write-Host ($doctor -join "`n")
Write-Host "    (a red 'daemon - ahd daemon is not running' line above is expected here --" -ForegroundColor DarkGray
Write-Host "     ahd starts on demand the first time you use the assistant menu.)" -ForegroundColor DarkGray
$codexStatus = Invoke-InDistro "codex login status" -AllowFail
Write-Host "Codex: $($codexStatus -join ' ')" -ForegroundColor DarkGray

Write-Host "`nDone. Go back to Studio and use the Claude/Codex assistant menu." -ForegroundColor Green
