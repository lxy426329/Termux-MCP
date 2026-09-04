# Development roadmap

This roadmap prioritizes the gap between “the server works” and “a new user can
reliably operate it.” Checked items describe the current `main` baseline.

## 0.9 — current foundation

- [x] Streamable HTTP MCP endpoint and REST API
- [x] shared operations layer
- [x] bearer authentication and persistent OAuth state
- [x] workspace and symlink escape protection
- [x] command risk classification and write snapshots
- [x] server/tunnel lifecycle commands
- [x] profile isolation
- [x] multi-provider tunnel fallback
- [x] pip-based installer and live MCP smoke test
- [x] zero-to-running bootstrap entry point

## 0.10 — installation and repair

- [ ] add `termux-mcp doctor --json` with stable check identifiers
- [ ] add targeted repair suggestions for package, PATH, port, tunnel, and permission failures
- [ ] add `termux-mcp update` with clean-tree checks and post-update rollback
- [ ] add an uninstall command that preserves user configuration by default
- [ ] verify bootstrap behavior on interrupted and repeated installations
- [ ] test F-Droid and GitHub Termux builds on Android 12, 14, and 16

## 0.11 — connection experience

- [ ] generate client-specific connection snippets without printing secrets
- [ ] add a local pairing page or QR handoff for the public MCP URL
- [ ] report tunnel URL changes and OAuth reauthorization requirements clearly
- [ ] add optional Termux:Boot integration
- [ ] add battery-optimization and background-process diagnostics

## 1.0 — stable release gate

- [ ] documented configuration migrations
- [ ] reproducible tagged releases with checksums
- [ ] automated clean-device installation tests
- [ ] threat-model and exposed-tool review
- [ ] compatibility matrix for major MCP clients
- [ ] recovery guide covering token rotation, tunnel failure, and corrupted state

