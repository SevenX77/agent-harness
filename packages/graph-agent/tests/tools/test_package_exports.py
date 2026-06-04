from __future__ import annotations

import graph_agent.tools as tools


def test_tools_package_does_not_export_domain_specific_tools() -> None:
    assert tools.__all__ == []
    assert not hasattr(tools, "synthesize_speech_tool")
