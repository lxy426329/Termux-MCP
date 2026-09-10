"""Local persistent logs for multi-step workflows.

Full workflow results stay on the Termux device so chat clients can request a
compact summary first and fetch only the task/step details they actually need.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .config import CONFIG_DIR

TASK_LOG_DIR = Path(CONFIG_DIR) / "task_logs"
MAX_LOG_FILES = 200


class TaskLogError(ValueError):
    pass


def _safe_id(task_id: str) -> str:
    value = str(task_id).strip().lower()
    if not value or any(ch not in "0123456789abcdef-" for ch in value):
        raise TaskLogError("invalid task_id")
    return value


def _path(task_id: str) -> Path:
    return TASK_LOG_DIR / f"{_safe_id(task_id)}.json"


def _prune() -> None:
    try:
        files = sorted(TASK_LOG_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[MAX_LOG_FILES:]:
            try:
                path.unlink()
            except OSError:
                pass
    except OSError:
        pass


def save(payload: dict[str, Any]) -> str:
    """Persist a full workflow result and return its task id."""
    task_id = uuid.uuid4().hex
    TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
    document = {
        "task_id": task_id,
        "created_at": int(time.time()),
        "payload": payload,
    }
    path = _path(task_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    _prune()
    return task_id


def load(task_id: str) -> dict[str, Any]:
    path = _path(task_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskLogError(f"task {task_id!r} was not found") from exc
    except (OSError, ValueError) as exc:
        raise TaskLogError(f"could not read task {task_id!r}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
        raise TaskLogError("invalid task log")
    return data


def get(task_id: str, step: int = 0) -> dict[str, Any]:
    """Return the whole stored workflow, or one 1-based step when requested."""
    data = load(task_id)
    if not step:
        return data
    if step < 1:
        raise TaskLogError("step must be 0 or a positive integer")
    results = data["payload"].get("results", [])
    if step > len(results):
        raise TaskLogError(f"step {step} was not found in task {task_id!r}")
    return {
        "task_id": data["task_id"],
        "created_at": data["created_at"],
        "step": results[step - 1],
    }


def list_recent(limit: int = 20) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise TaskLogError("limit must be between 1 and 100")
    TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(TASK_LOG_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            payload = data.get("payload", {})
            items.append({
                "task_id": data.get("task_id", path.stem),
                "created_at": data.get("created_at"),
                "ok": payload.get("ok"),
                "requested_steps": payload.get("requested_steps"),
                "executed_steps": payload.get("executed_steps"),
                "failed": payload.get("failed"),
                "duration_ms": payload.get("duration_ms"),
            })
        except (OSError, ValueError):
            continue
    return {"tasks": items, "count": len(items)}
