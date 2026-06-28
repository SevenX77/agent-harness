# Run the Studio app + verify the UI

Two parts:

1. **Startup (any machine)** — get the Tauri desktop app fully running, including
   the Python FastAPI sidecar. This applies to macOS / Windows / Linux desktop /
   VPS alike.
2. **Headless verify (VPS Linux only)** — how to *see* and *drive* the window
   when there is no physical display, using a virtual display + screenshots +
   synthetic mouse clicks.

---

## 1. Startup (any machine)

The standard command is `cd apps/studio/tauri && cargo tauri dev` (it owns both
Vite and the dynamic-port FastAPI sidecar — see `apps/studio/tauri/README.md`).
On a **fresh machine** that command alone shows a red **"Backend unavailable"**
banner, because the sidecar's Python runtime + dependencies are not provisioned
yet. The sidecar (`apps/studio/tauri/src/sidecar.rs`) runs a *vendored* Python
interpreter against a *vendored* dependency tree under
`apps/studio/tauri/vendor/` (a gitignored runtime artifact), not your system
Python. Provision it once:

```bash
# 0. workspace deps (one uv workspace, single root uv.lock)
uv sync --all-packages --all-extras --group dev

# 1. download the vendored Python interpreter (if not already present)
cd apps/studio/tauri && node scripts/download_runtime.js && cd ../../..

# 2. install the backend dependency closure into vendor/site-packages
#    (uses the vendored interpreter for ABI match; pulls the full uv-workspace
#     closure incl. local graph-agent / graph-agent-gateway wheels — NOT a
#     plain requirements.txt)
python3 apps/studio/backend/scripts/build_vendor.py

# 3. pre-warm .pyc for the whole closure so the FIRST cold start does not
#    exceed the sidecar health-check timeout (the langchain/langgraph/anthropic/
#    openai closure is large; compiling it lazily on first launch can blow the
#    timeout and reproduce the "Backend unavailable" banner)
PYBIN=apps/studio/tauri/vendor/python/x86_64-unknown-linux-gnu/bin/python3.12
"$PYBIN" -m compileall -q -j 4 \
  apps/studio/tauri/vendor/site-packages \
  apps/studio/tauri/vendor/backend \
  apps/studio/backend/app

# 4. run
cd apps/studio/tauri && cargo tauri dev
```

Notes:
- The vendored interpreter path is platform-specific; the Linux x86_64 triple is
  `x86_64-unknown-linux-gnu` (replace for other hosts).
- In a debug build the sidecar prefers the **live** backend source at
  `apps/studio/backend` (it checks `app/main.py` exists), and loads dependencies
  from `vendor/site-packages`. So you can edit backend code without re-vendoring;
  you only re-run `build_vendor.py` when **dependencies** change.
- Symptoms → cause: `No module named uvicorn` = step 2 never ran
  (`vendor/site-packages` missing). Banner stays red for ~30s+ then the sidecar
  dies = step 3 never ran (cold `.pyc` compile exceeded the health check).
- This is a pure **provisioning** step. It is NOT a macOS-vs-Linux compatibility
  issue — the vendored interpreter is a native binary for the host platform.

When healthy: the sidecar comes up in a few seconds and the "Backend
unavailable" banner is gone; settings / API-keys pages load real data.

---

## 2. Headless verify — **VPS Linux only**

> ⚠️ **This section is only for the headless VPS Linux server** (no physical
> display). On any machine with a desktop (macOS / Windows / Linux desktop),
> `cargo tauri dev` opens a real window you look at directly — you do **not**
> need Xvfb / mss / XTEST. Use this section purely as the "let me see the screen
> for you on the screenless server" workaround.

### 2.1 Virtual display + launch

> **Solo on the box?** the fixed `:99` / default ports below are fine.
> **Sharing the box with other agents?** STOP — do not use `:99` or the default
> port; each agent needs its own display / port / cache / worktree. Jump to
> **§3 Multi-agent isolation** and launch the way it shows, then come back here
> for screenshot/click.

