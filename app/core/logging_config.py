import logging
import sys
from app.core.config import settings

def setup_logging():
    """
    Configures the logging for the application.
    """
    log_level = settings.LOG_LEVEL.upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {log_level}")