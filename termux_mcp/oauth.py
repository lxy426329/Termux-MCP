"""Optional OAuth 2.0 authorization-server and auth-discovery support.

OAuth is disabled unless TERMUX_MCP_OAUTH_ISSUER is configured. The public
/authorize route is denied by default because this lightweight server does not
yet provide an interactive device-owner consent UI. Non-interactive approval
requires the explicit local TERMUX_MCP_OAUTH_AUTO_APPROVE=1 opt-in.
"""

import json
import os
import secrets
import threading
import time
from typing import List, Optional
from urllib.parse import urlparse

from . import config

_PUBLIC_PATHS = {"/authorize", "/token", "/register", "/revoke"}
_OAUTH_STATE_FILE = os.path.join(config.CONFIG_DIR, "oauth_state.json")


def oauth_enabled() -> bool:
    issuer = config.OAUTH_ISSUER.strip()
    return bool(issuer) and (issuer == "auto" or _valid_http_url(issuer))


def auto_approve_enabled() -> bool:
    return bool(config.OAUTH_AUTO_APPROVE)


def get_scopes() -> List[str]:
    return [scope for scope in config.OAUTH_SCOPES.split() if scope]


def get_public_url() -> Optional[str]:
    value = config.get_public_url().strip().rstrip("/")
    return value or None


def get_issuer() -> Optional[str]:
    if not oauth_enabled():
        return None
    issuer = config.OAUTH_ISSUER.strip()
    if issuer != "auto":
        return issuer.rstrip("/")
    return get_public_url()


def get_resource_url() -> Optional[str]:
    base = get_public_url() or get_issuer()
    return base.rstrip("/") + "/mcp" if base else None


def get_metadata_url() -> Optional[str]:
    resource = get_resource_url()
    if not resource:
        return None
    parsed = urlparse(resource)
    return (
        f"{parsed.scheme}://{parsed.netloc}"
        f"/.well-known/oauth-protected-resource{parsed.path}"
    )


def is_public_path(path: str) -> bool:
    return oauth_enabled() and (
        path in _PUBLIC_PATHS or path.startswith("/.well-known/")
    )


def _valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