```bash
# start a virtual X display once
Xvfb :99 -screen 0 1600x1000x24 >/tmp/xvfb.log 2>&1 &

# launch the app against it — RECORD the pid; it is the only process you may kill
cd apps/studio/tauri && DISPLAY=:99 cargo tauri dev >/tmp/tauri-dev.log 2>&1 &
echo "tauri pid = $!"
```

If the webview paints blank, set the usual WebKit-headless env vars
(`WEBKIT_DISABLE_COMPOSITING_MODE=1`, `LIBGL_ALWAYS_SOFTWARE=1`) before launch.

### 2.2 Screenshot

```bash
DISPLAY=:99 uv run --no-project --with mss python - <<'PY'
import mss; mss.MSS().shot(mon=1, output='/tmp/ui.png')
PY
```

A black/tiny PNG means the webview has not painted yet — poll every second for a
few seconds (cold start + lib recompiles can delay the first paint). Confirm the
window exists with python-xlib if unsure.

### 2.3 Mouse clicks (drive the UI)

Synthetic clicks via XTEST (python-xlib). Coordinates are screen-absolute on the
virtual display.

```bash
DISPLAY=:99 uv run --no-project --with python-xlib --with mss python - <<'PY'
import time, os
from Xlib import display, X
from Xlib.ext import xtest
import mss
d = display.Display(':99')
def click(x, y):
    xtest.fake_input(d, X.MotionNotify, x=x, y=y); d.sync(); time.sleep(0.3)
    xtest.fake_input(d, X.ButtonPress, 1); d.sync(); time.sleep(0.1)
    xtest.fake_input(d, X.ButtonRelease, 1); d.sync()
click(24, 871)            # e.g. the settings gear (bottom-left)
time.sleep(2.5)
mss.MSS().shot(mon=1, output='/tmp/after-click.png')
print('shot', os.path.getsize('/tmp/after-click.png'))
PY
```

Read the resulting PNG and confirm the expected screen appeared. Clicking a
backend-backed control (e.g. **Settings → API Keys**) doubles as an end-to-end
backend check: if the page loads real data, the sidecar + gateway are alive.

### 2.4 Cleanup

Kill **only the pid you recorded at launch** — never a pattern:

```bash
kill "$TAURI_PID"            # the $! you saved in 2.1; not a pattern
kill "$XVFB_PID"             # only if YOU started that Xvfb
```

> ⚠️ **`pkill -f 'cargo tauri dev'` / `pkill -f Xvfb` are SAFE ONLY when you are
> the sole user of the box.** If any other agent shares the repo, those patterns
> kill *every* agent's app and display at once. When in doubt, kill by pid — see
> §3.5 (footguns).

---

## 3. Multi-agent isolation — run YOUR OWN instance, don't collide

When **several agents work the repo at once** (each on its own task), every agent
must launch a **fully independent** app instance. The `:99` display / default
ports in §2 are a single-tenant convenience; the moment a second agent is active,
hardcoding them makes two apps fight over the same display, ports, and Vite cache.
Treat the rules below as mandatory whenever you are not certain you are alone.

### 3.1 Run the app from YOUR OWN worktree, never the shared root

The repo root has `main` checked out; each task runs in its own
`.worktrees/<type>-<desc>/` (see AGENTS.md "Workflow Pipeline"). **Launch the app
from inside your worktree**, not the root — otherwise you are verifying the root's
code, not the change you just made. Pointing the dev command at your worktree's
`frontend/` is what makes the screenshots actually prove *your* edits.

### 3.2 Give every shared resource a unique, per-instance value

Pick numbers nobody else is using and keep them constant for your whole session:

