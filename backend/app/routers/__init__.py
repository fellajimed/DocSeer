from .papers import router as papers_router
from .chat import router as chat_router
from .tasks import router as tasks_router
from .settings import router as settings_router

__all__ = ["papers_router", "chat_router", "tasks_router", "settings_router"]
