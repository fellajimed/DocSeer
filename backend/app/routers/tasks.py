"""
Tasks router
────────────
GET /tasks/{task_id}  – poll a Celery task and return its current state
"""

from __future__ import annotations

from fastapi import APIRouter

from ..celery_app import celery_app
from ..schemas.task import TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatus)
async def get_task(task_id: str) -> TaskStatus:
    """
    Return the current state of a Celery task.

    States mirrored from Celery:
      PENDING  – task is queued or unknown
      STARTED  – task has been picked up by a worker; `progress` contains the
                 latest step dict sent via update_state()
      SUCCESS  – task completed; `result` is the return value
      FAILURE  – task raised an exception; `error` contains the message
      RETRY    – task is being retried
      REVOKED  – task was cancelled
    """
    result = celery_app.AsyncResult(task_id)
    state = result.state

    progress: dict | None = None
    error: str | None = None
    task_result = None

    if state == "STARTED":
        # update_state() meta dict is available in result.info
        info = result.info or {}
        progress = {k: v for k, v in info.items() if k != "exc_message"}

    elif state == "SUCCESS":
        task_result = result.result

    elif state in ("FAILURE", "RETRY"):
        exc = result.result
        error = repr(exc) if exc is not None else "Unknown error"

    return TaskStatus(
        task_id=task_id,
        state=state,
        result=task_result,
        error=error,
        progress=progress,
    )