class InMemoryAuthProvider:
    """MCP SDK OAuth provider with persistent established-session state."""

    def __init__(
        self,
        scopes: List[str],
        code_ttl: float = 60.0,
        access_ttl: int = 3600,
        refresh_ttl: int = 7 * 24 * 3600,
        state_file: Optional[str] = None,
    ):
        self._scopes = scopes
        self._code_ttl = code_ttl
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._clients = {}
        self._codes = {}
        self._refresh_tokens = {}
        self._access_tokens = {}
        self._state_file = state_file or _OAUTH_STATE_FILE
        self._lock = threading.Lock()
        self._load_state()

    def _load_state(self) -> None:
        if not self._state_file:
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return

        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthClientInformationFull

        now = time.time()
        for client_id, raw in (data.get("clients") or {}).items():
            try:
                self._clients[client_id] = OAuthClientInformationFull.model_validate(raw)
            except Exception:
                continue
        for token, raw in (data.get("refresh_tokens") or {}).items():
            try:
                value = RefreshToken.model_validate(raw)
            except Exception:
                continue
            if not value.expires_at or value.expires_at >= now:
                self._refresh_tokens[token] = value
        for token, raw in (data.get("access_tokens") or {}).items():
            try:
                value = AccessToken.model_validate(raw)
            except Exception:
                continue
            if not value.expires_at or value.expires_at >= now:
                self._access_tokens[token] = value

    def _save_state(self) -> None:
        if not self._state_file:
            return
        data = {
            "clients": {
                key: value.model_dump(mode="json")
                for key, value in self._clients.items()
            },
            "refresh_tokens": {
                key: value.model_dump(mode="json")
                for key, value in self._refresh_tokens.items()
            },
            "access_tokens": {
                key: value.model_dump(mode="json")
                for key, value in self._access_tokens.items()
            },
        }
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        temp = self._state_file + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self._state_file)

    async def get_client(self, client_id: str):
        return self._clients.get(client_id)

    async def register_client(self, client_info) -> None:
        with self._lock:
            self._clients[client_info.client_id] = client_info
            self._save_state()

    async def authorize(self, client, params) -> str:
        from mcp.server.auth.provider import AuthorizationCode, construct_redirect_uri

        code = secrets.token_urlsafe(32)
        self._codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or self._scopes,
            expires_at=time.time() + self._code_ttl,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=None,
        )
        return construct_redirect_uri(
            str(params.redirect_uri), code=code, state=params.state
        )

    async def load_authorization_code(self, client, authorization_code: str):
        code = self._codes.get(authorization_code)
        if code is None:
            return None
        if code.expires_at < time.time():
            self._codes.pop(authorization_code, None)
            return None
        return code

    async def exchange_authorization_code(self, client, authorization_code):
        with self._lock:
            self._codes.pop(authorization_code.code, None)
            result = self._issue_tokens(
                client, authorization_code.scopes, authorization_code.subject
            )
            self._save_state()
            return result

    async def load_refresh_token(self, client, refresh_token: str):
        with self._lock:
            token = self._refresh_tokens.get(refresh_token)
            if token is None:
                return None
            if token.expires_at and token.expires_at < time.time():
                self._refresh_tokens.pop(refresh_token, None)
                self._save_state()
                return None
            return token

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        with self._lock:
            self._refresh_tokens.pop(refresh_token.token, None)
            result = self._issue_tokens(client, scopes, refresh_token.subject)
            self._save_state()
            return result

    async def load_access_token(self, token: str):
        with self._lock:
            access = self._access_tokens.get(token)
            if access is None:
                return None
            if access.expires_at and access.expires_at < time.time():
                self._access_tokens.pop(token, None)
                self._save_state()
                return None
            return access

    async def revoke_token(self, token) -> None:
        from mcp.server.auth.provider import AccessToken, RefreshToken

        with self._lock:
            if isinstance(token, AccessToken):
                self._access_tokens.pop(token.token, None)
            elif isinstance(token, RefreshToken):
                self._refresh_tokens.pop(token.token, None)
            self._save_state()

    def _issue_tokens(self, client, scopes, subject=None):
        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken

        access_value = secrets.token_urlsafe(32)
        refresh_value = secrets.token_urlsafe(32)
        now = int(time.time())
        self._access_tokens[access_value] = AccessToken(
            token=access_value,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=now + self._access_ttl,
            subject=subject,
        )
        self._refresh_tokens[refresh_value] = RefreshToken(
            token=refresh_value,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=now + self._refresh_ttl,
            subject=subject,
        )
        return OAuthToken(
            access_token=access_value,
            token_type="Bearer",
            expires_in=self._access_ttl,
            scope=" ".join(scopes),
            refresh_token=refresh_value,
        )


_auth_server_provider: Optional[InMemoryAuthProvider] = None


def get_auth_server_provider() -> InMemoryAuthProvider:
    global _auth_server_provider
    if _auth_server_provider is None:
        _auth_server_provider = InMemoryAuthProvider(get_scopes())
    return _auth_server_provider


def reset_auth_server_provider() -> None:
    global _auth_server_provider
    _auth_server_provider = None


def get_token_verifier():
    from mcp.server.auth.provider import ProviderTokenVerifier

    return ProviderTokenVerifier(get_auth_server_provider())


class _DynamicAuthServerMetadataHandler:
    async def handle(self, request):
        from mcp.server.auth.json_response import PydanticJSONResponse
        from mcp.shared.auth import OAuthMetadata
        from pydantic import AnyHttpUrl
        from starlette.responses import JSONResponse

        issuer = get_issuer()
        if not issuer:
            return JSONResponse({"error": "not_found"}, status_code=404)
        value = OAuthMetadata(
            issuer=AnyHttpUrl(issuer),
            authorization_endpoint=AnyHttpUrl(issuer + "/authorize"),
            token_endpoint=AnyHttpUrl(issuer + "/token"),
            registration_endpoint=AnyHttpUrl(issuer + "/register"),
            revocation_endpoint=AnyHttpUrl(issuer + "/revoke"),
            scopes_supported=get_scopes(),
            response_types_supported=["code"],
            grant_types_supported=["authorization_code", "refresh_token"],
            token_endpoint_auth_methods_supported=[
                "client_secret_post", "client_secret_basic"
            ],
            code_challenge_methods_supported=["S256"],
        )
        return PydanticJSONResponse(
            content=value, headers={"Cache-Control": "public, max-age=3600"}
        )


