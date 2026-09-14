# MCP OAuth and auth discovery

Termux-MCP supports two MCP authentication modes:

1. **Static Bearer token (default)** — `Authorization: Bearer <token>`.
2. **Optional OAuth 2.0 authorization-code + PKCE** — a self-hosted authorization server using the official MCP Python SDK abstractions.

Static Bearer remains valid when OAuth is enabled. Tokens are never accepted in URL query parameters.

## Safe default

OAuth is **disabled by default**. Normal setup does not silently enable it.

Enable OAuth only by configuring an issuer:

```bash
export TERMUX_MCP_OAUTH_ISSUER=https://mcp.example.com
export TERMUX_MCP_PUBLIC_URL=https://mcp.example.com
```

The current lightweight server does not yet provide an interactive device-owner consent UI. For that reason, the public `/authorize` route returns `403 access_denied` by default even when OAuth metadata is enabled.

Non-interactive automatic approval requires a separate, explicit local opt-in:

```bash
export TERMUX_MCP_OAUTH_AUTO_APPROVE=1
```

Only enable automatic approval when the endpoint and client trust model are fully owner-controlled. With automatic approval enabled, a dynamically registered client that satisfies the OAuth/PKCE checks can receive an authorization code without an additional human consent screen.

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `TERMUX_MCP_OAUTH_ISSUER` | Enables OAuth; concrete URL or `auto` | unset |
| `TERMUX_MCP_PUBLIC_URL` | Externally visible base URL | unset |
| `TERMUX_MCP_OAUTH_SCOPES` | Advertised/required scopes | `mcp:read mcp:write` |
| `TERMUX_MCP_OAUTH_AUTO_APPROVE` | Allow non-interactive authorization approval | `0` |

When the issuer is `auto`, it resolves from the current runtime public URL written by the tunnel launcher. Metadata is resolved from configured/runtime state and never trusts `Host` or `X-Forwarded-*` headers.

## Architecture

The implementation separates:

- **MCP Resource Server** — validates the static Bearer token and/or OAuth access tokens on `/mcp`, and serves RFC 9728 protected-resource metadata.
- **Authorization Server** — uses MCP SDK authorization, token, registration, and revocation handlers for authorization-code + PKCE, dynamic client registration, token exchange, refresh, and revocation.

The OAuth provider persists registered clients and refresh/access tokens to the profile config directory with mode `0600`. Authorization codes remain in memory only and are never persisted.

## Discovery endpoints

When OAuth is enabled, the server exposes:

| Endpoint | Purpose |
| --- | --- |
| `/.well-known/oauth-authorization-server` | Authorization-server metadata |
| `/.well-known/oauth-protected-resource` | RFC 9728 resource metadata |
| `/.well-known/oauth-protected-resource/mcp` | Path-form resource metadata |
| `/authorize` | Authorization endpoint; denied unless owner approval policy permits it |
| `/token` | Authorization-code / refresh-token exchange |
| `/register` | Dynamic client registration |
| `/revoke` | Token revocation |

Unauthenticated `/mcp` requests return `401` with a `WWW-Authenticate` challenge. When OAuth is disabled the challenge is plain Bearer; when enabled it includes protected-resource metadata and scopes.

## Security properties

- PKCE S256 is handled by the MCP SDK flow.
- Exact redirect URI validation is enforced by the SDK provider/handlers.
- Authorization codes are short-lived, one-time, and memory-only.
- Access tokens expire; refresh tokens rotate on exchange.
- Static Bearer comparison uses constant-time comparison.
- Secrets are not accepted in URL query parameters.
- Persistent OAuth state is written atomically with restrictive file permissions.
- Forwarded host headers do not determine advertised resource/issuer URLs.
- **Public authorization is denied by default unless the device owner explicitly enables automatic approval.**

## Dynamic tunnel example

Metadata can follow a dynamic public tunnel:

```bash
export TERMUX_MCP_OAUTH_ISSUER=auto
termux-mcp start --tunnel auto
```

This advertises OAuth metadata but `/authorize` still denies by default. If you intentionally want the current non-interactive approval mode, explicitly add:

```bash
export TERMUX_MCP_OAUTH_AUTO_APPROVE=1
```

For most owner-operated installations, the static Bearer path is simpler and safer until an interactive consent UI is implemented.

## Local checks

With OAuth metadata enabled:

```bash
curl -i http://127.0.0.1:8765/.well-known/oauth-protected-resource/mcp
curl -i http://127.0.0.1:8765/.well-known/oauth-authorization-server
curl -i http://127.0.0.1:8765/authorize
```

Without `TERMUX_MCP_OAUTH_AUTO_APPROVE=1`, the final request should return HTTP 403 with `access_denied`.

## Restart survival

A server-only `termux-mcp restart` can preserve a running tunnel/public URL. Registered OAuth clients and established refresh/access-token state are loaded again from the profile config directory; in-flight authorization codes do not survive restart.

## SDK assumptions

- Requires `mcp>=1.28,<2`.
- Termux-MCP uses a custom auth middleware to preserve its existing JSON 401 shape while adding standards-compliant `WWW-Authenticate` discovery information.
- Dynamic metadata handlers are used because the externally visible tunnel URL may change independently of the local MCP listener.
