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

```bash
# start a virtual X display once
Xvfb :99 -screen 0 1600x1000x24 >/tmp/xvfb.log 2>&1 &

# launch the app against it
cd apps/studio/tauri && DISPLAY=:99 cargo tauri dev >/tmp/tauri-dev.log 2>&1 &
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

```bash
pkill -f 'cargo tauri dev'; pkill -f Xvfb   # when done
```