class _DynamicProtectedResourceHandler:
    async def handle(self, request):
        from mcp.server.auth.json_response import PydanticJSONResponse
        from mcp.shared.auth import ProtectedResourceMetadata
        from pydantic import AnyHttpUrl
        from starlette.responses import JSONResponse

        resource = get_resource_url()
        issuer = get_issuer()
        if not resource or not issuer:
            return JSONResponse({"error": "not_found"}, status_code=404)
        value = ProtectedResourceMetadata(
            resource=AnyHttpUrl(resource),
            authorization_servers=[AnyHttpUrl(issuer)],
            scopes_supported=get_scopes(),
            bearer_methods_supported=["header"],
        )
        return PydanticJSONResponse(
            content=value, headers={"Cache-Control": "public, max-age=3600"}
        )


def build_auth_routes() -> list:
    """Build OAuth routes with the SDK version's required authenticators."""
    from mcp.server.auth.handlers.authorize import AuthorizationHandler
    from mcp.server.auth.handlers.register import RegistrationHandler
    from mcp.server.auth.handlers.revoke import RevocationHandler
    from mcp.server.auth.handlers.token import TokenHandler
    from mcp.server.auth.middleware.client_auth import ClientAuthenticator
    from mcp.server.auth.routes import cors_middleware
    from mcp.server.auth.settings import ClientRegistrationOptions
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    provider = get_auth_server_provider()
    client_authenticator = ClientAuthenticator(provider)
    registration_options = ClientRegistrationOptions(
        enabled=True,
        valid_scopes=get_scopes(),
        default_scopes=get_scopes(),
    )
    authorize_handler = AuthorizationHandler(provider)

    async def guarded_authorize(request):
        if not auto_approve_enabled():
            return JSONResponse(
                {
                    "error": "access_denied",
                    "error_description": (
                        "OAuth automatic approval is disabled. Set "
                        "TERMUX_MCP_OAUTH_AUTO_APPROVE=1 locally only if you "
                        "intentionally accept non-interactive approval."
                    ),
                },
                status_code=403,
            )
        return await authorize_handler.handle(request)

    return [
        Route(
            "/.well-known/oauth-authorization-server",
            endpoint=cors_middleware(
                _DynamicAuthServerMetadataHandler().handle, ["GET", "OPTIONS"]
            ),
            methods=["GET", "OPTIONS"],
        ),
        Route("/authorize", endpoint=guarded_authorize, methods=["GET", "POST"]),
        Route(
            "/token",
            endpoint=cors_middleware(
                TokenHandler(provider, client_authenticator).handle,
                ["POST", "OPTIONS"],
            ),
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/register",
            endpoint=cors_middleware(
                RegistrationHandler(provider, registration_options).handle,
                ["POST", "OPTIONS"],
            ),
            methods=["POST", "OPTIONS"],
        ),
        Route(
            "/revoke",
            endpoint=cors_middleware(
                RevocationHandler(provider, client_authenticator).handle,
                ["POST", "OPTIONS"],
            ),
            methods=["POST", "OPTIONS"],
        ),
    ]


def build_protected_resource_routes() -> list:
    from mcp.server.auth.routes import cors_middleware
    from starlette.routing import Route

    handler = _DynamicProtectedResourceHandler()
    return [
        Route(
            "/.well-known/oauth-protected-resource",
            endpoint=cors_middleware(handler.handle, ["GET", "OPTIONS"]),
            methods=["GET", "OPTIONS"],
        ),
        Route(
            "/.well-known/oauth-protected-resource/mcp",
            endpoint=cors_middleware(handler.handle, ["GET", "OPTIONS"]),
            methods=["GET", "OPTIONS"],
        ),
    ]