| Resource | Env / flag | Example (mine) | Why unique |
|---|---|---|---|
| Vite dev port | `--port <n> --strictPort` | `5199` | `--strictPort` fails loud instead of silently hopping onto another agent's port |
| Virtual display | `DISPLAY` / `Xvfb :<n>` | `:91` | screenshots/clicks of one app must not land on another's window |
| Vite cache dir | `VITE_CACHE_DIR` | `/tmp/vite-mine-5199` | sharing root's `.vite` cross-contaminates dep optimization |
| Backend CORS allow-origin | `STUDIO_CORS_EXTRA_ORIGINS` | `http://127.0.0.1:5199` | backend only allows `5173`/`5174` by default → any other Vite port gets CORS-rejected (`Preflight not successful`) unless you allow it |
| Sidecar (FastAPI) port | `STUDIO_SIDECAR_PORT` | `8795` | **only if you pin it** — see note below |

> **Sidecar port is the one knob you can usually skip.** Leave `STUDIO_SIDECAR_PORT`
> **unset** and the Rust process auto-allocates a *free dynamic* port per instance
> (`allocate_loopback_port()` in `sidecar.rs`) — two agents never collide. Pin it to
> a unique value **only** when something external needs a fixed port (the
> browser-tunnel `/api` proxy in `scripts/dev-tunnel.py`); if two agents both pin
> the *same* value, their sidecars collide — so a pinned value must also be unique.

### 3.3 Share the heavy build artifacts read-only (fast isolated launch)

A fresh worktree's Rust/Python source is identical to root — only `frontend/` and
docs differ — so you can borrow root's compiled outputs instead of rebuilding the
world:

- `CARGO_TARGET_DIR=<root>/apps/studio/tauri/target` → near cache-hit; only the
  final crate recompiles (~30–40s, because `CARGO_MANIFEST_DIR` path changed).
- Symlink `node_modules` and `apps/studio/tauri/vendor` from root (read-only share)
  so you skip `npm install` + re-vendoring.
- But keep `VITE_CACHE_DIR` **unique** (§3.2) — that one must not be shared.

Drive it with a per-instance Tauri config override instead of editing the checked-in
config:

```bash
# /tmp/tauri-isolated.conf.json  (your ports baked in)
{
  "build": {
    "devUrl": "http://127.0.0.1:5199",
    "beforeDevCommand": "node tauri/scripts/sync_resources.js && cd frontend && env VITE_STUDIO_API_BASE_URL=/api STUDIO_SIDECAR_PORT=8795 VITE_CACHE_DIR=/tmp/vite-mine-5199 npm run dev -- --host 127.0.0.1 --port 5199 --strictPort"
  }
}
# launch from YOUR worktree's apps/studio dir:
cd <worktree>/apps/studio/tauri \
  && CARGO_TARGET_DIR=<root>/apps/studio/tauri/target \
     DISPLAY=:91 WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1 \
     STUDIO_CORS_EXTRA_ORIGINS=http://127.0.0.1:5199 \
     cargo tauri dev --config /tmp/tauri-isolated.conf.json >/tmp/tauri-mine.log 2>&1 &
echo "MY tauri pid = $!"   # record it — the ONLY process you may kill later (§3.5)
```

`STUDIO_CORS_EXTRA_ORIGINS` goes in the **outer** env (not `beforeDevCommand`): the
Rust process spawns the sidecar and the sidecar inherits it, so the FastAPI backend
allows your `:5199` origin. Put it only on the Vite line and the backend still rejects
your preflight.

### 3.4 Before running OR touching anything: `git worktree list`

Other agents working the **same** repo show up as registered worktrees. An agent's
worktree is **ACTIVE — do not touch** when it has *uncommitted changes + an open PR
+ recently-modified files* (check `git -C <wt> status` and file mtimes). Never edit
its files, never launch on its ports/display, never `wt-clean` it. Clean up only
**your own** stale worktrees (yours, and the PR already merged).

### 3.5 Footguns

- **`pgrep -f <pattern>` matches your own command line.** A grep for the port/app
  string counts the very bash you're running, so it lies about "leftover"
  processes. The real evidence a port is taken/free is
  `ss -ltn | grep -c ':<port>'`, not a process-name grep.
