"""User-owned permission policy for MCP tools.

The policy is deliberately small and predictable:

* ``read-only`` exposes inspection-only capabilities.
* ``standard`` enables the normal Android/Termux execution surface while
  keeping high-risk commands behind the command risk gate.
* ``full`` is an explicit owner opt-in for unrestricted Termux execution and
  advanced managed-MCP actions.

Managed MCP installation/removal/calls are intentionally *not* part of
``standard``. Third-party MCP servers may execute arbitrary package install,
build, or tool code, so those capabilities require ``full``.
"""

from . import config

MODES = {
    "read-only": "查看信息和文件，不允许修改或执行命令",
    "standard": "允许日常 Android/Termux 操作，高风险命令仍需确认",
    "full": "允许完整 Termux 控制，并启用高级第三方 MCP 执行能力",
}

_READ_ONLY_CAPABILITIES = {
    "filesystem.read",
    "device.read",
    "permissions.read",
    "managed.list",
}

_STANDARD_CAPABILITIES = _READ_ONLY_CAPABILITIES | {
    "command.run",
    "filesystem.write",
    "device.write",
}

_FULL_ONLY_CAPABILITIES = {
    "managed.install",
    "managed.remove",
    "managed.call",
}


def current_mode() -> str:
    return config.PERMISSION_MODE


def status() -> dict:
    mode = current_mode()
    return {
        "mode": mode,
        "description": MODES[mode],
        "full_control": mode == "full",
        "managed_execution": mode == "full",
        "change_command": "termux-mcp permissions set <read-only|standard|full>",
    }


def allows(capability: str) -> bool:
    mode = current_mode()
    if mode == "full":
        return True
    if mode == "standard":
        return capability in _STANDARD_CAPABILITIES
    return capability in _READ_ONLY_CAPABILITIES


def denied(capability: str) -> dict:
    required = "full" if capability in _FULL_ONLY_CAPABILITIES else "standard (or full)"
    return {
        "error": "permission_denied",
        "capability": capability,
        "permission_mode": current_mode(),
        "message": (
            "The device owner has not enabled this capability. "
            f"Required permission: {required}. Change it locally with: "
            "termux-mcp permissions set <mode>"
        ),
    }
