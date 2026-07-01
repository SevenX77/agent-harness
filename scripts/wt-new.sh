#!/usr/bin/env bash
# Start a new task: a fresh git worktree + branch cut from origin/main.
#
# Usage:  scripts/wt-new.sh <type>/<short-desc>
#   e.g.  scripts/wt-new.sh feat/copilot-streaming
#
# Always branches from the latest origin/main (never from another task branch),
# and tidies any already-merged worktrees first so the tree stays clean.
set -euo pipefail

branch="${1:?usage: scripts/wt-new.sh <type>/<short-desc>  (e.g. feat/copilot-streaming)}"

# repo root = the main worktree, resolved from the shared git dir so this works
# no matter which worktree you invoke it from.
repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
cd "$repo_root"

# tidy already-merged worktrees before starting a new one (best-effort)
[ -x "$repo_root/scripts/wt-clean.sh" ] && "$repo_root/scripts/wt-clean.sh" || true

git fetch origin --prune

dir=".worktrees/${branch//\//-}"
if [ -e "$dir" ]; then
  echo "error: $dir already exists" >&2
  exit 1
fi

git worktree add -b "$branch" "$dir" origin/main

# Pre-install frontend deps in the background so npm run dev / lint / test are
# ready by the time they're needed. npm ci only writes into node_modules/ and
# never touches src, so coding can start immediately. scripts/wt-fe-dev.sh
# waits for this install (marker: node_modules/.wt-install-done).
# Skip with WT_SKIP_NPM=1 (e.g. for backend-only tasks).
fe_dir="$dir/apps/studio/frontend"
if [ -z "${WT_SKIP_NPM:-}" ] && [ -f "$fe_dir/package.json" ]; then
  wt_name="$(basename "$dir")"
  npm_log="$repo_root/.worktrees/.$wt_name.npm-ci.log"
  npm_pid="$repo_root/.worktrees/.$wt_name.npm-ci.pid"
  (
    cd "$fe_dir"
    nohup sh -c 'npm ci && touch node_modules/.wt-install-done' >"$npm_log" 2>&1 &
    echo $! >"$npm_pid"
  )
  echo "• npm ci running in background (log: $npm_log)"
fi

echo
echo "✓ worktree ready: $repo_root/$dir"
echo "  branch '$branch' cut from origin/main"
echo "  next: cd \"$repo_root/$dir\"  →  write code  →  scripts/wt-ship.sh"
echo "  frontend preview: scripts/wt-fe-dev.sh  (own Vite port, shares the main repo's sidecar)"
