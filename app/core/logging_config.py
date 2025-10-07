import logging
import sys
from app.core.config import settings

def setup_logging():
    """
    Configures the logging for the application.
    This function is designed to be idempotent, so it can be called multiple times
    without causing issues (e.g., by both the main app and Celery workers).
    """
    log_level = settings.LOG_LEVEL.upper()

    # Get the root logger
    root_logger = logging.getLogger()

    # Remove any existing handlers to prevent duplicate logging
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Set the level on the root logger
    root_logger.setLevel(log_level)

    # Create a handler and formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    # Add the handler to the root logger
    root_logger.addHandler(handler)

    # Set levels for other loggers to reduce noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    # Log this message only once to avoid clutter during reloads
    if not getattr(setup_logging, "already_run", False):
        logger.info(f"Logging configured with level: {log_level}")
        setup_logging.already_run = True