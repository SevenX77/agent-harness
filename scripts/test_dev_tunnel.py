from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_PATH = Path(__file__).with_name("dev-tunnel.py")
spec = importlib.util.spec_from_file_location("dev_tunnel", SCRIPT_PATH)
assert spec is not None
dev_tunnel = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(dev_tunnel)


def test_start_processes_injects_backend_dev_tunnel_token() -> None:
    with patch.object(dev_tunnel.subprocess, "Popen") as popen:
        popen.side_effect = [
            MagicMock(pid=101),
            MagicMock(pid=102),
            MagicMock(pid=103),
        ]

        dev_tunnel.start_processes("session-token")

    backend_call = popen.call_args_list[0]
    assert backend_call.args[0] == ["uv", "run", "--no-sync", "python", "-m", "app.main"]
    assert backend_call.kwargs["cwd"] == dev_tunnel.BACKEND_DIR
    assert backend_call.kwargs["env"]["STUDIO_DEV_TUNNEL_TOKEN"] == "session-token"

    cloudflared_call = popen.call_args_list[2]
    assert cloudflared_call.args[0] == [
        "cloudflared",
        "tunnel",
        "--url",
        "http://127.0.0.1:5173",
        "--no-autoupdate",
    ]
    assert cloudflared_call.kwargs["stdout"] == dev_tunnel.subprocess.PIPE
    assert cloudflared_call.kwargs["stderr"] == dev_tunnel.subprocess.STDOUT


def test_wait_for_tunnel_url_parses_cloudflared_stdout() -> None:
    process = MagicMock()
    process.stdout.readline.side_effect = [
        "2026-05-14T info starting tunnel\n",
        "Your quick Tunnel has been created! https://abc-123.trycloudflare.com\n",
    ]
    process.poll.return_value = None

    tunnel_url = dev_tunnel.wait_for_tunnel_url(process, timeout=1, output=StringIO())

    assert tunnel_url == "https://abc-123.trycloudflare.com"


def test_entry_url_uses_hash_token() -> None:
    entry_url = dev_tunnel.build_entry_url(
        "https://abc-123.trycloudflare.com/",
        "token_value",
    )

    assert entry_url == "https://abc-123.trycloudflare.com/#tkn=token_value"