- **`pkill -f 'cargo tauri dev'` kills EVERY agent's app.** In a shared repo use a
  pattern unique to your instance (e.g. your log path / config name) or kill by the
  PID you backgrounded — never the broad `-f 'cargo tauri dev'`.
- Software-rendering noise (`libEGL warning`, `MESA: dri` lines) under Xvfb is
  harmless; the `WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1` env is
  what keeps the webview painting.

## 4. Handbook webpage — single source, single network exit (`main` only)

The N6 frontend handbook (`docs/studio/mvp1/_impl/frontend-handbook/`) is the one
exception to the per-worktree isolation in §3: the **app** runs per-worktree, but the
**handbook** is a published doc artifact that must converge to **one** copy. Rule:

- **Source of truth = `main` repo root.** Edit slices / add screenshots / regenerate
  in a worktree and land via PR like any change — but do **not** keep a second
  handbook copy in a worktree or `/tmp`, and do **not** open a second tunnel for it.
  Screenshots ride into git next to the slices (never baked into `index.html` only).
- **One network exit, served from the repo root** so a `main` update refreshes it:

  ```bash
  ROOT=/home/sevenx/coding/agent-harness          # the main working tree (repo root)
  HB=$ROOT/docs/studio/mvp1/_impl/frontend-handbook

  # serve the repo-root handbook (NOT a /tmp or worktree copy)
  python3 -m http.server 8902 --directory "$HB" >/tmp/handbook-serve.log 2>&1 &
  cloudflared tunnel --url http://127.0.0.1:8902 >/tmp/handbook-tunnel.log 2>&1 &
  ```

  `http.server` reads `index.html` fresh per request, so **refresh = update the repo
  root**: after a handbook PR merges, `git -C "$ROOT" pull` and the live URL shows it.
  Keep exactly one such serve + tunnel; tear down any extra handbook tunnels you
  started for review (`§3` isolation is for the app, not for spawning more exits).

> **If the live URL returns `502 Bad gateway`** the tunnel is up but its origin
> `http.server` died (a bare `nohup python -m http.server` does not survive a crash
> or reboot). The fix is to **restart the origin on the same port** — the existing
> `cloudflared` keeps the same public URL, so you do not re-open the tunnel. Confirm
> with `ss -ltnp | grep 890x` (nothing listening = origin dead) before restarting.

### 4.1 12D node-repair handbook (a *separate* document, its own exit)

The 12D node-repair handbook
(`docs/studio/mvp1/_impl/wave2/studio-mvp1-12d-repair-framework-2026-06-15.html`) is a
**different document** from the N6 handbook, so it gets its own serve + tunnel on a
**separate port**. This does **not** violate the "single network exit" rule above —
that rule forbids a *second copy / second tunnel of the same N6 handbook*, not a
distinct handbook. Same discipline still applies: serve the **`main` repo-root copy**
(self-contained single HTML, committed), never a `/tmp` or worktree copy.

```bash
ROOT=/home/sevenx/coding/agent-harness          # the main working tree (repo root)
HB12=$ROOT/docs/studio/mvp1/_impl/wave2

python3 -m http.server 8903 --directory "$HB12" >/tmp/handbook12d-serve.log 2>&1 &
cloudflared tunnel --url http://127.0.0.1:8903 >/tmp/handbook12d-tunnel.log 2>&1 &
# entry URL = <printed trycloudflare host>/studio-mvp1-12d-repair-framework-2026-06-15.html
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/handbook12d-tunnel.log | head -1
```

The `wave2/` dir has no `index.html`, so the file is reached by its full name in the
URL path (the `grep` above prints only the host — append the filename). Refresh = same
as N6: after a wave2 PR merges, `git -C "$ROOT" pull`. Keep one 8903 serve + tunnel;
if it 502s, restart the origin on 8903 (the tunnel URL is unchanged).
