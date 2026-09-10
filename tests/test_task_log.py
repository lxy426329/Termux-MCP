from termux_mcp import task_log


def test_task_log_round_trip_and_step_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(task_log, "TASK_LOG_DIR", tmp_path)
    payload = {
        "ok": True,
        "requested_steps": 2,
        "executed_steps": 2,
        "failed": 0,
        "duration_ms": 12,
        "results": [
            {"step": 1, "tool": "one", "ok": True, "result": {"stdout": "alpha"}},
            {"step": 2, "tool": "two", "ok": True, "result": {"stdout": "beta"}},
        ],
    }

    task_id = task_log.save(payload)
    loaded = task_log.get(task_id)
    assert loaded["task_id"] == task_id
    assert loaded["payload"]["results"][1]["result"]["stdout"] == "beta"

    step = task_log.get(task_id, 2)
    assert step["step"]["tool"] == "two"
    assert step["step"]["result"]["stdout"] == "beta"


def test_task_log_lists_only_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(task_log, "TASK_LOG_DIR", tmp_path)
    task_log.save({
        "ok": False,
        "requested_steps": 1,
        "executed_steps": 1,
        "failed": 1,
        "duration_ms": 5,
        "results": [{"step": 1, "result": {"stdout": "x" * 5000}}],
    })

    listing = task_log.list_recent()
    assert listing["count"] == 1
    item = listing["tasks"][0]
    assert item["failed"] == 1
    assert "results" not in item


def test_task_log_rejects_invalid_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(task_log, "TASK_LOG_DIR", tmp_path)
    try:
        task_log.get("../escape")
    except task_log.TaskLogError:
        pass
    else:
        raise AssertionError("invalid task id should be rejected")
