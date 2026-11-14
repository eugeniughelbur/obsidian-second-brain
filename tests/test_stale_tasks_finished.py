"""A finished task is not a stale task.

check_stale_tasks reported every task with a past `due:` date, including tasks
whose frontmatter says `status: done`. On a vault that keeps its completed
tasks, half the "Stale tasks" warnings were finished work.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _task(status: str | None, due: str = "2000-01-01") -> dict:
    fm = "type: task\n"
    if status is not None:
        fm += f"status: {status}\n"
    fm += f"due: {due}\n"
    return {"frontmatter": fm, "content": "", "due": due}


def test_open_overdue_task_is_still_reported():
    from vault_health import check_stale_tasks

    issues = check_stale_tasks({"Tasks/open.md": _task("open")})
    assert [i["files"] for i in issues] == [["Tasks/open.md"]]


def test_task_with_no_status_is_still_reported():
    from vault_health import check_stale_tasks

    assert len(check_stale_tasks({"Tasks/nostatus.md": _task(None)})) == 1


def test_finished_tasks_are_not_reported():
    from vault_health import check_stale_tasks

    notes = {
        "Tasks/a.md": _task("done"),
        "Tasks/b.md": _task('"done"'),
        "Tasks/c.md": _task("'Done'"),
        "Tasks/d.md": _task("cancelled"),
        "Tasks/e.md": _task("completed"),
    }
    assert check_stale_tasks(notes) == []


def test_status_that_only_starts_with_done_is_not_treated_as_finished():
    from vault_health import check_stale_tasks

    # "done-pending-review" is not one of the finished states.
    assert len(check_stale_tasks({"Tasks/x.md": _task("done-pending-review")})) == 1
