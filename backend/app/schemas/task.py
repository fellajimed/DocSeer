from typing import Any

from pydantic import BaseModel


class TaskStatus(BaseModel):
    task_id: str
    # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
    state: str
    result: Any | None = None
    error: str | None = None
    # intermediate progress dict sent via update_state()
    progress: dict[str, Any] | None = None
