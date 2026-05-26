from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from graph_agent.core.purity import scan_python_purity, scan_tool_imports_context

_REPO_ROOT = Path(__file__).parents[4]
_SCANNER = _REPO_ROOT / "scripts" / "ci_scan_v21_purity.py"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _apis(path: Path) -> list[str]:
    return [violation.api for violation in scan_python_purity(path)]


def _tool_context_violations(path: Path) -> list[str]:
    return [violation.reason for violation in scan_tool_imports_context(path)]


def test_purity_open_write_fatal(tmp_path: Path) -> None:
    assert "open" in _apis(_write(tmp_path / "x.py", "open('x.txt', 'w')\n"))


def test_purity_open_append_fatal(tmp_path: Path) -> None:
    assert "open" in _apis(_write(tmp_path / "x.py", "open('x.txt', 'a')\n"))


def test_purity_open_exclusive_fatal(tmp_path: Path) -> None:
    assert "open" in _apis(_write(tmp_path / "x.py", "open('x.txt', 'x')\n"))


def test_purity_open_plus_fatal(tmp_path: Path) -> None:
    assert "open" in _apis(_write(tmp_path / "x.py", "open('x.txt', 'r+')\n"))


def test_purity_open_read_ok(tmp_path: Path) -> None:
    assert scan_python_purity(_write(tmp_path / "x.py", "open('x.txt', 'r')\n")) == []
    assert scan_python_purity(_write(tmp_path / "y.py", "open('x.txt')\n")) == []


def test_purity_path_write_text_fatal(tmp_path: Path) -> None:
    assert "write_text" in _apis(
        _write(tmp_path / "x.py", "from pathlib import Path\nPath('x').write_text('x')\n")
    )


def test_purity_path_write_bytes_fatal(tmp_path: Path) -> None:
    assert "write_bytes" in _apis(
        _write(tmp_path / "x.py", "from pathlib import Path\nPath('x').write_bytes(b'x')\n")
    )


def test_purity_path_touch_fatal(tmp_path: Path) -> None:
    assert "touch" in _apis(
        _write(tmp_path / "x.py", "from pathlib import Path\nPath('x').touch()\n")
    )


def test_purity_path_mkdir_fatal(tmp_path: Path) -> None:
    assert "mkdir" in _apis(
        _write(tmp_path / "x.py", "from pathlib import Path\nPath('x').mkdir()\n")
    )


def test_purity_os_makedirs_fatal(tmp_path: Path) -> None:
    assert "os.makedirs" in _apis(_write(tmp_path / "x.py", "import os\nos.makedirs('x')\n"))


def test_purity_shutil_copy_fatal(tmp_path: Path) -> None:
    assert "shutil.copy" in _apis(
        _write(tmp_path / "x.py", "import shutil\nshutil.copy('a', 'b')\n")
    )


def test_purity_shutil_rmtree_fatal(tmp_path: Path) -> None:
    assert "shutil.rmtree" in _apis(
        _write(tmp_path / "x.py", "import shutil\nshutil.rmtree('a')\n")
    )


def test_purity_tempfile_named_fatal(tmp_path: Path) -> None:
    assert "tempfile.NamedTemporaryFile" in _apis(
        _write(tmp_path / "x.py", "import tempfile\ntempfile.NamedTemporaryFile()\n")
    )


def test_purity_tempfile_mkdtemp_fatal(tmp_path: Path) -> None:
    assert "tempfile.mkdtemp" in _apis(
        _write(tmp_path / "x.py", "import tempfile\ntempfile.mkdtemp()\n")
    )


def test_purity_temporary_directory_fatal(tmp_path: Path) -> None:
    assert "tempfile.TemporaryDirectory" in _apis(
        _write(tmp_path / "x.py", "import tempfile\ntempfile.TemporaryDirectory()\n")
    )


def test_purity_path_read_text_ok(tmp_path: Path) -> None:
    assert (
        scan_python_purity(
            _write(tmp_path / "x.py", "from pathlib import Path\nPath('x').read_text()\n")
        )
        == []
    )


def test_scan_blocks_import_full_path(tmp_path: Path) -> None:
    reasons = _tool_context_violations(
        _write(tmp_path / "tool.py", "import graph_agent.cognitive.context_facade\n")
    )

    assert any("form 2" in reason for reason in reasons)


def test_scan_blocks_import_aliased(tmp_path: Path) -> None:
    reasons = _tool_context_violations(
        _write(tmp_path / "tool.py", "import graph_agent.cognitive.context_facade as cf\n")
    )

    assert any("form 3" in reason for reason in reasons)


def test_scan_blocks_from_cognitive_import_facade(tmp_path: Path) -> None:
    reasons = _tool_context_violations(
        _write(tmp_path / "tool.py", "from graph_agent.cognitive import context_facade\n")
    )

    assert any("form 4" in reason for reason in reasons)


def test_purity_cli_clean_exit_0(tmp_path: Path) -> None:
    _write(
        tmp_path / "phases" / "p" / "actions" / "clean.py", "def clean(context):\n    return None\n"
    )

    result = subprocess.run(
        [sys.executable, str(_SCANNER), str(tmp_path)], text=True, capture_output=True
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_purity_cli_dirty_exit_1(tmp_path: Path) -> None:
    _write(tmp_path / "phases" / "p" / "actions" / "dirty.py", "open('x', 'w')\n")

    result = subprocess.run(
        [sys.executable, str(_SCANNER), str(tmp_path)], text=True, capture_output=True
    )

    assert result.returncode == 1
    assert "[F-v3-logic-action-purity-violation]" in result.stdout


def test_purity_cli_ignores_v2_pending(tmp_path: Path) -> None:
    _write(tmp_path / "_v2_pending" / "x" / "tools" / "dirty.py", "open('x', 'w')\n")

    result = subprocess.run(
        [sys.executable, str(_SCANNER), str(tmp_path)], text=True, capture_output=True
    )

    assert result.returncode == 0
    assert result.stdout == ""
