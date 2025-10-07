from celery import Celery
from app.core.config import settings
from celery.signals import after_setup_logger
from app.core.logging_config import setup_logging

celery_app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.data_fetching",
        "app.tasks.analysis",
        "app.tasks.scheduler"
    ]
)

celery_app.conf.update(
    task_track_started=True,
)

@after_setup_logger.connect
def on_after_setup_logger(logger, **kwargs):
    """
    Configures the logger for Celery workers.
    This function is connected to the `after_setup_logger` signal to ensure
    that the logging configuration is applied to Celery workers.
    """
    setup_logging()