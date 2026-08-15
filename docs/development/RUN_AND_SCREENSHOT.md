# Run the Studio app + verify the UI

Four parts:

1. **Startup (any machine)** — get the Tauri desktop app fully running, including
   the Python FastAPI sidecar. This applies to macOS / Windows / Linux desktop /
   VPS alike.
2. **Headless verify (VPS Linux only)** — how to *see* and *drive* the window
   when there is no physical display, using a virtual display + screenshots +
   synthetic mouse clicks.
3. **Verifying a worktree's changes** — per-task Vite via `scripts/wt-dev.sh`;
   the root app stays the only full app instance.
4. **Per-item verification on Windows** — drive the REAL desktop window over the
   Chrome DevTools Protocol, which is how the agent runs its own post-merge
   per-item verification.

---

## 1. Startup (any machine)

The standard command, from repo root, is
`powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1` on Windows.
That launcher pins `STUDIO_SIDECAR_PORT` before running `cargo tauri dev`, so
Vite's `/api` proxy and the FastAPI sidecar use the same port.
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
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1
```

Notes:
- The vendored interpreter path is platform-specific; the Linux x86_64 triple is
  `x86_64-unknown-linux-gnu` (replace for other hosts).
- In a debug build the sidecar prefers the **live** FastAPI backend source at
  `apps/studio/backend` (it checks `app/main.py` exists) — so you can edit
  `apps/studio/backend/app/**` without re-vendoring. But `graph_agent` /
  `graph_agent_gateway` are ALWAYS imported from `vendor/site-packages` (dev
  builds included), and those two are vendored as pre-built wheels from
  `packages/graph-agent` / `packages/graph-agent-gateway` — so any SOURCE
  change to those two packages, not just a dependency-manifest change, leaves
  the running app on stale engine/gateway code until you re-run
  `build_vendor.py` (+ re-warm `.pyc`) and restart. See `AGENTS.md`
  "Workflow Pipeline" step 7 for the exact recipe and the close-app-first
  Windows file-lock gotcha.
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

> This recipe drives the **ONE full app at the repo root** (`main`'s code). If
> what you need to verify is a **worktree's** change, this is the wrong tool —
> use `scripts/wt-dev.sh` + Playwright instead (**§3**). The Xvfb/XTEST path
> below is only for native-shell behaviors a browser cannot reach. Sharing the
> box with other agents? The root app is shared — do **not** start a second
> Xvfb + Tauri stack; coordinate instead (§3).

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
> kill the shared root app and *every* agent's processes at once. When in doubt,
> kill by pid — see §3.2 (footguns).

---

## 3. Verifying a worktree's changes — per-task Vite, never a second app

Task isolation is owned by the worktree pipeline (AGENTS.md "Workflow Pipeline"
+ the feature SOP `apps/studio/frontend/CLAUDE.md`), **not** by launching
another app instance. The repo root runs the ONE full app
(`scripts/studio-dev.ps1` / `scripts/studio-dev.sh`: Tauri + sidecar :8787 +
Vite 5173, showing `main`'s code); **never start a second Tauri — or a second
Xvfb + Tauri stack — from a worktree**.

- **Frontend-only change** → run `scripts/wt-dev.sh` inside your worktree. It
  starts this worktree's own Vite on a free port in 5174-5199 and proxies
  `/api`/`/ws` to the shared main sidecar. Requests stay same-origin via
  `VITE_STUDIO_API_BASE_URL=/api`, so no CORS setup
  (`STUDIO_CORS_EXTRA_ORIGINS`) is needed for any port.
- **Backend / engine / gateway change** → `scripts/wt-dev.sh --backend`
  additionally starts a private sidecar from THIS worktree's Python code (free
  port in 8788-8799, fresh `STUDIO_API_TOKEN` printed for `#tkn=`), so backend
  changes are verified against your own tree — never against `main`'s sidecar
  by accident.
- **Verify at `http://localhost:<vite-port>/#tkn=<token>`** — never on 5173
  (that is `main`'s code, without your changes).
- **Headless boxes**: verifying a worktree is browser-level — drive the wt-dev
  URL with Playwright (locators + screenshots), per
  `docs/development/FRONTEND_UI_SPEC.md` §2.10. The §2 Xvfb/XTEST recipe is
  only for the root app's Tauri window (native-shell behaviors such as file
  dialogs, native menus, and Tauri bridge paths that Playwright cannot reach).

### 3.1 Respect other agents' worktrees

Other agents working the same repo show up in `git worktree list`. A worktree
is **ACTIVE — do not touch** when it has *uncommitted changes + an open PR +
recently-modified files* (check `git -C <wt> status` and file mtimes). Never
edit its files, never kill its processes, never `wt-clean` it. Clean up only
**your own** merged worktrees, by name — `scripts/wt-clean.sh <your-branch>`
(cleans only the worktree you name; `--all` is an opt-in global sweep).

### 3.2 Footguns (shared box)

- **`pkill -f 'cargo tauri dev'` / broad `pkill -f Xvfb` kill the shared root
  app** (and any other agent's processes). Kill only the PIDs you recorded when
  you backgrounded something (see §2.4).
- **`pgrep -f <pattern>` matches your own command line.** A grep for the
  port/app string counts the very bash you're running, so it lies about
  "leftover" processes. The real evidence a port is taken/free is
  `ss -ltn | grep -c ':<port>'`, not a process-name grep.
- Software-rendering noise (`libEGL warning`, `MESA: dri` lines) under Xvfb is
  harmless; the `WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1` env
  is what keeps the webview painting.

## 4. Per-item verification on Windows — drive the real window over CDP

> **可执行入口:`/studio-verify` skill(`.claude/skills/studio-verify/`)** —
> 本节方法的落地实例:启停 launcher(带/不带 9222)+ cdp/click/shot/emulate/console
> 五件套脚本 + 纪律清单,拿来即用。本节保留原理与协议细节;两处如有出入,以能跑通的
> skill 为准并回修本节。**禁止**用浏览器直开 Vite 的 web 模式充当验证(2026-08-14
> 用户裁决):web 模式下 Tauri 原生桥是假的、Recent 存在 Rust native store 里根本
> 打不开 skill,结论不可信。

The desktop app's UI is a WebView2 (Chromium) instance, so the real window can
be driven over the Chrome DevTools Protocol: DOM-level assertions and real
mouse events, no screenshot-pixel guessing. This is the standard way the agent
runs the post-merge per-item verification itself (AGENTS.md "Studio Feature
Development", decision 2026-08-06). Unlike §2 this drives the REAL Tauri
window, so native `invoke` paths are live too.

```powershell
# launch WITH a debug port (the env var only affects processes started under it)
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=9222"
powershell -ExecutionPolicy Bypass -File .\scripts\studio-dev.ps1
```

- **Page target**: `GET http://127.0.0.1:9222/json` → the entry with
  `type == "page"` whose url matches the Vite **port** (`/:5173/`). Match the
  port, not the hostname — it may be `127.0.0.1`, not `localhost`.
- **Assertions / navigation**: `Runtime.evaluate` over the target's WebSocket
  (`returnByValue: true, awaitPromise: true`). Read `document.body.innerText`
  FIRST to see which screen is actually up before clicking anything — the app
  may have restored the last workspace instead of the home screen.
- **Clicks**: Radix/shadcn menus need REAL pointer events —
  `Input.dispatchMouseEvent` (mouseMoved → mousePressed → mouseReleased) at
  the element's `getBoundingClientRect()` center; synthetic `.click()` does
  not open them.
- **Screenshots for the verification report**: `Page.captureScreenshot`.
- **Transients** (sub-second loading states): run a sampling loop INSIDE the
  page via one `Runtime.evaluate` (poll every 100 ms, record state changes,
  return the timeline).
- **Close the debug port when done**: restart the app with the env var
  explicitly empty, then VERIFY with `curl http://127.0.0.1:9222/json/version`
  that the port is really gone — while it is open, any local process can fully
  control the page. Do not restart a session the user is actively using
  without asking first.
