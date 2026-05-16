from typing import Any

from pydantic import BaseModel


class TaskStatus(BaseModel):
    task_id: str
    state: str
    result: Any | None = None
    error: str | None = None
    progress: dict[str, Any] | None = None
