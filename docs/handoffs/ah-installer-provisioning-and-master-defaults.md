# Handoff → `SevenX77/ah` repo: installer should provision ah's own runtime, and fix the ccbd-rust-era master defaults

**Audience:** an agent/maintainer working on the `SevenX77/ah` repo (the Agent
Hypervisor — `ah` CLI + `ahd` daemon).

**Why this exists:** Studio's "Open in Claude Code" button drives `ah` to run a
real Claude Code session inside WSL2 on Windows. Getting that working end-to-end
surfaced three things that architecturally belong in `ah`, not in the host app.
Everything below was verified on a real Windows 11 + WSL2 (Ubuntu-24.04) box
against `ah`/`ahd` **1.2.0** (installed via `ah-installer.sh`); exact evidence is
quoted per item.

---

## Requirement 1 — `ah`'s installer should provision `ah`'s OWN runtime prerequisites

**Problem.** `ah-installer.sh` installs only the `ah` + `ahd` binaries. But `ah`
cannot actually run an agent until a pile of OS-level prerequisites exist — and
today the user (or the host app) has to install every one of them by hand. `ah`
knows exactly what it needs (it checks all of them in `ah doctor`) but can only
*diagnose*, never *install* or *fix*.

Evidence:

- The install receipt shows the installer's whole payload is two binaries:
  ```
  # ~/.config/ah/ah-receipt.json
  {"binaries":["ah","ahd"], ... "source":{"app_name":"ah","name":"ah","owner":"SevenX77","release_type":"github"},"version":"1.2.0"}
  ```
- `ah doctor` already enumerates the prerequisites it depends on, and its own
  error strings tell the user to install them manually, e.g. baked into the
  binary:
  ```
  WSL detected, but tmux is not installed or not on PATH. ah runs every agent in tmux.
    Install it inside WSL, e.g.: sudo apt update && sudo apt install -y tmux ...
  WSL detected, but the systemd user session is not available. ah needs systemd user
    services/scopes. Enable systemd in WSL: add [boot]\nsystemd=true to /etc/wsl.conf,
    then run "wsl --shutdown" ...
  ```
- `ah --help` has **no** install/provision/bootstrap subcommand, and `ah doctor`
  has **no** `--fix`. So there is no first-party way to go from "binaries
  installed" to "ah can run".

**Ask.** Fold the provisioning of `ah`'s own runtime into the install flow —
either bundled into `ah-installer.sh` (e.g. a `--provision` / `ah setup` step) or
declared as installer dependencies so the package manager pulls them. Concretely,
the prerequisites `ah` itself requires:

- On Windows: the **WSL2** feature + a Linux distro (needs a reboot after the
  feature install — surface that clearly and make it resumable).
- **`systemd`** enabled in the distro (`[boot]\nsystemd=true` in `/etc/wsl.conf`
  + a `wsl --shutdown`), since `ahd` runs as a systemd user service and agents
  run in `systemd-run --user --scope` sandboxes.
