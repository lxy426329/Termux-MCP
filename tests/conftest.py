"""Shared pytest configuration.

OAuth integration tests exercise the legacy automatic-approval flow explicitly;
production defaults remain safe (TERMUX_MCP_OAUTH_AUTO_APPROVE=0). Tests that
need to verify the safe default override config.OAUTH_AUTO_APPROVE themselves.
"""

import os

# Set before termux_mcp.config is imported by test modules.
os.environ.setdefault("TERMUX_MCP_AUTH_TOKEN", "test-token-0123456789abcdef")
os.environ.setdefault("TERMUX_MCP_OAUTH_AUTO_APPROVE", "1")
