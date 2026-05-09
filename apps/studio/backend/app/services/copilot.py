"""Studio Copilot service - Claude Agent SDK integration.

NOTE (T0.1 base_url verify, 2026-05-09):
- claude-agent-sdk version: 0.1.80
- ClaudeSDKClient.__init__ accepts base_url=...: False
- Injection strategy: contextvars fallback
- Verification command showed __init__(self, options=None, transport=None).
- See design.md:53 for the fallback decision.
"""

from __future__ import annotations