- **`tmux`** (ah runs every agent/master in tmux).
- Enough network reachability that a spawned agent can reach its provider — on
  WSL that means mirrored networking and inheriting the host proxy (see the
  host-side notes in Non-Goals; some of this may be host-specific and stay out
  of scope, but tmux/systemd/WSL are unambiguously `ah`'s to own).

`ah doctor` is the perfect contract for this: everything it currently reports as
`✗`/`!` and "suggestion: install X" is exactly what a first-party provisioner
should install.

---

## Requirement 2 — remove the ccbd-rust-era default master command (it's broken)

**Problem.** `ah` ships a **baked-in default `[master].cmd`**. When an `ah.toml`
enables the master without an explicit `cmd`, ah launches:

```
claude --dangerously-skip-permissions --continue /remote-control
```

This exact string is compiled into the `ah` binary (it appears verbatim in the
binary's string table, adjacent to the config/agent handling code). It is a
**ccbd-rust-era default** and it is broken in three independent ways for a fresh,
non-interactive, single-machine attach — all reproduced on 1.2.0:

1. **`--continue` aborts on a fresh workspace.** Interactive
   `claude --continue` with no prior conversation in cwd exits immediately with
   "No conversation found to continue", so the master dies before it's usable.
   (Verified: the master pane showed exactly that message, then the tmux session
   ended.)
2. **`--dangerously-skip-permissions` is refused under root.** WSL's default
   user is frequently root; claude refuses that flag under root/sudo unless
   `IS_SANDBOX=1` is set — the master pane printed
   `--dangerously-skip-permissions cannot be used with root/sudo privileges for
   security reasons` and exited 1.
3. **`/remote-control` is the wrong feature for a local attach.** In current
   claude, `/remote-control` opens claude's *phone / claude.ai remote-control*
   dialog ("Enable Remote Control — opens a secure connection to claude.ai"),
   which just blocks the master behind a modal. Local `ah attach master` (tmux)
   needs none of it.

We work around all three in the host by writing an explicit `cmd`
(`IS_SANDBOX=1 claude --dangerously-skip-permissions '<report prompt>'`, no
`--continue`, no `/remote-control`), but the shipped **default** should not be a
foot-gun.

**Ask.** Change ah's built-in default `[master].cmd` to something that works out
of the box on a fresh workspace as a non-root *or* root WSL user, without opening
an unrelated remote-control modal. Minimally: default to bare `claude` (ah's docs
already say an empty `cmd` normalizes to `claude`), and make the aggressive flags
opt-in. If skip-permissions is desired by default, ah should set `IS_SANDBOX=1`
in the master's environment itself when it detects it's launching under root, so
the default doesn't self-destruct.

> Note on naming: `ccbd-rust` still leaks into `ahd`'s user-facing error strings
> (e.g. `systemd-run not found in PATH; ccbd-rust requires Linux + systemd user
> session`) and a wall of `CCB_*` env-var names. Not urgent, but a rename sweep
> would stop the old project name from surfacing to users.

---

## Requirement 3 — don't implicitly adopt the ambient CWD as a project / create eager global state

**Problem.** Run without an explicit `--config`, `ah` targets a `default`
namespace but still **eagerly creates persistent daemon state** for it, and
`ah doctor` surfaces whatever directory it happened to launch from. If you run
any bare `ah` command from inside a checkout, that checkout's path ends up
recorded in ah's state — it looks (to a user) like "ah defaulted to pointing at
my repo."

Evidence (all from a clean `~/.local/state/ah` wipe):

- `ah doctor` reports the launch cwd as a project-ish fact:
  ```
  ✓ permissions:cwd - /mnt/d/coding/agent-harness
  ```
- A bare, read-only `ah ps` (no `--config`) run from an unrelated throwaway dir
  still **created** a state namespace on disk:
  ```
  # after `rm -rf ~/.local/state/ah`, then `ah ps` from /root/cwdtest:
  ahd daemon is not running at /root/.local/state/ah/default/ahd.sock
  # -> a new /root/.local/state/ah/<hash>/ahd.sqlite appeared anyway
  ```
- Earlier, a bare `ah` invocation while cwd was the repo left the repo path
  recorded inside `~/.local/state/ah/<hash>/ahd.sqlite`.
- (`ah doctor` alone did NOT create cwd-bound state — verified — so this is
  specifically the daemon/ps path being eager, not doctor.)

**Ask.** With no explicit project (`--config`), `ah` should be **neutral**: don't
adopt the ambient CWD as a project, and don't materialize per-repo daemon state
just because a command was run from inside a directory. Read-only commands like
`ps` shouldn't create state at all. The project should come *only* from an
explicit `--config` (which is how the host always invokes ah:
`ah --config <workspace>/ah.toml start|attach master`).

---

## Non-Goals (explicitly NOT ah's job)

- **Do NOT install or manage the provider CLI (`claude`) or its auth.** The
  provider binary and the user's subscription login stay with the host / the
  user. `ah doctor` already treats the provider as external
  (`✓ provider:claude - ~/.claude`, `! provider:codex - ... may need login`) —
  keep that boundary. ah reuses an already-authenticated provider; it must not
  try to install claude or mint its credentials.
- Host-specific niceties (mirroring the *Windows* system proxy / timezone /
  locale into WSL) may remain the host's concern if they're awkward to do from
  inside the distro; but the distro-internal prerequisites (systemd, tmux, and
  the WSL feature itself) are unambiguously ah's.

---

## How the host (Studio) invokes ah today (context)

For reference, the host never relies on any ah default that this handoff asks to
change — so these fixes won't break Studio, they just let Studio delete its
workarounds:

- Always passes an explicit `--config <workspace>/ah.toml` with an explicit
  master `cmd` (Req 2 workaround) and `[agents.studio] provider = "bash"`.
- Runs `ah --config … start --wait` then `ah --config … attach master`, all in
  ONE interactive WSL session so the attach holds the distro alive.
- Provisions the WSL runtime itself today via
  `scripts/install-claude-code-wsl.ps1` — the parts that Req 1 would let us
  delete are marked in that script as "ah runtime prerequisites (belongs in ah;
  see this handoff)".
