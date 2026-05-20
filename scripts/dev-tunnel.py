#!/usr/bin/env python3
"""Launch Studio dev mode through a single Cloudflare tunnel."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "apps" / "studio" / "backend"
FRONTEND_DIR = REPO_ROOT / "apps" / "studio" / "frontend"
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start Studio backend, Vite, and a frontend-only Cloudflare tunnel."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated token length and commands without starting processes.",
    )
    parser.add_argument(
        "--tunnel-timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for cloudflared to print the trycloudflare URL.",
    )
    return parser.parse_args(argv)


def build_entry_url(tunnel_url: str, token: str) -> str:
    return f"{tunnel_url.rstrip('/')}/#tkn={token}"


def extract_tunnel_url(line: str) -> str | None:
    match = TUNNEL_URL_RE.search(line)
    return match.group(0) if match else None


def wait_for_tunnel_url(
    process: subprocess.Popen[str],
    *,
    timeout: float = 60.0,
    output: TextIO = sys.stdout,
) -> str:
    if process.stdout is None:
        raise RuntimeError("cloudflared stdout is not captured")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line:
            print(line.rstrip(), file=output)
            tunnel_url = extract_tunnel_url(line)
            if tunnel_url:
                return tunnel_url
            continue

        if process.poll() is not None:
            raise RuntimeError(f"cloudflared exited before printing tunnel URL: {process.poll()}")
        time.sleep(0.1)

    raise TimeoutError(f"Timed out after {timeout:.1f}s waiting for cloudflared tunnel URL")


def print_qr(entry_url: str, *, output: TextIO = sys.stdout) -> None:
    import qrcode

    qr = qrcode.QRCode(border=1)
    qr.add_data(entry_url)
    qr.make(fit=True)
    qr.print_ascii(out=output)


def process_specs(token: str) -> list[tuple[str, list[str], Path, dict[str, str] | None]]:
    backend_env = {**os.environ, "STUDIO_DEV_TUNNEL_TOKEN": token}
    return [
        (
            "backend",
            ["uv", "run", "--no-sync", "python", "-m", "app.main"],
            BACKEND_DIR,
            backend_env,
        ),
        (
            "vite",
            ["corepack", "pnpm", "dev"],
            FRONTEND_DIR,
            {**os.environ, "VITE_STUDIO_API_BASE_URL": "/api"},
        ),
        (
            "cloudflared",
            [
                "cloudflared",
                "tunnel",
                "--url",
                "http://127.0.0.1:5173",
                "--no-autoupdate",
            ],
            REPO_ROOT,
            None,
        ),
    ]


def start_processes(token: str) -> list[subprocess.Popen[str]]:
    processes: list[subprocess.Popen[str]] = []
    for name, command, cwd, env in process_specs(token):
        stdout = subprocess.PIPE if name == "cloudflared" else None
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT if name == "cloudflared" else None,
            text=name == "cloudflared",
        )
        print(f"[start] {name}: pid={process.pid}")
        processes.append(process)
    return processes


def terminate_processes(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 10.0
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_dry_run(token: str) -> None:
    print(f"[1/4] Generated session token (len={len(token)})")
    for name, command, cwd, env in process_specs(token):
        env_note = " STUDIO_DEV_TUNNEL_TOKEN=<generated>" if env else ""
        print(f"[dry-run] {name}: cwd={cwd} command={' '.join(command)}{env_note}")
    sample_url = "https://example.trycloudflare.com"
    print(f"[dry-run] Entry URL shape: {build_entry_url(sample_url, token)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = secrets.token_urlsafe(32)

    if args.dry_run:
        run_dry_run(token)
        return 0

    processes: list[subprocess.Popen[str]] = []
    try:
        print(f"[1/4] Generated session token (len={len(token)})")
        processes = start_processes(token)
        cloudflared = processes[2]
        print("[2/4] Waiting for Cloudflare tunnel URL...")
        tunnel_url = wait_for_tunnel_url(cloudflared, timeout=args.tunnel_timeout)
        entry_url = build_entry_url(tunnel_url, token)
        print(f"[3/4] Entry URL: {entry_url}")
        print_qr(entry_url)
        print("[4/4] Studio dev tunnel is running. Press Ctrl+C to stop.")
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        return next((process.returncode or 1 for process in processes if process.poll()), 1)
    except KeyboardInterrupt:
        print("\nStopping Studio dev tunnel...")
        return 130
    finally:
        if processes:
            terminate_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
