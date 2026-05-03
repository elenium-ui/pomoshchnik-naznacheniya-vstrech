import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    """Configure console and file logging for early-stage diagnostics."""
    Path("logs").mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(level.upper())
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level.upper())
    console_handler.setFormatter(formatter)

    app_file_handler = RotatingFileHandler(
        "logs/app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    app_file_handler.setLevel(level.upper())
    app_file_handler.setFormatter(formatter)

    error_file_handler = RotatingFileHandler(
        "logs/error.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(app_file_handler)
    logger.addHandler(error_file_handler)
