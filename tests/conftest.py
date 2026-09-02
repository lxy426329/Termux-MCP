"""Shared pytest fixtures and environment setup.

Environment variables MUST be set before termux_mcp is imported — config.py
reads them at import time. HOME is redirected to a temp dir so snapshot /
trash behavior never touches the real user home.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="termux-mcp-test-")
os.environ["HOME"] = _TMP
os.environ["TERMUX_MCP_AUTH_TOKEN"] = "test-token-0123456789abcdef"
os.environ["TERMUX_MCP_MCP_PORT"] = "18765"
os.environ["TERMUX_MCP_WORKSPACE"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))