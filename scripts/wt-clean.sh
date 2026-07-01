#!/usr/bin/env bash
# Remove local task worktrees whose branch has been merged.
#
# After a PR squash-merges, GitHub deletes its remote branch (delete-branch-on-merge).
# This script detects that — a worktree branch that was pushed but whose remote
# branch is now gone — and removes the local worktree + local branch.
#
# Safe: never touches main, skips worktrees with uncommitted changes, and ignores
# branches that were never pushed.
#
# Usage:  scripts/wt-clean.sh
set -euo pipefail

repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
cd "$repo_root"
git fetch origin --prune >/dev/null 2>&1 || true

removed=0
while IFS= read -r wt; do
  [ -z "$wt" ] && continue
  br="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ -z "$br" ] && continue
  [ "$br" = "main" ] && continue
  # only branches that were actually pushed (have a remote configured)
  [ -z "$(git -C "$wt" config "branch.$br.remote" 2>/dev/null || true)" ] && continue
  # if the remote branch still exists, the PR hasn't merged yet → leave it
  if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
    continue
  fi
  if [ -n "$(git -C "$wt" status --porcelain)" ]; then
    echo "• skip $wt ($br): uncommitted changes"
    continue
  fi
  git worktree remove "$wt"
  git branch -D "$br" >/dev/null 2>&1 || true
  # drop the background npm-ci log/pid left by wt-new.sh
  rm -f "$repo_root/.worktrees/.$(basename "$wt").npm-ci."* 2>/dev/null || true
  echo "✓ removed merged worktree: $wt ($br)"
  removed=$((removed + 1))
done < <(git worktree list --porcelain | awk '/^worktree /{print $2}' | grep "/.worktrees/" || true)

git worktree prune
[ "$removed" -eq 0 ] && echo "(nothing to clean — no merged worktrees)" || true
