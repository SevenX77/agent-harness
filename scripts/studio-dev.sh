#!/usr/bin/env bash
# macOS/Linux equivalent of scripts/studio-dev.ps1: pin the sidecar port for
# both Tauri and Vite, then hand off to the cross-platform Node launcher
# (apps/studio/tauri/scripts/dev_studio.js → cargo tauri dev).
#
# Usage: scripts/studio-dev.sh [port]   (default 8787)
#
# Prereqs on a fresh machine (see apps/studio/tauri/README.md):
#   - Rust + cargo-tauri, Node 20, uv
#   - Linux only: webkit2gtk-4.1 / libgtk-3-dev / libssl-dev
#   - vendored sidecar: apps/studio/backend/scripts/build_vendor.py
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sidecar_port="${1:-8787}"

# Cross-platform bottom line (docs/development/CROSS_PLATFORM.md): every
# Python child in the dev tree writes UTF-8, not the locale codepage.
export PYTHONUTF8=1
export STUDIO_SIDECAR_PORT="$sidecar_port"

exec node "$repo_root/apps/studio/tauri/scripts/dev_studio.js" --port "$sidecar_port"
