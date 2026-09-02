# MCP OAuth Roadmap

Current state: termux-mcp authenticates MCP clients with a **static Bearer
token** (`Authorization: Bearer <token>` header only — tokens in URL query
parameters are never accepted). This is simple, works with every MCP client
that supports custom headers, and is safe when the endpoint is only reachable
through an authenticated tunnel.

The MCP authorization spec (2025-06-18 and later protocol versions) defines a
standard OAuth 2.0 flow for MCP clients. This document describes exactly what
is needed to add it — nothing here is implemented yet, and we will not fake an
OAuth flow or put the Bearer token into a URL.

## Why not yet

- The static Bearer token already covers the primary use case (ChatGPT /
  custom MCP clients with header support).
- A correct OAuth implementation needs a browser/device authorization flow,
  token storage, refresh handling, and client registration — a meaningful
  amount of code that must not weaken the existing security model.
- The auth layer is already abstracted (`termux_mcp/auth.py`) so the REST and
  MCP handlers do not need to change when OAuth lands.

## Implementation plan

1. **Discovery** — serve `/.well-known/oauth-authorization-server` on the MCP
   endpoint advertising `authorization_endpoint`, `token_endpoint`, and
   `registration_endpoint`.
2. **Client registration** — support dynamic client registration (RFC 7591)
   or a small set of pre-registered clients.
3. **Authorization Code + PKCE** (RFC 7636) — device/browser flow so the user
   approves access on the phone; `code_challenge`/`code_verifier` required.
4. **Token endpoint** — issue short-lived access tokens; the resource server
   (MCP Streamable HTTP app) validates them instead of the static Bearer.
5. **Backward compatibility** — keep the static Bearer provider as a fallback
   config option (`TERMUX_MCP_AUTH_MODE=bearer|oauth`), defaulting to `bearer`.

## Security invariants that must survive the OAuth work

- No tokens in URL query parameters.
- No weakening of risk grading / confirmation / workspace restrictions.
- No automatic disabling of authentication.
- Secrets never logged or uploaded.