#!/usr/bin/env bash
# Remove YOUR OWN merged task worktree(s) — never other tasks' trees.
#
# After a PR squash-merges, GitHub deletes its remote branch (delete-branch-on-merge).
# This detects that — a worktree branch that was pushed UNDER ITS OWN NAME but whose
# remote branch is now gone — and removes the local worktree + local branch.
#
# SCOPE (2026-07-02): cleans ONLY the worktree(s) you NAME. With no target it does
# nothing but print usage — it never sweeps the whole tree, so it can never delete
# another task's worktree by surprise. `--all` is an explicit opt-in to sweep EVERY
# merged worktree (that one DOES touch other tasks' trees; use sparingly). This
# matches the long-standing rule in RUN_AND_SCREENSHOT.md §3.1 "clean up only your
# own merged worktrees".
#
# Safe: never touches main; only removes a branch that was pushed under its OWN name
# and whose remote is now gone; skips worktrees with uncommitted changes.
#
# Usage:
#   scripts/wt-clean.sh <worktree-dir-or-branch> [<more> ...]   # clean the named worktree(s)
#   scripts/wt-clean.sh --all                                   # opt-in: sweep ALL merged worktrees
set -euo pipefail

repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
cd "$repo_root"

removed=0

# Resolve an arg (a path under .worktrees/, or a branch name like feat/foo) to an
# absolute worktree dir. Branch names map via wt-new.sh's naming: '/' -> '-'.
resolve_wt() {
  local arg="$1"
  if [ -d "$arg" ]; then (cd "$arg" && pwd); return 0; fi
  if [ -d "$repo_root/$arg" ]; then (cd "$repo_root/$arg" && pwd); return 0; fi
  local guess="$repo_root/.worktrees/${arg//\//-}"
  if [ -d "$guess" ]; then echo "$guess"; return 0; fi
  return 1
}

# Remove ONE worktree iff its branch was pushed under its own name, that remote
# branch is now gone (PR merged + deleted), and the tree is clean. Prints why it
# skipped otherwise. Never removes main.
clean_one() {
  local wt="$1" br merge_ref
  br="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [ -z "$br" ];       then echo "• skip $wt: not a git worktree"; return 0; fi
  if [ "$br" = "main" ]; then echo "• skip $wt ($br): is main"; return 0; fi
  # Only ever remove a branch that was PUSHED UNDER ITS OWN NAME. wt-ship does
  # `git push -u origin <branch>`, which sets branch.<br>.merge=refs/heads/<br>.
  # A fresh wt-new branch instead TRACKS origin/main (merge=refs/heads/main) —
  # treating that as "merged/gone" is the bug that deleted clean, in-progress
  # worktrees (2026-07-02). Requiring merge==refs/heads/<br> excludes them.
  merge_ref="$(git -C "$wt" config "branch.$br.merge" 2>/dev/null || true)"
  if [ "$merge_ref" != "refs/heads/$br" ]; then
    echo "• skip $wt ($br): not pushed under its own name (upstream=${merge_ref:-none}) — not a finished task"
    return 0
  fi
  # Pushed as itself; if its remote branch still exists, the PR hasn't merged yet.
  if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
    echo "• skip $wt ($br): remote branch still exists (PR not merged)"; return 0
  fi
  if [ -n "$(git -C "$wt" status --porcelain)" ]; then
    echo "• skip $wt ($br): uncommitted changes"; return 0
  fi
  if git worktree remove "$wt" 2>/dev/null; then
    git branch -D "$br" >/dev/null 2>&1 || true
    rm -f "$repo_root/.worktrees/.$(basename "$wt")."* 2>/dev/null || true
    echo "✓ removed merged worktree: $wt ($br)"
    removed=$((removed + 1))
  else
    echo "• could not remove $wt ($br): leftover files (e.g. node_modules). Delete the dir manually, then: git worktree prune"
  fi
}

git fetch origin --prune >/dev/null 2>&1 || true

if [ "${1:-}" = "--all" ]; then
  # Opt-in GLOBAL sweep — every merged worktree, INCLUDING other tasks'. Sparingly.
  while IFS= read -r wt; do
    [ -z "$wt" ] && continue
    clean_one "$wt"
  done < <(git worktree list --porcelain | awk '/^worktree /{print $2}' | grep "/.worktrees/" || true)
elif [ "$#" -gt 0 ]; then
  # Named targets only — your own worktree(s). Never sweeps others'.
  for arg in "$@"; do
    if wt="$(resolve_wt "$arg")"; then
      clean_one "$wt"
    else
      echo "• skip $arg: no such worktree (looked for a dir, or .worktrees/${arg//\//-})"
    fi
  done
else
  echo "usage: scripts/wt-clean.sh <worktree-dir-or-branch> [...]   (--all to sweep every merged worktree)" >&2
  echo "cleans only the worktree you name — nothing named, nothing swept (never touches others')." >&2
fi

git worktree prune
[ "$removed" -eq 0 ] && echo "(nothing cleaned)" || true
