from celery import Celery

from .config import get_settings

_settings = get_settings()

celery_app = Celery(
    "docseer",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=["backend.app.tasks.ingest"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=86_400,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.ingest_paper": {"queue": "ingest"},
    },
)
