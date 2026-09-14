# Development roadmap

Termux-MCP has entered a **stabilization phase**.

The core product already works: an AI client can reach an Android / Termux execution node through MCP. Until the 1.0 release gate is met, the default priority is no longer adding capabilities. It is proving that installation, execution, security, connectivity, restart, and recovery are reliable on real devices.

The product boundary is defined in [PRODUCT.md](PRODUCT.md). New roadmap items should pass that scope test before entering the core plan.

## Current baseline — implemented

### Execution and protocol

- [x] Streamable HTTP MCP endpoint and retained REST API
- [x] shared operations layer used by REST and MCP
- [x] shell, filesystem, and Android device tools
- [x] structured tool responses and bounded output handling

### Security and ownership

- [x] bearer authentication
- [x] persistent OAuth state
- [x] owner-selectable read-only, standard, and full permission modes
- [x] workspace and symlink-escape protection
- [x] command risk classification and write snapshots

### Installation and connectivity

- [x] pip-based installer
- [x] zero-to-running bootstrap entry point
- [x] one-time guided setup for supported client profiles
- [x] server/tunnel lifecycle commands
- [x] multi-provider tunnel fallback
- [x] profile isolation
- [x] fixed-domain migration and route health helpers

### Diagnosis and verification

- [x] `termux-mcp doctor --json` with stable check identifiers
- [x] startup validation for profiles, ports, timeouts, and output limits
- [x] actionable installer log
- [x] unit/security tests and critical static checks in GitHub Actions
- [x] live MCP smoke test

### Advanced / experimental extensions

These are implemented but are not part of the 1.0 core release gate:

- [x] import remote MCP URLs
- [x] prepare common Python/Node.js GitHub MCP projects
- [x] managed-MCP install/list/inspect/call/remove tools

Until 1.0, these extensions should receive compatibility and security fixes, not major scope expansion.

## 0.x stabilization — next work

### P0 — real-device reliability

- [ ] verify clean bootstrap from a fresh supported Termux installation
- [ ] verify interrupted installation and repeated installation recovery
- [ ] run an end-to-end MCP session from an external client through the public endpoint
- [ ] verify server-only restart preserves valid tunnel and authorization state
- [ ] verify stop → start recovery after Android background/process interruption
- [ ] record failures and expected recovery behavior instead of fixing them only ad hoc

### P0 — Android lifecycle

- [ ] add diagnostics for Android battery optimization / background-process restrictions
- [ ] document and test `termux-wake-lock` behavior
- [ ] evaluate optional Termux:Boot integration without making it a hard dependency
- [ ] test at least two materially different Android / Termux environments before 1.0

Target matrix, subject to available physical devices:

- F-Droid Termux
- GitHub Termux build
- Android versions represented by available test devices

Do not claim compatibility for an Android version until it has actually been tested.

### P0 — security review

- [ ] write a concise threat model: trusted owner, remote AI client, public endpoint, third-party MCP extension
- [ ] review every exposed MCP tool and its permission requirements
- [ ] test dangerous-command rejection and warning/confirmation behavior end-to-end
- [ ] test workspace traversal and symlink escapes end-to-end
- [ ] verify credentials/tokens are not printed by normal diagnostics or connection helpers
- [ ] review full-permission mode wording and behavior so owner consent remains explicit

### P1 — installation and recovery UX

- [ ] add targeted repair suggestions for package, PATH, port, tunnel, and permission failures
- [ ] add `termux-mcp update` with clean-tree checks and post-update rollback
- [ ] add an uninstall command that preserves user configuration by default
- [ ] generate client-specific connection instructions without unnecessarily exposing secrets
- [ ] write a recovery guide covering token rotation, tunnel failure, corrupted state, and failed update

### P1 — release engineering

- [ ] document configuration migrations
- [ ] create reproducible tagged releases with checksums
- [ ] add automated clean-install coverage where practical
- [ ] define a minimal release checklist
- [ ] document tested MCP-client compatibility rather than assuming compatibility from protocol support

## 1.0 release gate

Termux-MCP 1.0 is ready when all of the following are true:

- [ ] a fresh supported Termux installation can reach a healthy MCP endpoint using only the documented bootstrap path
- [ ] core shell, filesystem, and Android tools have passed an external-client end-to-end test
- [ ] authentication and permission modes behave as documented
- [ ] restart, tunnel failure, Android process interruption, and token rotation have documented recovery paths
- [ ] the exposed-tool threat model has been reviewed
- [ ] at least two real-device / Termux environments have documented test results
- [ ] releases are tagged and reproducible enough to roll back to a known version
- [ ] README claims match the compatibility actually tested

## Deferred until after 1.0

Useful ideas are not deleted; they are intentionally prevented from delaying stabilization:

- local QR / pairing page
- broader automatic OAuth client migration
- major managed-MCP orchestration features
- additional third-party MCP runtimes and packaging heuristics
- richer domain-management UX

Anything that becomes a general MCP observability platform, workflow engine, VPS manager, marketplace, or application suite belongs in a separate project rather than this roadmap.

## Definition of progress

For the stabilization phase, a fixed failure, a reproducible test, a documented compatibility result, or a successful clean-device run counts as more progress than adding another tool.
