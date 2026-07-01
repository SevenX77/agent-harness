#!/usr/bin/env bash
# Frontend preview for a task worktree: start THIS worktree's Vite on its own
# port, proxying /api and /ws to the already-running Studio sidecar owned by
# the main repo root (scripts/studio-dev.ps1, sidecar default :8787).
#
# Usage:  scripts/wt-fe-dev.sh [port]
#   port: optional; defaults to the first free port in 5174-5199.
#
# One full app (Tauri + sidecar + Vite 5173) keeps running from the main repo
# root; each worktree only adds a lightweight Vite. VITE_STUDIO_API_BASE_URL=/api
# keeps browser requests same-origin (they ride the Vite proxy), so no CORS
# config is needed regardless of the port.
#
# Browser auth: open  http://localhost:<port>/#tkn=<sidecar-token>
# (same tunnel-token mechanism as the main 5173 instance).
#
# Caveat: the shared sidecar runs the MAIN repo's backend code. If your task
# also changes apps/studio/backend, this preview will not reflect those backend
# changes — that's beyond the frontend-only SOP anyway.
set -euo pipefail

wt_top="$(git rev-parse --show-toplevel)"
repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
fe_dir="$wt_top/apps/studio/frontend"
cd "$fe_dir"

# Wait for the background npm ci kicked off by wt-new.sh, or run it ourselves.
marker="node_modules/.wt-install-done"
if [ ! -f "$marker" ]; then
  wt_name="$(basename "$wt_top")"
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

# Pick a port: explicit arg, else first free one in 5174-5199 (5173 belongs to
# the main repo's full app — never take it from a worktree).
port="${1:-}"
if [ -z "$port" ]; then
  port="$(node -e '
    const net = require("net");
    (async () => {
      for (let p = 5174; p < 5200; p++) {
        const free = await new Promise((resolve) => {
          const s = net.createServer()
            .once("error", () => resolve(false))
            .once("listening", () => s.close(() => resolve(true)))
            .listen(p, "0.0.0.0");
        });
        if (free) { console.log(p); return; }
      }
      process.exit(1);
    })();
  ')"
fi

export STUDIO_SIDECAR_PORT="${STUDIO_SIDECAR_PORT:-8787}"
export VITE_STUDIO_API_BASE_URL="/api"
# Git Bash (MSYS) rewrites env values that look like POSIX paths when spawning
# native Windows programs ("/api" → "C:/Program Files/Git/api"), which breaks
# the axios base URL. Exclude the var from that conversion (no-op elsewhere).
export MSYS2_ENV_CONV_EXCL="${MSYS2_ENV_CONV_EXCL:+$MSYS2_ENV_CONV_EXCL;}VITE_STUDIO_API_BASE_URL"

echo
echo "✓ worktree Vite → http://localhost:$port   (proxy → sidecar :$STUDIO_SIDECAR_PORT)"
echo "  browser auth: http://localhost:$port/#tkn=<sidecar-token>"
exec npm run dev -- --port "$port"
