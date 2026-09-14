# Termux-MCP: product scope

## One-line definition

**Termux-MCP turns an Android phone running Termux into a secure local execution node for AI clients through MCP.**

The core path is deliberately narrow:

**AI client ↔ MCP gateway ↔ Android / Termux**

Termux-MCP is not intended to become a general workflow platform, VPS manager, MCP marketplace, or application suite.

## What problem it solves

AI clients can reason and call tools, but a normal Android phone is not automatically a stable, remotely reachable execution environment. Termux-MCP closes that gap by providing the complete path from a fresh Termux installation to a controlled MCP endpoint:

1. bootstrap and diagnose the Termux environment;
2. install and start the Python service;
3. expose shell, filesystem, and Android device capabilities through standard MCP;
4. authenticate the remote client and enforce owner-selected permissions;
5. create and verify a public tunnel when remote access is needed;
6. preserve credentials and runtime state across restarts;
7. provide diagnostics and recovery information when something fails.

## Who it is for

- users who want ChatGPT, Claude, or another MCP-capable client to operate their own Android / Termux environment;
- developers who want a portable, inexpensive Android execution node for AI-assisted tasks;
- users who want this capability without manually maintaining a custom REST integration for each AI client.

## Product principles

### 1. Android first

The phone is the product boundary. Features should improve Android / Termux execution, connectivity, safety, reliability, installation, or recovery.

### 2. MCP is the interface, not the product itself

MCP provides the standard connection between AI clients and the phone. Termux-MCP should not grow into a universal MCP ecosystem merely because MCP makes that possible.

### 3. The owner controls the boundary

The phone owner chooses the permission level. Authentication, command-risk classification, workspace restrictions, path validation, write safeguards, and other security mechanisms exist to make high-capability execution controllable.

### 4. Reliability before feature count

A small set of tools that installs cleanly, survives restarts, reports failures clearly, and works on real Android devices is more valuable than a large feature surface that is difficult to operate.

### 5. Conversation after bootstrap

A new user should need minimal terminal knowledge: bootstrap the service, choose the relevant settings, connect the MCP client, then perform normal operation and diagnosis through the connected AI where practical.

## Scope

### Core

These capabilities define Termux-MCP:

- Streamable HTTP MCP endpoint;
- shell command execution;
- filesystem operations;
- Android device capabilities exposed by Termux;
- shared operation layer used by MCP and the retained REST interface;
- owner-selected permission modes;
- command-risk and write safeguards;
- workspace boundary and symlink-escape protection;
- authentication required for remote control.

### Supporting infrastructure

These capabilities exist to make the core usable and reliable, but are not separate product identities:

- bootstrap and installer;
- OAuth / bearer authentication compatibility;
- public tunnel creation and health verification;
- tunnel and server lifecycle management;
- persistent runtime and authorization state;
- profile isolation;
- status, logs, doctor, repair and recovery tooling;
- optional fixed-domain support;
- Android background-process and boot integration where useful.

### Advanced / experimental extensions

These features may remain available, but must not drive the core roadmap or complicate the default experience:

- importing remote MCP servers;
- hosting or preparing third-party MCP projects on the phone;
- managed-MCP install/list/inspect/call/remove tools;
- compatibility helpers for third-party Python or Node.js MCP projects.

Extensions should remain separable from the Android execution gateway. If maintaining an extension begins to require its own registry, marketplace, workflow engine, broad runtime platform, or independent product surface, it should move to a separate project.

### Out of scope

The following are intentionally not Termux-MCP responsibilities:

- general-purpose MCP observability or visualization platforms;
- workflow / agent orchestration systems;
- VPS or generic remote-server fleet management;
- MCP marketplaces or universal package registries;
- personal home, sleep, memory, productivity, or lifestyle applications;
- application-specific business logic that can simply use Termux-MCP as an execution layer.

These can be separate projects built on top of Termux-MCP.

## Why this fork exists

The upstream project supplies the original Termux control foundation. This fork keeps attribution and the REST API while focusing on a standards-compliant MCP interface and a deployable Android execution experience.

The main engineering additions include:

- Streamable HTTP MCP using the official Python SDK;
- a shared operations layer rather than MCP proxying through localhost REST;
- owner-selected permission modes and execution safeguards;
- authentication and persistent authorization state;
- server/tunnel lifecycle management and health checks;
- isolated profiles and recovery diagnostics;
- one-command bootstrap and guided setup.

## Product promise

A new user should be able to start with a fresh supported Termux installation, run the documented bootstrap path, connect an MCP-capable AI client, and obtain a healthy Android execution node without manually editing Python or JSON configuration.

Once connected, the node should remain understandable and recoverable: failures should identify what broke, restarts should not silently destroy valid state, and security boundaries should remain visible to the owner.

## Success criteria

Before adding substantial new core functionality, prioritize proving that the existing product works reliably:

- clean installation succeeds on supported Termux / Android combinations;
- repeated or interrupted installation has a defined recovery path;
- shell, filesystem, and Android tools work end-to-end through MCP;
- authentication and permission boundaries behave as documented;
- dangerous commands, path traversal, and symlink escapes are covered by tests;
- server restart does not unnecessarily invalidate retained tunnel or authorization state;
- failures expose actionable diagnostics rather than silent breakage;
- a zero-background user can reach a healthy endpoint from the README alone;
- supported MCP clients have a documented compatibility matrix;
- releases are reproducible and have a documented rollback / recovery path.

## Scope test for future features

Before adding a feature to the core project, ask:

> Does this directly improve an Android phone acting as a secure AI execution node?

If yes, it may belong in Core or Supporting Infrastructure.

If it only extends what can be built on top of the node, prefer an extension.

If it creates a new product identity, put it in a separate project.
