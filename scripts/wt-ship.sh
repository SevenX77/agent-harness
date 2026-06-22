#!/usr/bin/env bash
# Ship the current task branch: push it, open a PR to main, and arm auto-merge.
#
# Run from inside a task worktree (one made by scripts/wt-new.sh).
# CI runs on the PR; once the required checks go green, GitHub squash-merges
# into main automatically and deletes the remote branch. No manual merge click.
#
# Usage:  scripts/wt-ship.sh ["PR title"]
#   title defaults to the last commit subject.
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" = "main" ] || [ "$branch" = "HEAD" ]; then
  echo "error: you are on '$branch', not a task branch. Run scripts/wt-new.sh first." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "error: uncommitted changes present — commit them before shipping." >&2
  exit 1
fi

git push -u origin "$branch"

if gh pr view "$branch" --json number >/dev/null 2>&1; then
  echo "• PR already exists for $branch — reusing it"
elif [ -n "${1:-}" ]; then
  gh pr create --base main --head "$branch" --title "$1" --body "$(git log -1 --pretty=%b)"
else
  gh pr create --base main --head "$branch" --fill
fi

# Arm auto-merge (squash). Merges itself once the 5 required checks pass.
gh pr merge "$branch" --auto --squash

echo
echo "✓ PR open and auto-merge armed (squash)."
echo "  It merges into main automatically when CI is green, then the remote branch is deleted."
echo "  after it merges: scripts/wt-clean.sh   (removes this local worktree)"
