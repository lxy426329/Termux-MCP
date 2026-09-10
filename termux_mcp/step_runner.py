"""Bounded multi-step execution for Termux-MCP.

The runner deliberately does not invent plans or replay failed side-effecting
steps. It executes an explicit list supplied by the caller, keeps intermediate
results local to the request, and returns one final aggregate response.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable

MAX_STEPS = 20
DEFAULT_STEP_TIMEOUT = 30.0


class StepRunnerError(ValueError):
    pass


def _failed(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("blocked") or result.get("confirmation_required"):
        return True
    if result.get("error"):
        return True
    exit_code = result.get("exit_code")
    return isinstance(exit_code, int) and exit_code != 0


async def run_steps(
    steps: list[dict[str, Any]],
    dispatcher: Callable[[str, dict[str, Any]], Awaitable[Any]],
    *,
    stop_on_error: bool = True,
    step_timeout: float = DEFAULT_STEP_TIMEOUT,
) -> dict[str, Any]:
    """Execute explicit steps sequentially and return one aggregate response."""
    if not isinstance(steps, list) or not steps:
        raise StepRunnerError("steps must be a non-empty list")
    if len(steps) > MAX_STEPS:
        raise StepRunnerError(f"too many steps: maximum is {MAX_STEPS}")
    if step_timeout <= 0 or step_timeout > 300:
        raise StepRunnerError("step_timeout must be > 0 and <= 300 seconds")

    started = time.monotonic()
    results: list[dict[str, Any]] = []
    stopped = False

    for index, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            raise StepRunnerError(f"step {index} must be an object")
        tool = str(raw.get("tool", "")).strip()
        arguments = raw.get("arguments", {})
        if not tool:
            raise StepRunnerError(f"step {index} is missing tool")
        if not isinstance(arguments, dict):
            raise StepRunnerError(f"step {index} arguments must be an object")

        step_started = time.monotonic()
        try:
            value = await asyncio.wait_for(dispatcher(tool, arguments), timeout=step_timeout)
            failed = _failed(value)
            item = {
                "step": index,
                "tool": tool,
                "ok": not failed,
                "duration_ms": round((time.monotonic() - step_started) * 1000),
                "result": value,
            }
        except asyncio.TimeoutError:
            failed = True
            item = {
                "step": index,
                "tool": tool,
                "ok": False,
                "duration_ms": round((time.monotonic() - step_started) * 1000),
                "error": f"step timed out after {step_timeout:g}s",
            }
        except Exception as exc:
            failed = True
            item = {
                "step": index,
                "tool": tool,
                "ok": False,
                "duration_ms": round((time.monotonic() - step_started) * 1000),
                "error": str(exc),
            }

        results.append(item)
        if failed and stop_on_error:
            stopped = index < len(steps)
            break

    succeeded = sum(1 for item in results if item["ok"])
    failed_count = len(results) - succeeded
    return {
        "ok": failed_count == 0 and len(results) == len(steps),
        "requested_steps": len(steps),
        "executed_steps": len(results),
        "succeeded": succeeded,
        "failed": failed_count,
        "stopped_early": stopped,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "results": results,
    }
