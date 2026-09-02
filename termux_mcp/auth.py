"""Authentication abstraction for termux-mcp.

Currently ships a static Bearer-token provider — `Authorization: Bearer`
header only; tokens in URL query parameters are never accepted. The
provider interface is designed so a standards-compliant MCP OAuth 2.0
flow can be added later without touching the REST or MCP request handlers.

OAuth roadmap (not yet implemented — see docs/oauth.md):
  * Dynamic client registration (RFC 7591) or pre-registered clients.
  * Authorization Code + PKCE flow (RFC 7636) with a browser/device flow.
  * Token endpoint issuing access tokens; resource server validates them.
  * MCP client discovery via /.well-known/oauth-authorization-server.
"""

import hmac
from abc import ABC, abstractmethod
from typing import Dict, Optional

from .config import AUTH_TOKEN, REQUIRE_AUTH


class AuthProvider(ABC):
    """Interface for authenticating incoming requests."""

    @abstractmethod
    def authenticate(self, headers: Dict[str, str]) -> bool:
        """Return True when the request is authorized."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """True when authentication is required."""

    def challenge_headers(self) -> Dict[str, str]:
        """WWW-Authenticate headers to send on 401."""
        return {"WWW-Authenticate": "Bearer"}


class BearerAuthProvider(AuthProvider):
    """Static Bearer token authentication (Authorization header only)."""

    def __init__(self, token: str = "", required: Optional[bool] = None):
        self._token = token
        self._required = REQUIRE_AUTH if required is None else required

    @property
    def enabled(self) -> bool:
        return self._required

    def authenticate(self, headers: Dict[str, str]) -> bool:
        if not self._required:
            return True
        auth = ""
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth = value
                break
        if auth.startswith("Bearer "):
            return hmac.compare_digest(auth[7:], self._token)
        return False


_provider: Optional[AuthProvider] = None


def get_auth_provider() -> AuthProvider:
    """Return the process-wide auth provider (lazily created)."""
    global _provider
    if _provider is None:
        _provider = BearerAuthProvider(AUTH_TOKEN)
    return _provider


def reset_auth_provider() -> None:
    """Drop the cached provider (used by tests)."""
    global _provider
    _provider = None