#!/usr/bin/env bash
# Dev preview for a task worktree: start THIS worktree's Vite on its own port.
#
# Usage:  scripts/wt-dev.sh [--backend] [vite-port]
#
# Default (frontend-only changes): proxy /api and /ws to the already-running
# Studio sidecar owned by the main repo root (scripts/studio-dev.ps1, sidecar
# default :8787). That sidecar runs MAIN's backend code.
#
# --backend (task touches apps/studio/backend / engine / gateway): start a
# private sidecar from THIS worktree's Python code on a free port in 8788-8799
# (fresh STUDIO_API_TOKEN, printed for the browser #tkn= hash), and point the
# Vite proxy at it — so backend changes are verified against YOUR tree too.
#
# Either way, one full app (Tauri + sidecar + Vite 5173) stays on the main repo
# root; worktrees never start a second Tauri. VITE_STUDIO_API_BASE_URL=/api
# keeps browser requests same-origin (they ride the Vite proxy), so no CORS
# config is needed regardless of the port.
#
# Browser: open  http://localhost:<vite-port>/#tkn=<token>
# (default mode: the main sidecar's token; --backend: the token printed below).
set -euo pipefail

with_backend=0
port=""
for arg in "$@"; do
  case "$arg" in
    --backend) with_backend=1 ;;
    *) port="$arg" ;;
  esac
done

wt_top="$(git rev-parse --show-toplevel)"
repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
fe_dir="$wt_top/apps/studio/frontend"
wt_name="$(basename "$wt_top")"

free_port() { # free_port <from> <to>
  node -e '
    const net = require("net");
    const [from, to] = [Number(process.argv[1]), Number(process.argv[2])];
    (async () => {
      for (let p = from; p <= to; p++) {
        // Probe the SAME address the consumers bind (sidecar: uvicorn --host
        // 127.0.0.1). On Windows a 127.0.0.1 listener does not block a 0.0.0.0
        // probe, so probing 0.0.0.0 reports "free" for a port that another
        // worktree sidecar already holds on loopback.
        const free = await new Promise((resolve) => {
          const s = net.createServer()
            .once("error", () => resolve(false))
            .once("listening", () => s.close(() => resolve(true)))
            .listen(p, "127.0.0.1");
        });
        if (free) { console.log(p); return; }
      }
      process.exit(1);
    })();
  ' "$1" "$2"
}

# --- frontend deps: wait for the background npm ci from wt-new.sh, or run it ---
cd "$fe_dir"
marker="node_modules/.wt-install-done"
if [ ! -f "$marker" ]; then
  npm_pid_file="$repo_root/.worktrees/.$wt_name.npm-ci.pid"
  npm_log="$repo_root/.worktrees/.$wt_name.npm-ci.log"
  if [ -f "$npm_pid_file" ] && kill -0 "$(cat "$npm_pid_file")" 2>/dev/null; then
    echo "• waiting for background npm ci to finish (log: $npm_log) ..."
    while kill -0 "$(cat "$npm_pid_file")" 2>/dev/null && [ ! -f "$marker" ]; do
      sleep 2
    done
  fi
  if [ ! -f "$marker" ]; then
    echo "• node_modules not ready — running npm ci now"
    npm ci
    touch "$marker"
  fi
fi

# --- backend: private sidecar from this worktree's code (--backend only) ---
side_pid=""
if [ "$with_backend" = "1" ]; then
  # wait for the background uv sync from wt-new.sh if it's still running
  uv_pid_file="$repo_root/.worktrees/.$wt_name.uv-sync.pid"
  if [ -f "$uv_pid_file" ] && kill -0 "$(cat "$uv_pid_file")" 2>/dev/null; then
    echo "• waiting for background uv sync to finish ..."
    while kill -0 "$(cat "$uv_pid_file")" 2>/dev/null; do sleep 2; done
  fi
  bport="$(free_port 8788 8799)"
  token="$(node -e 'console.log(require("crypto").randomBytes(24).toString("hex"))')"
  side_log="$repo_root/.worktrees/.$wt_name.sidecar.log"
  (
    cd "$wt_top/apps/studio/backend"
    STUDIO_API_TOKEN="$token" PYTHONUTF8=1 exec uv run uvicorn app.main:app \
      --host 127.0.0.1 --port "$bport" >"$side_log" 2>&1
  ) &
  side_pid=$!
  trap '[ -n "$side_pid" ] && kill "$side_pid" 2>/dev/null || true' EXIT
  echo "• private sidecar (THIS worktree's backend) starting on :$bport (log: $side_log)"
  until curl -s -o /dev/null "http://127.0.0.1:$bport/api/health"; do
    kill -0 "$side_pid" 2>/dev/null || { echo "sidecar died — see $side_log" >&2; exit 1; }
    sleep 1
  done
  export STUDIO_SIDECAR_PORT="$bport"
else
  export STUDIO_SIDECAR_PORT="${STUDIO_SIDECAR_PORT:-8787}"
fi

# --- vite: own port, proxy to the chosen sidecar ---
[ -n "$port" ] || port="$(free_port 5174 5199)"
export VITE_STUDIO_API_BASE_URL="/api"
# Git Bash (MSYS) rewrites env values that look like POSIX paths when spawning
# native Windows programs ("/api" → "C:/Program Files/Git/api"), which breaks
# the axios base URL. Exclude the var from that conversion (no-op elsewhere).
export MSYS2_ENV_CONV_EXCL="${MSYS2_ENV_CONV_EXCL:+$MSYS2_ENV_CONV_EXCL;}VITE_STUDIO_API_BASE_URL"

echo
echo "✓ worktree Vite → http://localhost:$port   (proxy → sidecar :$STUDIO_SIDECAR_PORT)"
if [ "$with_backend" = "1" ]; then
  echo "  browser auth: http://localhost:$port/#tkn=$token"
else
  echo "  browser auth: http://localhost:$port/#tkn=<main sidecar's token>"
fi
npm run dev -- --port "$port"
