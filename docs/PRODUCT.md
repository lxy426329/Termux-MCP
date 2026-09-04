# Termux-MCP: project overview

## What it is

Termux-MCP turns an Android phone running Termux into a remotely accessible MCP
server for AI clients. The Python service exposes a deliberately limited set of
device and shell capabilities through Streamable HTTP, with authentication,
workspace boundaries, command-risk controls, process management, and optional
public tunnels.

It is not merely an Android port of an MCP server. Its product value is the
complete path from a fresh phone to a controlled AI endpoint:

1. bootstrap and diagnose the Termux environment;
2. install a versioned Python service and its dependencies;
3. start the local REST and MCP endpoints;
4. create and verify a public tunnel when requested;
5. preserve credentials and runtime state across restarts;
6. expose a small, reviewable tool surface rather than unrestricted device
   automation by default.

## Who it is for

- developers who want an inexpensive, portable MCP host;
- people experimenting with AI-to-Android workflows without maintaining a VPS;
- users who need selected phone capabilities available to an MCP client;
- educators and students who want a visible, inspectable MCP deployment.

## Why use this fork instead of the upstream project

The upstream project supplies the original Termux control foundation. This fork
keeps attribution and the REST API while adding an official-SDK MCP layer and a
deployment-focused product surface:

| Area | This fork's focus |
| --- | --- |
| Protocol | Streamable HTTP MCP endpoint built on the official Python SDK |
| Safety | bearer authentication, workspace confinement, symlink checks, command risk policy |
| Architecture | REST and MCP share the same operation functions instead of proxying through localhost |
| Reliability | managed server/tunnel state, health checks, persistent OAuth state, isolated profiles |
| Onboarding | one-line bootstrap, one-command start, doctor output, zero-background tutorial |

## Product promise

A new user should be able to paste one reviewed bootstrap command into a fresh
Termux installation, receive an actionable error if the environment is broken,
then run `termux-mcp start` and obtain the URL needed by an MCP client.

The project should never hide security-sensitive behavior to make setup look
simpler. Tokens remain local, dangerous shell actions remain governed by the
existing risk policy, and public exposure is explicit and diagnosable.

## Success criteria

- clean install succeeds without manual Python or JSON editing;
- repeated installation preserves configuration and secrets;
- every failed setup stage names the failed operation and a concrete next step;
- start/stop/restart behavior does not silently invalidate a retained tunnel;
- MCP and REST paths remain covered by shared-operation and security tests;
- a zero-background user can reach a healthy endpoint from the README alone.

