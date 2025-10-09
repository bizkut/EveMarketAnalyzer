from celery import Celery
from .config import settings

celery = Celery(
    "tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.data_fetching"]
)

celery.conf.update(
    task_track_started=True,
)