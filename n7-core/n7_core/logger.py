
import logging
import sys
from pythonjsonlogger import jsonlogger
from .config import settings

def setup_logging():
    """
    Configures structured logging for the application.
    Uses JSON formatting in production, standard formatting in development.
    """
    logger = logging.getLogger()
    
    # clear existing handlers
    for handler in logger.handlers:
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    
    if settings.ENVIRONMENT == "production":
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            json_ensure_ascii=False
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(settings.LOG_LEVEL)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    return logger

logger = setup_logging()
